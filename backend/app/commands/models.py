"""``owner_commands`` (data-model.md §3.4, state-machines.md §3)."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, TimestampMixin, UUIDPrimaryKeyMixin, WorkspaceScopedMixin

COMMAND_CHANNELS = ("web", "telegram")
COMMAND_STATUSES = (
    "interpreting",
    "needs_clarification",
    "awaiting_confirmation",
    "executing",
    "completed",
    "unsupported",
    "failed",
    "cancelled",
    "expired",
)
MAX_COMMAND_CHARS = 1000


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


class OwnerCommand(UUIDPrimaryKeyMixin, TimestampMixin, WorkspaceScopedMixin, Base):
    __tablename__ = "owner_commands"
    __table_args__ = (
        UniqueConstraint("workspace_id", "id"),
        UniqueConstraint("user_id", "client_request_id"),
        ForeignKeyConstraint(
            ["workspace_id", "approval_id"],
            ["approvals.workspace_id", "approvals.id"],
        ),
        ForeignKeyConstraint(
            ["workspace_id", "agent_run_id"],
            ["agent_runs.workspace_id", "agent_runs.id"],
        ),
        CheckConstraint(_in("channel", COMMAND_CHANNELS), name="channel"),
        CheckConstraint(_in("status", COMMAND_STATUSES), name="status"),
        CheckConstraint(f"char_length(raw_text) <= {MAX_COMMAND_CHARS}", name="raw_text"),
        Index("ix_owner_commands_user_created", "workspace_id", "user_id", "created_at"),
        Index("ix_owner_commands_waiting_expires", "status", "expires_at"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    channel: Mapped[str] = mapped_column(Text, nullable=False)
    client_request_id: Mapped[str] = mapped_column(Text, nullable=False)
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    command_type: Mapped[str | None] = mapped_column(Text)
    interpreted: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    resolution: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    clarification: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    result: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    error_code: Mapped[str | None] = mapped_column(Text)
    approval_id: Mapped[uuid.UUID | None] = mapped_column()
    agent_run_id: Mapped[uuid.UUID | None] = mapped_column()
    correlation_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
