"""Owner channel linking service (ADR-012, Phase 9 Session 01 / P9-01).

Manages identity linking between AgentNest users/workspaces and external messaging channels
(such as Telegram). Generates single-use 15-minute alphanumeric codes and binds external
channel user IDs to workspace memberships.
"""

import hashlib
import secrets
import string
import uuid
from datetime import datetime, timedelta

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.audit import service as audit_service
from app.core.clock import Clock
from app.core.context import ActorRef, WorkspaceContext
from app.core.db import set_tenant_context
from app.core.errors import AppError
from app.core.ids import new_id
from app.identity.models import (
    CHANNEL_TYPES,
    ChannelLink,
    ChannelLinkCode,
    User,
    Workspace,
)

MAX_ACTIVE_LINK_CODES = 3
LINK_CODE_EXPIRY_MINUTES = 15
LINK_CODE_LENGTH = 8
CODE_ALPHABET = string.ascii_uppercase + string.digits


def hash_link_code(code: str) -> str:
    """Return SHA-256 hex digest of the normalized uppercase code."""
    return hashlib.sha256(code.strip().upper().encode("utf-8")).hexdigest()


class ChannelLinkService:
    """Service encapsulating owner channel linking and unlinking flows."""

    @staticmethod
    def generate_link_code(
        db: Session,
        clock: Clock,
        ctx: WorkspaceContext,
        channel: str = "telegram",
    ) -> tuple[str, datetime]:
        """Generate a cryptographically secure 8-character link code for the current user.

        Throttled to MAX_ACTIVE_LINK_CODES (3) active codes per user in this workspace.
        """
        if channel not in CHANNEL_TYPES:
            raise AppError(
                "VALIDATION_FAILED",
                channel=channel,
                supported=list(CHANNEL_TYPES),
            )

        if ctx.actor.type != "user" or not ctx.actor.id:
            raise AppError("FORBIDDEN")

        user_id = uuid.UUID(ctx.actor.id)
        now = clock.now()

        # Check throttle: count active (unused & unexpired) codes
        active_codes_count = (
            db.scalar(
                select(func.count(ChannelLinkCode.id)).where(
                    ChannelLinkCode.workspace_id == ctx.workspace_id,
                    ChannelLinkCode.user_id == user_id,
                    ChannelLinkCode.channel == channel,
                    ChannelLinkCode.used_at.is_(None),
                    ChannelLinkCode.expires_at > now,
                )
            )
            or 0
        )

        if active_codes_count >= MAX_ACTIVE_LINK_CODES:
            raise AppError("TOO_MANY_ACTIVE_CODES", limit=MAX_ACTIVE_LINK_CODES)

        # Generate 8-character uppercase alphanumeric code
        raw_code = "".join(secrets.choice(CODE_ALPHABET) for _ in range(LINK_CODE_LENGTH))
        code_hash = hash_link_code(raw_code)
        expires_at = now + timedelta(minutes=LINK_CODE_EXPIRY_MINUTES)

        link_code = ChannelLinkCode(
            id=new_id(),
            workspace_id=ctx.workspace_id,
            user_id=user_id,
            channel=channel,
            code_hash=code_hash,
            expires_at=expires_at,
            used_at=None,
            created_at=now,
        )
        db.add(link_code)
        db.flush()

        audit_service.record(
            db,
            ctx=ctx,
            action="channel_link.code_generated",
            resource_type="channel_link_code",
            resource_id=link_code.id,
            metadata={
                "channel": channel,
                "actor_user_id": str(user_id),
                "expires_at": expires_at.isoformat(),
            },
            clock=clock,
        )

        return raw_code, expires_at

    @staticmethod
    def redeem_link_code(
        db: Session,
        clock: Clock,
        channel: str,
        channel_user_id: str,
        channel_chat_id: str,
        raw_code: str,
        channel_username: str | None = None,
    ) -> ChannelLink:
        """Redeem a link code from a messaging platform bot command (/link <code>).

        Verifies validity, marks used, unlinks any superseded active link for this channel
        identity, creates an active ChannelLink, and logs audit events.
        """
        if channel not in CHANNEL_TYPES:
            raise AppError(
                "VALIDATION_FAILED",
                channel=channel,
                supported=list(CHANNEL_TYPES),
            )

        cleaned_code = raw_code.strip().upper()
        if len(cleaned_code) != LINK_CODE_LENGTH or not cleaned_code.isalnum():
            raise AppError("LINK_CODE_INVALID")

        code_hash = hash_link_code(cleaned_code)
        now = clock.now()

        # Resolve code under tenant RLS
        bind = db.get_bind()
        if bind.dialect.name == "postgresql":
            resolved = db.execute(
                text(
                    "SELECT id, workspace_id, user_id, channel, expires_at, used_at "
                    "FROM public.resolve_channel_link_code_by_hash(:channel, :code_hash)"
                ),
                {"channel": channel, "code_hash": code_hash},
            ).first()

            if resolved is None:
                raise AppError("LINK_CODE_INVALID")

            set_tenant_context(db, resolved.workspace_id)
            code_record = db.get(ChannelLinkCode, resolved.id)
        else:
            code_record = db.scalar(
                select(ChannelLinkCode).where(
                    ChannelLinkCode.channel == channel,
                    ChannelLinkCode.code_hash == code_hash,
                )
            )
            if code_record is None:
                raise AppError("LINK_CODE_INVALID")
            set_tenant_context(db, code_record.workspace_id)

        if code_record is None:
            raise AppError("LINK_CODE_INVALID")

        if code_record.used_at is not None:
            raise AppError("LINK_CODE_USED")

        if code_record.expires_at <= now:
            raise AppError("LINK_CODE_EXPIRED")

        # Mark code as used
        code_record.used_at = now

        target_workspace_id = code_record.workspace_id
        target_user_id = code_record.user_id

        # 1. Unlink any existing active link for this channel identity across all workspaces
        if bind.dialect.name == "postgresql":
            existing_identity_link = db.execute(
                text(
                    "SELECT id, workspace_id, user_id "
                    "FROM public.resolve_channel_link_by_channel_user(:channel, :channel_user_id)"
                ),
                {"channel": channel, "channel_user_id": channel_user_id},
            ).first()

            if existing_identity_link is not None:
                set_tenant_context(db, existing_identity_link.workspace_id)
                link_to_unlink = db.get(ChannelLink, existing_identity_link.id)
                if link_to_unlink and link_to_unlink.status == "active":
                    link_to_unlink.status = "unlinked"
                    link_to_unlink.unlinked_at = now
                    audit_service.record(
                        db,
                        ctx=None,
                        workspace_id=existing_identity_link.workspace_id,
                        actor=ActorRef.user(existing_identity_link.user_id),
                        action="channel_link.unlinked",
                        resource_type="channel_link",
                        resource_id=link_to_unlink.id,
                        metadata={
                            "channel": channel,
                            "user_id": str(existing_identity_link.user_id),
                            "channel_user_id": channel_user_id,
                            "initiated_by": "bot",
                        },
                        clock=clock,
                    )
        else:
            existing_links = db.scalars(
                select(ChannelLink).where(
                    ChannelLink.channel == channel,
                    ChannelLink.channel_user_id == channel_user_id,
                    ChannelLink.status == "active",
                )
            ).all()
            for ex in existing_links:
                ex.status = "unlinked"
                ex.unlinked_at = now
                audit_service.record(
                    db,
                    ctx=None,
                    workspace_id=ex.workspace_id,
                    actor=ActorRef.user(ex.user_id),
                    action="channel_link.unlinked",
                    resource_type="channel_link",
                    resource_id=ex.id,
                    metadata={
                        "channel": channel,
                        "user_id": str(ex.user_id),
                        "channel_user_id": channel_user_id,
                        "initiated_by": "bot",
                    },
                    clock=clock,
                )

        # 2. Reset context to target workspace and unlink any previous active link for this user
        set_tenant_context(db, target_workspace_id)
        existing_user_links = db.scalars(
            select(ChannelLink).where(
                ChannelLink.workspace_id == target_workspace_id,
                ChannelLink.user_id == target_user_id,
                ChannelLink.channel == channel,
                ChannelLink.status == "active",
            )
        ).all()
        for ex in existing_user_links:
            ex.status = "unlinked"
            ex.unlinked_at = now
            audit_service.record(
                db,
                ctx=None,
                workspace_id=target_workspace_id,
                actor=ActorRef.user(target_user_id),
                action="channel_link.unlinked",
                resource_type="channel_link",
                resource_id=ex.id,
                metadata={
                    "channel": channel,
                    "user_id": str(target_user_id),
                    "channel_user_id": ex.channel_user_id,
                    "initiated_by": "bot",
                },
                clock=clock,
            )

        # 3. Create active ChannelLink
        new_link = ChannelLink(
            id=new_id(),
            workspace_id=target_workspace_id,
            user_id=target_user_id,
            channel=channel,
            channel_user_id=channel_user_id,
            channel_chat_id=channel_chat_id,
            channel_username=channel_username,
            status="active",
            linked_at=now,
            unlinked_at=None,
        )
        db.add(new_link)
        db.flush()

        audit_service.record(
            db,
            ctx=None,
            workspace_id=target_workspace_id,
            actor=ActorRef.user(target_user_id),
            action="channel_link.created",
            resource_type="channel_link",
            resource_id=new_link.id,
            metadata={
                "channel": channel,
                "user_id": str(target_user_id),
                "channel_user_id": channel_user_id,
                "channel_username": channel_username,
            },
            clock=clock,
        )

        return new_link

    @staticmethod
    def unlink_by_user(
        db: Session,
        clock: Clock,
        ctx: WorkspaceContext,
        channel_link_id: uuid.UUID,
    ) -> None:
        """Unlink a channel from the web settings interface."""
        link = db.scalar(
            select(ChannelLink).where(
                ChannelLink.id == channel_link_id,
                ChannelLink.workspace_id == ctx.workspace_id,
            )
        )
        if link is None or link.status != "active":
            raise AppError("CHANNEL_LINK_NOT_FOUND")

        # Authorization: Must be the link's user or have owner/manager role
        is_link_owner = ctx.actor.id is not None and uuid.UUID(ctx.actor.id) == link.user_id
        is_elevated = ctx.role in ("owner", "manager")
        if not (is_link_owner or is_elevated):
            raise AppError("FORBIDDEN")

        now = clock.now()
        link.status = "unlinked"
        link.unlinked_at = now
        db.flush()

        audit_service.record(
            db,
            ctx=ctx,
            action="channel_link.unlinked",
            resource_type="channel_link",
            resource_id=link.id,
            metadata={
                "channel": link.channel,
                "user_id": str(link.user_id),
                "channel_user_id": link.channel_user_id,
                "initiated_by": "web",
            },
            clock=clock,
        )

    @staticmethod
    def unlink_by_channel(
        db: Session,
        clock: Clock,
        channel: str,
        channel_user_id: str,
    ) -> None:
        """Unlink when the owner sends /unlink in the bot."""
        bind = db.get_bind()
        now = clock.now()

        if bind.dialect.name == "postgresql":
            resolved = db.execute(
                text(
                    "SELECT id, workspace_id, user_id "
                    "FROM public.resolve_channel_link_by_channel_user(:channel, :channel_user_id)"
                ),
                {"channel": channel, "channel_user_id": channel_user_id},
            ).first()

            if resolved is None:
                return

            set_tenant_context(db, resolved.workspace_id)
            link = db.get(ChannelLink, resolved.id)
        else:
            link = db.scalar(
                select(ChannelLink).where(
                    ChannelLink.channel == channel,
                    ChannelLink.channel_user_id == channel_user_id,
                    ChannelLink.status == "active",
                )
            )
            if link is not None:
                set_tenant_context(db, link.workspace_id)

        if link is None or link.status != "active":
            return

        link.status = "unlinked"
        link.unlinked_at = now
        db.flush()

        audit_service.record(
            db,
            ctx=None,
            workspace_id=link.workspace_id,
            actor=ActorRef.user(link.user_id),
            action="channel_link.unlinked",
            resource_type="channel_link",
            resource_id=link.id,
            metadata={
                "channel": channel,
                "user_id": str(link.user_id),
                "channel_user_id": channel_user_id,
                "initiated_by": "bot",
            },
            clock=clock,
        )

    @staticmethod
    def resolve_channel_user(
        db: Session,
        channel: str,
        channel_user_id: str,
    ) -> tuple[User, Workspace, ChannelLink] | None:
        """Resolve incoming webhook author to user, workspace, and active channel link."""
        bind = db.get_bind()
        if bind.dialect.name == "postgresql":
            row = db.execute(
                text(
                    "SELECT id, workspace_id, user_id "
                    "FROM public.resolve_channel_link_by_channel_user(:channel, :channel_user_id)"
                ),
                {"channel": channel, "channel_user_id": channel_user_id},
            ).first()

            if row is None:
                return None

            set_tenant_context(db, row.workspace_id)
            link = db.get(ChannelLink, row.id)
            user = db.get(User, row.user_id)
            workspace = db.get(Workspace, row.workspace_id)
        else:
            link = db.scalar(
                select(ChannelLink).where(
                    ChannelLink.channel == channel,
                    ChannelLink.channel_user_id == channel_user_id,
                    ChannelLink.status == "active",
                )
            )
            if link is None:
                return None

            set_tenant_context(db, link.workspace_id)
            user = db.get(User, link.user_id)
            workspace = db.get(Workspace, link.workspace_id)

        if user is None or workspace is None or link is None or link.status != "active":
            return None

        return user, workspace, link

    @staticmethod
    def list_links_for_user(
        db: Session,
        ctx: WorkspaceContext,
        channel: str | None = None,
    ) -> list[ChannelLink]:
        """List active channel links for the current user in this workspace."""
        if ctx.actor.type != "user" or not ctx.actor.id:
            return []
        user_id = uuid.UUID(ctx.actor.id)
        stmt = (
            select(ChannelLink)
            .where(
                ChannelLink.workspace_id == ctx.workspace_id,
                ChannelLink.user_id == user_id,
                ChannelLink.status == "active",
            )
            .order_by(ChannelLink.linked_at.desc())
        )
        if channel is not None:
            stmt = stmt.where(ChannelLink.channel == channel)
        return list(db.scalars(stmt).all())


# Module-level aliases
generate_link_code = ChannelLinkService.generate_link_code
redeem_link_code = ChannelLinkService.redeem_link_code
unlink_by_user = ChannelLinkService.unlink_by_user
unlink_by_channel = ChannelLinkService.unlink_by_channel
resolve_channel_user = ChannelLinkService.resolve_channel_user
list_links_for_user = ChannelLinkService.list_links_for_user
