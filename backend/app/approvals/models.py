"""``approvals`` (data-model.md §3.4, ADR-014, state-machines.md §1).

An approval is bound to an exact subject version and payload (``payload_hash``). The payload
itself lives with the subject (e.g. ``owner_commands.resolution``); only its hash and a render
``summary`` are stored here.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, TimestampMixin, UUIDPrimaryKeyMixin, WorkspaceScopedMixin

APPROVAL_KINDS = ("confirmation", "authorization")
APPROVAL_STATUSES = ("pending", "approved", "rejected", "expired", "cancelled")
APPROVAL_ACTIONS = (
    "command.update_fact",
    "command.update_brand_voice",
    "command.cancel_content",
    "reply.send",
    "content.publish",
    "comments.approve",
    "content.prepare",
    "content.schedule",
    "content.cancel",
)
APPROVAL_SUBJECT_TYPES = ("owner_command", "reply_draft", "content_item", "agent_action")
DECISION_CHANNELS = ("web", "telegram", "policy")


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


class Approval(UUIDPrimaryKeyMixin, TimestampMixin, WorkspaceScopedMixin, Base):
    __tablename__ = "approvals"
    __table_args__ = (
        UniqueConstraint("workspace_id", "id"),
        CheckConstraint(_in("kind", APPROVAL_KINDS), name="kind"),
        CheckConstraint(_in("action", APPROVAL_ACTIONS), name="action"),
        CheckConstraint(_in("subject_type", APPROVAL_SUBJECT_TYPES), name="subject_type"),
        CheckConstraint(_in("status", APPROVAL_STATUSES), name="status"),
        CheckConstraint("subject_version >= 1", name="subject_version"),
        CheckConstraint("payload_hash ~ '^[0-9a-f]{64}$'", name="payload_hash"),
        CheckConstraint(
            f"decision_channel IS NULL OR {_in('decision_channel', DECISION_CHANNELS)}",
            name="decision_channel",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "operation_id"], ["operations.workspace_id", "operations.id"]
        ),
        # At most one pending approval per subject.
        Index(
            "uq_approvals_pending_subject",
            "workspace_id",
            "subject_type",
            "subject_id",
            unique=True,
            postgresql_where=text("status = 'pending'"),
        ),
        Index("ix_approvals_workspace_status_expires", "workspace_id", "status", "expires_at"),
        # The expiry sweep looks across workspaces.
        Index(
            "ix_approvals_pending_expires",
            "expires_at",
            postgresql_where=text("status = 'pending'"),
        ),
    )

    kind: Mapped[str] = mapped_column(Text, nullable=False)
    action: Mapped[str] = mapped_column(Text, nullable=False)
    subject_type: Mapped[str] = mapped_column(Text, nullable=False)
    subject_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    subject_version: Mapped[int] = mapped_column(Integer, nullable=False)
    payload_hash: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    required_permission: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="pending")
    requested_by_actor_type: Mapped[str] = mapped_column(Text, nullable=False)
    requested_by_actor_id: Mapped[str | None] = mapped_column(Text)
    decided_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decision_channel: Mapped[str | None] = mapped_column(Text)
    decision_note: Mapped[str | None] = mapped_column(Text)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    execute_before: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    operation_id: Mapped[uuid.UUID | None] = mapped_column()  # the one operation it authorised
    cancel_reason: Mapped[str | None] = mapped_column(Text)
    is_simulated: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
