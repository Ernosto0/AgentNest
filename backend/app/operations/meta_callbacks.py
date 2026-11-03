"""Meta deauthorization and data-deletion callback service (ADR-025 §3.4, P8-05 / V-06).

Strictly verifies Meta signed_requests, handles idempotent deauthorization,
orchestrates customer/workspace erasure, records durable data_deletion_requests,
and exposes privacy-preserving confirmation status queries.
"""

import base64
import hashlib
import hmac
import json
import secrets
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent.models import AccountAgent
from app.audit.service import record
from app.core.clock import Clock
from app.core.config import Settings
from app.core.context import ActorRef, WorkspaceContext
from app.integrations.instagram.models import SocialAccount
from app.memory.models import CustomerIdentity
from app.operations.data_rights import erase_customer
from app.operations.models import DataDeletionRequest, DeletionTombstone

MAX_SIGNED_REQUEST_LEN = 16384


class InvalidSignedRequestError(Exception):
    """Raised when the signed_request format, payload, or algorithm is malformed."""


class InvalidSignatureError(Exception):
    """Raised when the HMAC-SHA256 signature does not match the app secret."""


def _base64url_decode(input_str: str) -> bytes:
    """Decodes a URL-safe base64 string, restoring stripped padding."""
    rem = len(input_str) % 4
    if rem > 0:
        input_str += "=" * (4 - rem)
    return base64.urlsafe_b64decode(input_str)


def parse_and_verify_signed_request(signed_request: str, secret: str) -> dict[str, Any]:
    """Strictly parses and verifies a Meta signed_request.

    Format: <encoded_sig>.<payload>
    """
    if not signed_request or len(signed_request) > MAX_SIGNED_REQUEST_LEN:
        raise InvalidSignedRequestError("signed_request is empty or exceeds bounded size")

    parts = signed_request.split(".", 1)
    if len(parts) != 2:
        raise InvalidSignedRequestError("signed_request must have exactly two parts")

    encoded_sig, payload_b64 = parts
    try:
        decoded_sig = _base64url_decode(encoded_sig)
    except Exception as exc:
        raise InvalidSignedRequestError("Failed to base64url decode signature") from exc

    if not secret:
        raise InvalidSignatureError("App secret is empty")

    expected_sig = hmac.new(
        secret.encode("utf-8"),
        payload_b64.encode("utf-8"),
        hashlib.sha256,
    ).digest()

    if not hmac.compare_digest(decoded_sig, expected_sig):
        raise InvalidSignatureError("Signature mismatch")

    try:
        payload_bytes = _base64url_decode(payload_b64)
        payload = json.loads(payload_bytes.decode("utf-8"))
    except Exception as exc:
        raise InvalidSignedRequestError("Failed to parse JSON payload") from exc

    if not isinstance(payload, dict):
        raise InvalidSignedRequestError("Payload must be a JSON object")

    algorithm = str(payload.get("algorithm", "")).upper()
    if algorithm != "HMAC-SHA256":
        raise InvalidSignedRequestError(f"Unsupported signature algorithm: {algorithm}")

    user_id = str(payload.get("user_id") or payload.get("app_scoped_user_id") or "")
    if not user_id:
        raise InvalidSignedRequestError("Payload is missing user_id")

    return payload


def verify_signed_request_with_settings(settings: Settings, signed_request: str) -> dict[str, Any]:
    """Verifies a signed_request attempting configured secrets."""
    meta_secret = settings.meta_app_secret.get_secret_value()
    mock_secret = settings.mock_instagram_app_secret.get_secret_value()

    # Try meta_app_secret first if configured
    if meta_secret:
        try:
            return parse_and_verify_signed_request(signed_request, meta_secret)
        except InvalidSignatureError:
            # If meta_secret failed and mock_secret is also configured, try fallback
            if mock_secret and settings.demo_tools_enabled:
                return parse_and_verify_signed_request(signed_request, mock_secret)
            raise

    # Fallback to mock secret if meta_app_secret is blank
    if mock_secret:
        return parse_and_verify_signed_request(signed_request, mock_secret)

    raise InvalidSignatureError("No valid app secret configured to verify signature")


def handle_deauthorization(
    db: Session,
    clock: Clock,
    settings: Settings,
    signed_request: str,
) -> dict[str, str]:
    """Processes a Meta deauthorization callback.

    Revokes social account credentials, fences automation, and emits audit records.
    """
    try:
        payload = verify_signed_request_with_settings(settings, signed_request)
    except (InvalidSignatureError, InvalidSignedRequestError) as exc:
        record(
            db,
            None,
            "webhook.signature_invalid",
            None,
            None,
            {"endpoint": "deauthorize", "error": str(exc)},
            clock=clock,
            actor=ActorRef(type="system", id="meta"),
        )
        db.commit()
        raise

    user_id = str(payload.get("user_id") or payload.get("app_scoped_user_id") or "")

    accounts = (
        db.execute(
            select(SocialAccount).where(
                SocialAccount.external_account_id == user_id,
                SocialAccount.status != "disconnected",
            )
        )
        .scalars()
        .all()
    )

    if accounts:
        for acc in accounts:
            acc.status = "disconnected"
            acc.token_ciphertext = None
            acc.capabilities = {}

            # Pause active account agent if one exists
            agent = db.execute(
                select(AccountAgent).where(
                    AccountAgent.workspace_id == acc.workspace_id,
                    AccountAgent.social_account_id == acc.id,
                )
            ).scalar_one_or_none()
            if agent:
                agent.state = "paused"

            record(
                db,
                None,
                "meta.deauthorized",
                "social_account",
                acc.id,
                {"social_account_id": str(acc.id), "external_account_id": user_id},
                clock=clock,
                actor=ActorRef(type="system", id="meta"),
                workspace_id=acc.workspace_id,
            )
            record(
                db,
                None,
                "social_account.disconnected",
                "social_account",
                acc.id,
                {"social_account_id": str(acc.id), "reason": "meta_deauthorized"},
                clock=clock,
                actor=ActorRef(type="system", id="meta"),
                workspace_id=acc.workspace_id,
            )
    else:
        # Unknown or already disconnected account: record system audit log without leaking state
        record(
            db,
            None,
            "meta.deauthorized",
            None,
            None,
            {"external_account_id": user_id, "status": "unknown_account"},
            clock=clock,
            actor=ActorRef(type="system", id="meta"),
        )

    db.commit()
    return {"status": "ok"}


def handle_data_deletion_request(
    db: Session,
    clock: Clock,
    settings: Settings,
    signed_request: str,
) -> dict[str, str]:
    """Processes a Meta data-deletion callback.

    Orchestrates erasure across customer identities or connected accounts,
    creates a durable data_deletion_requests record, and returns the confirmation URL.
    """
    try:
        payload = verify_signed_request_with_settings(settings, signed_request)
    except (InvalidSignatureError, InvalidSignedRequestError) as exc:
        record(
            db,
            None,
            "webhook.signature_invalid",
            None,
            None,
            {"endpoint": "data-deletion", "error": str(exc)},
            clock=clock,
            actor=ActorRef(type="system", id="meta"),
        )
        db.commit()
        raise

    user_id = str(payload.get("user_id") or payload.get("app_scoped_user_id") or "")

    # Replay / Idempotency handling: check if request already exists for this provider_user_id
    existing = (
        db.execute(
            select(DataDeletionRequest).where(
                DataDeletionRequest.provider == "meta",
                DataDeletionRequest.provider_user_id == user_id,
            )
        )
        .scalars()
        .first()
    )
    if existing:
        base_url = settings.app_base_url.rstrip("/")
        return {
            "url": f"{base_url}/api/v1/webhooks/meta/data-deletion/{existing.confirmation_code}",
            "confirmation_code": existing.confirmation_code,
        }

    confirmation_code = "del_" + secrets.token_urlsafe(24)
    target_workspace_id: uuid.UUID | None = None
    status = "completed"
    now = clock.now()
    completed_at: Any = now

    # 1. Check if user_id belongs to a connected SocialAccount (page owner)
    account = (
        db.execute(
            select(SocialAccount).where(
                SocialAccount.external_account_id == user_id,
            )
        )
        .scalars()
        .first()
    )

    if account:
        target_workspace_id = account.workspace_id
        account.status = "disconnected"
        account.token_ciphertext = None
        account.capabilities = {}

        tombstone = DeletionTombstone(
            workspace_id=target_workspace_id,
            entity_type="social_account",
            entity_id=user_id,
            purged_at=now,
            details={"provider": "meta", "reason": "data_deletion_request"},
        )
        db.add(tombstone)
    else:
        # 2. Check if user_id belongs to a CustomerIdentity (customer conversation)
        subject_hash = hashlib.sha256(user_id.encode("utf-8")).hexdigest()
        customer = (
            db.execute(
                select(CustomerIdentity).where(
                    CustomerIdentity.provider_subject_hash == subject_hash
                )
            )
            .scalars()
            .first()
        )

        if customer:
            target_workspace_id = customer.workspace_id
            ctx = WorkspaceContext(
                workspace_id=target_workspace_id,
                actor=ActorRef(type="system", id="meta"),
                role="owner",
                timezone="UTC",
                locale="en",
                is_demo=False,
            )
            erasure_res = erase_customer(
                db,
                clock,
                ctx,
                customer.id,
            )
            if erasure_res.get("status") == "redacted_reconciliation_pending":
                status = "in_progress"
                completed_at = None
            else:
                status = "completed"
                completed_at = now
        else:
            # 3. Unknown identity or already erased: write tombstone to fence future restores
            status = "not_found_or_already_erased"
            completed_at = now
            tombstone = DeletionTombstone(
                workspace_id=None,
                entity_type="meta_user",
                entity_id=user_id,
                purged_at=now,
                details={"provider": "meta", "reason": "data_deletion_unknown"},
            )
            db.add(tombstone)

    req = DataDeletionRequest(
        id=uuid.uuid4(),
        confirmation_code=confirmation_code,
        provider="meta",
        provider_user_id=user_id,
        status=status,
        workspace_id=target_workspace_id,
        requested_at=now,
        completed_at=completed_at,
        details={"initial_status": status},
    )
    db.add(req)

    record(
        db,
        None,
        "meta.data_deletion_requested",
        "data_deletion_request",
        req.id,
        {"confirmation_code": confirmation_code, "status": status},
        clock=clock,
        actor=ActorRef(type="system", id="meta"),
        workspace_id=target_workspace_id,
    )

    db.commit()

    base_url = settings.app_base_url.rstrip("/")
    return {
        "url": f"{base_url}/api/v1/webhooks/meta/data-deletion/{confirmation_code}",
        "confirmation_code": confirmation_code,
    }


def get_data_deletion_status(
    db: Session,
    clock: Clock,
    confirmation_code: str,
) -> dict[str, Any] | None:
    """Retrieves privacy-preserving deletion status for a confirmation code.

    Returns only confirmation_code, status, requested_at, completed_at.
    Never exposes usernames, external IDs, workspace names, or message text.
    """
    req = (
        db.execute(
            select(DataDeletionRequest).where(
                DataDeletionRequest.confirmation_code == confirmation_code
            )
        )
        .scalars()
        .first()
    )

    if not req:
        return None

    # If pending or in_progress, check if pending operations have completed
    if req.status in ("pending", "in_progress") and req.workspace_id:
        # Check operations in workspace
        from app.operations.models import Operation

        pending_ops = (
            db.execute(
                select(Operation).where(
                    Operation.workspace_id == req.workspace_id,
                    Operation.status.in_(("in_progress", "outcome_unknown")),
                )
            )
            .scalars()
            .first()
        )
        if not pending_ops:
            req.status = "completed"
            req.completed_at = clock.now()
            db.commit()

    return {
        "confirmation_code": req.confirmation_code,
        "status": req.status,
        "requested_at": req.requested_at.isoformat(),
        "completed_at": req.completed_at.isoformat() if req.completed_at else None,
    }
