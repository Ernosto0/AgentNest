"""Single-use Telegram tokens for "save this answer as a verified fact" (D-05).

Same shape as the approval action tokens (ADR-012, INV-16): a random token is shown only as the
button's callback data, only its hash is stored, it is bound to one candidate and one user, it
expires and the first tap consumes it. The token authorises nothing by itself: the tap runs the
ordinary candidate accept (``knowledge.verify``) as the linked user.
"""

import hashlib
import secrets
import uuid
from datetime import timedelta

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core.clock import Clock
from app.core.context import WorkspaceContext
from app.core.db import set_tenant_context
from app.core.errors import AppError
from app.core.ids import new_id
from app.identity.channels import ChannelLinkService
from app.owner_requests.models import FactSaveToken

FACT_SAVE_TOKEN_TTL = timedelta(hours=48)
CALLBACK_PREFIX = "fsv:"


def hash_token(raw: str) -> str:
    return hashlib.sha256(raw.strip().encode("utf-8")).hexdigest()


def create(
    db: Session,
    clock: Clock,
    ctx: WorkspaceContext,
    candidate_id: uuid.UUID,
    user_id: uuid.UUID,
) -> str:
    """Return the raw token (callback data is ``fsv:<token>``, well under Telegram's 64 bytes)."""
    raw = secrets.token_urlsafe(16)
    db.add(
        FactSaveToken(
            id=new_id(),
            workspace_id=ctx.workspace_id,
            token_hash=hash_token(raw),
            candidate_id=candidate_id,
            user_id=user_id,
            expires_at=clock.now() + FACT_SAVE_TOKEN_TTL,
            used_at=None,
            created_at=clock.now(),
        )
    )
    db.flush()
    return raw


def consume(db: Session, clock: Clock, token_str: str, channel_user_id: str) -> FactSaveToken:
    """Validate, bind-check and mark the token used. Raises ``AppError`` otherwise.

    ``NOT_FOUND`` unknown token, ``APPROVAL_ALREADY_DECIDED`` replay, ``APPROVAL_EXPIRED`` too old,
    ``FORBIDDEN`` the Telegram account is not the user the token was issued to.
    """
    token_hash = hash_token(token_str)
    if db.get_bind().dialect.name == "postgresql":
        found = db.execute(
            text("SELECT id, workspace_id FROM public.resolve_fact_save_token_by_hash(:h)"),
            {"h": token_hash},
        ).first()
        if found is None:
            raise AppError("NOT_FOUND", reason="fact_save_token_not_found")
        set_tenant_context(db, found.workspace_id)
        token = db.get(FactSaveToken, found.id, with_for_update=True)
    else:  # pragma: no cover - the application is PostgreSQL only
        token = db.scalar(
            select(FactSaveToken).where(FactSaveToken.token_hash == token_hash).with_for_update()
        )
        if token is not None:
            set_tenant_context(db, token.workspace_id)
    if token is None:
        raise AppError("NOT_FOUND", reason="fact_save_token_not_found")
    if token.used_at is not None:
        raise AppError("APPROVAL_ALREADY_DECIDED", reason="token_already_used")
    if token.expires_at <= clock.now():
        raise AppError("APPROVAL_EXPIRED", reason="token_expired")
    resolved = ChannelLinkService.resolve_channel_user(
        db, channel="telegram", channel_user_id=channel_user_id
    )
    if resolved is None:
        raise AppError("FORBIDDEN", reason="unlinked_channel_user")
    user, workspace, _ = resolved
    if user.id != token.user_id or workspace.id != token.workspace_id:
        raise AppError("FORBIDDEN", reason="user_mismatch")
    token.used_at = clock.now()
    db.flush()
    return token
