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
