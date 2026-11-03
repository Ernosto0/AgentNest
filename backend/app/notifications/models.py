"""``notifications`` (data-model.md §3.8): in-app messages for one recipient.

A pending (unread) notification with the same ``dedup_key`` for the same recipient is never
created twice; once read, the same event may notify again.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, TimestampMixin, UUIDPrimaryKeyMixin, WorkspaceScopedMixin

SEVERITIES = ("info", "attention", "critical")


class Notification(UUIDPrimaryKeyMixin, TimestampMixin, WorkspaceScopedMixin, Base):
    __tablename__ = "notifications"
    __table_args__ = (
        UniqueConstraint("workspace_id", "id"),
        CheckConstraint("severity IN ('info', 'attention', 'critical')", name="severity"),
        Index(
            "uq_notifications_unread_dedup",
            "recipient_user_id",
            "dedup_key",
            unique=True,
            postgresql_where=text("read_at IS NULL AND dedup_key IS NOT NULL"),
        ),
        Index(
            "ix_notifications_recipient_created", "workspace_id", "recipient_user_id", "created_at"
        ),
    )

    recipient_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    type: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(Text, nullable=False, server_default="info")
    params: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default="{}")
    subject_type: Mapped[str | None] = mapped_column(Text)
    subject_id: Mapped[uuid.UUID | None] = mapped_column()
    dedup_key: Mapped[str | None] = mapped_column(Text)
    is_simulated: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


DELIVERY_CHANNELS = ("web", "telegram")
DELIVERY_STATUSES = ("pending", "delivered", "failed", "skipped_quiet_hours")


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


class NotificationDelivery(UUIDPrimaryKeyMixin, TimestampMixin, WorkspaceScopedMixin, Base):
    """``notification_deliveries``: per-channel external delivery ledger (ADR-012, Phase 9)."""

    __tablename__ = "notification_deliveries"
    __table_args__ = (
        UniqueConstraint("workspace_id", "id"),
        CheckConstraint(_in("channel", DELIVERY_CHANNELS), name="channel"),
        CheckConstraint(_in("status", DELIVERY_STATUSES), name="status"),
        Index("ix_notification_deliveries_notification", "notification_id"),
        Index("ix_notification_deliveries_recipient", "workspace_id", "recipient_user_id"),
        Index("ix_notification_deliveries_status", "status"),
        Index("ix_notification_deliveries_pending", "status", "created_at"),
    )

    notification_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("notifications.id", ondelete="CASCADE"), nullable=False
    )
    recipient_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    channel: Mapped[str] = mapped_column(Text, nullable=False)
    channel_link_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("channel_links.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="pending")
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    last_error: Mapped[str | None] = mapped_column(Text)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
