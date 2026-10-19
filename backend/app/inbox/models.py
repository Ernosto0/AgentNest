"""Inbox tables (data-model.md §3.5): ``inbound_events``, ``conversations``, ``messages``,
``reply_drafts``.

Every tenant child references its parent through a composite foreign key
``(workspace_id, parent_id)`` (INV-01). ``inbound_events`` is the one table that may exist
before the workspace is known (an unknown receiving account), so its workspace and account
columns are nullable.
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
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, UUIDPrimaryKeyMixin

EVENT_TYPES = ("message", "echo", "reaction", "read", "postback", "other")
EVENT_STATUSES = ("received", "processed", "ignored", "failed")
# Why an event was stored but not processed (observability.md §4.1).
IGNORE_REASONS = ("UNKNOWN_ACCOUNT", "ACCOUNT_DISCONNECTED", "UNSUPPORTED_EVENT")


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


class InboundEvent(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "inbound_events"
    __table_args__ = (
        UniqueConstraint("dedup_key"),
        UniqueConstraint("workspace_id", "id"),
        ForeignKeyConstraint(
            ["workspace_id", "social_account_id"],
            ["social_accounts.workspace_id", "social_accounts.id"],
            ondelete="CASCADE",
        ),
        CheckConstraint(_in("provider_kind", ("mock", "meta")), name="provider_kind"),
        CheckConstraint(_in("event_type", EVENT_TYPES), name="event_type"),
        CheckConstraint(_in("status", EVENT_STATUSES), name="status"),
        CheckConstraint(
            f"ignore_reason IS NULL OR {_in('ignore_reason', IGNORE_REASONS)}",
            name="ignore_reason",
        ),
        Index("ix_inbound_events_status_received", "status", "received_at"),
        Index("ix_inbound_events_workspace_received", "workspace_id", "received_at"),
    )

    workspace_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE")
    )
    social_account_id: Mapped[uuid.UUID | None] = mapped_column()
    provider_kind: Mapped[str] = mapped_column(Text, nullable=False)
    dedup_key: Mapped[str] = mapped_column(Text, nullable=False)
    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    # The single webhook item (never the whole body). Nulled by the retention job after 30 days.
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="received")
    ignore_reason: Mapped[str | None] = mapped_column(Text)
    error_code: Mapped[str | None] = mapped_column(Text)
    correlation_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    is_simulated: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
