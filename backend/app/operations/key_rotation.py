"""Token encryption key rotation service and job handler (Phase 8 Session 12, P8-06).

Rotates stored OAuth tokens from older keys in TOKEN_ENCRYPTION_KEYS to
TOKEN_ENCRYPTION_ACTIVE_KEY_ID in-place across social_accounts while preserving
tenant AAD bindings and recording immutable security audit events (INV-08).
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass
from typing import Any

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.audit import service as audit
from app.core.clock import Clock
from app.core.config import Settings, get_settings
from app.core.context import ActorRef
from app.core.db import set_tenant_context
from app.core.security import TokenCryptoError, TokenKeyRing, account_token_aad
from app.integrations.instagram.models import SocialAccount
from app.jobs.registry import JobContext, job_handler

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class KeyRotationResult:
    scanned: int = 0
    rotated: int = 0
    skipped: int = 0
    failed: int = 0
    active_key_id: str = ""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


class RotateTokenKeysPayload(BaseModel):
    batch_size: int = 100


def rotate_social_account_tokens(
    session_factory: sessionmaker[Session],
    settings: Settings,
    clock: Clock,
    *,
    batch_size: int = 100,
) -> KeyRotationResult:
    """Scan and re-encrypt social_accounts with outdated token_key_id in bounded batches."""
    keys_raw = settings.token_encryption_keys.get_secret_value()
    active_key_id = settings.token_encryption_active_key_id

    if not keys_raw or not active_key_id:
        logger.warning("Token key rotation skipped: TOKEN_ENCRYPTION_KEYS or active key ID not set")
        return KeyRotationResult(active_key_id=active_key_id)

    # Validate keyring upfront before modifying rows
    ring = TokenKeyRing(keys_raw, active_key_id)

    # 1. Discover candidates across workspaces (pre-context query on social_accounts)
    with session_factory() as session:
        candidates = list(
            session.execute(
                select(SocialAccount.id, SocialAccount.workspace_id, SocialAccount.token_key_id)
                .where(
                    SocialAccount.provider_kind == "meta",
                    SocialAccount.token_ciphertext.is_not(None),
                    SocialAccount.token_key_id != active_key_id,
                    SocialAccount.status != "disconnected",
                )
                .limit(batch_size)
            ).all()
        )

    scanned = len(candidates)
    rotated = 0
    skipped = 0
    failed = 0

    # 2. Process each account inside its own tenant-scoped transaction
    for account_id, workspace_id, old_key_id in candidates:
        with session_factory() as session:
            set_tenant_context(session, workspace_id)
            account = session.scalars(
                select(SocialAccount)
                .where(SocialAccount.workspace_id == workspace_id, SocialAccount.id == account_id)
                .with_for_update()
            ).first()

            if (
                account is None
                or account.status == "disconnected"
                or account.token_ciphertext is None
                or account.token_key_id is None
                or account.token_key_id == active_key_id
            ):
                skipped += 1
                session.commit()
                continue

            aad = account_token_aad(workspace_id, account.id)
            try:
                # Decrypt using old key ID, re-encrypt using active key ID
                plaintext = ring.decrypt(account.token_ciphertext, account.token_key_id, aad=aad)
                new_ciphertext, new_key_id = ring.encrypt(plaintext, aad=aad)

                account.token_ciphertext = new_ciphertext
                account.token_key_id = new_key_id
                account.token_refreshed_at = clock.now()

                audit.record(
                    session,
                    None,
                    "security.token_key_rotated",
                    "social_account",
                    account.id,
                    {
                        "workspace_id": str(workspace_id),
                        "old_key_id": old_key_id,
                        "new_key_id": new_key_id,
                    },
                    clock=clock,
                    actor=ActorRef.system("key_rotation"),
                )
                session.commit()
                rotated += 1
            except TokenCryptoError as err:
                account.last_error_code = "KEY_ROTATION_FAILED"
                audit.record(
                    session,
                    None,
                    "security.token_key_rotation_failed",
                    "social_account",
                    account.id,
                    {
                        "workspace_id": str(workspace_id),
                        "old_key_id": old_key_id,
                        "error": str(err),
                    },
                    clock=clock,
                    actor=ActorRef.system("key_rotation"),
                )
                session.commit()
                failed += 1

    return KeyRotationResult(
        scanned=scanned,
        rotated=rotated,
        skipped=skipped,
        failed=failed,
        active_key_id=active_key_id,
    )


@job_handler("rotate_token_keys", RotateTokenKeysPayload, max_attempts=1)
def handle_rotate_token_keys(job: JobContext) -> None:
    """Worker background job handler for token encryption key rotation."""
    payload = (
        job.payload
        if isinstance(job.payload, RotateTokenKeysPayload)
        else RotateTokenKeysPayload.model_validate(job.payload)
    )
    settings = get_settings()
    result = rotate_social_account_tokens(
        job.session_factory, settings, job.clock, batch_size=payload.batch_size
    )
    logger.info(
        "Token key rotation completed: scanned=%d, rotated=%d, skipped=%d, failed=%d, "
        "active_key_id=%s",
        result.scanned,
        result.rotated,
        result.skipped,
        result.failed,
        result.active_key_id,
    )
