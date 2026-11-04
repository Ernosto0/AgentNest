"""Action token service for owner channel single-use approval buttons (ADR-012, ADR-014, INV-16)."""

from __future__ import annotations

import hashlib
import secrets
import uuid

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.approvals.models import ActionToken, Approval
from app.core.clock import Clock
from app.core.context import WorkspaceContext
from app.core.db import set_tenant_context
from app.core.errors import AppError
from app.core.ids import new_id
from app.identity.channels import ChannelLinkService


def hash_action_token(raw_token: str) -> str:
    """Return SHA-256 hex digest of the raw action token string."""
    return hashlib.sha256(raw_token.strip().encode("utf-8")).hexdigest()


class ActionTokenService:
    """Service managing generation and consumption of single-use action tokens."""

    @staticmethod
    def create_action_token(
        db: Session,
        clock: Clock,
        ctx: WorkspaceContext,
        approval: Approval,
        decision: str,
        user_id: uuid.UUID,
    ) -> str:
        """Generate a cryptographically random single-use token bound to approval & user."""
        if decision not in ("approved", "rejected"):
            raise AppError("VALIDATION_FAILED", decision=decision)

        # 16 random bytes url-safe base64 (~22 chars)
        raw_token = secrets.token_urlsafe(16)
        token_hash = hash_action_token(raw_token)

        action_token = ActionToken(
            id=new_id(),
            workspace_id=ctx.workspace_id,
            token_hash=token_hash,
            approval_id=approval.id,
            decision=decision,
            user_id=user_id,
            payload_hash=approval.payload_hash,
            expires_at=approval.expires_at,
            used_at=None,
            created_at=clock.now(),
        )
        db.add(action_token)
        db.flush()
        return raw_token

    @staticmethod
    def consume_action_token(
        db: Session,
        clock: Clock,
        token_str: str,
        channel_user_id: str,
    ) -> tuple[Approval, ActionToken]:
        """Validate, bind-check and atomically consume an action token."""
        cleaned = token_str.strip()
        token_hash = hash_action_token(cleaned)
        now = clock.now()

        # 1. Resolve action token record under tenant isolation
        bind = db.get_bind()
        if bind.dialect.name == "postgresql":
            resolved = db.execute(
                text(
                    "SELECT id, workspace_id, approval_id, decision, user_id, "
                    "payload_hash, expires_at, used_at "
                    "FROM public.resolve_action_token_by_hash(:token_hash)"
                ),
                {"token_hash": token_hash},
            ).first()

            if resolved is None:
                raise AppError("NOT_FOUND", reason="action_token_not_found")

            set_tenant_context(db, resolved.workspace_id)
            token_record = db.get(ActionToken, resolved.id, with_for_update=True)
        else:
            token_record = db.scalar(
                select(ActionToken).where(ActionToken.token_hash == token_hash).with_for_update()
            )
            if token_record is None:
                raise AppError("NOT_FOUND", reason="action_token_not_found")
            set_tenant_context(db, token_record.workspace_id)

        if token_record is None:
            raise AppError("NOT_FOUND", reason="action_token_not_found")

        # 2. Check if already used (INV-16 single-use guarantee)
        if token_record.used_at is not None:
            raise AppError("APPROVAL_ALREADY_DECIDED", reason="token_already_used")

        # 3. Check expiry
        if token_record.expires_at <= now:
            raise AppError("APPROVAL_EXPIRED", reason="token_expired")

        # 4. Verify channel_user_id resolves to the token's bound user_id (wrong user protection)
        resolved_channel = ChannelLinkService.resolve_channel_user(
            db, channel="telegram", channel_user_id=channel_user_id
        )
        if resolved_channel is None:
            raise AppError("FORBIDDEN", reason="unlinked_channel_user")

        channel_user, channel_workspace, _ = resolved_channel
        if (
            channel_user.id != token_record.user_id
            or channel_workspace.id != token_record.workspace_id
        ):
            raise AppError("FORBIDDEN", reason="user_mismatch")

        # 5. Verify the approval entity exists and is in pending state
        approval = db.get(Approval, token_record.approval_id, with_for_update=True)
        if approval is None:
            raise AppError("NOT_FOUND", reason="approval_not_found")

        if approval.status != "pending":
            if approval.status in ("approved", "rejected"):
                raise AppError("APPROVAL_ALREADY_DECIDED", reason="approval_already_decided")
            elif approval.status == "expired":
                raise AppError("APPROVAL_EXPIRED", reason="approval_expired")
            else:
                raise AppError("CONFLICT_STATE", reason=f"approval_{approval.status}")

        # 6. Atomically mark action token used
        token_record.used_at = now
        db.flush()

        return approval, token_record


# Module-level aliases
create_action_token = ActionTokenService.create_action_token
consume_action_token = ActionTokenService.consume_action_token
