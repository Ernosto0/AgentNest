"""Database models for Telegram channel integration (ADR-012, INV-06)."""

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, UUIDPrimaryKeyMixin, WorkspaceScopedMixin, workspace_unique_constraint


class TelegramUpdate(Base):
    """Ledger of received Telegram updates for deduplication (INV-06).

    Explicit global table (no workspace_id because deduplication occurs at ingress
    before tenant resolution).
    """

    __tablename__ = "telegram_updates"
    __table_args__ = (
        CheckConstraint(
            "status IN ('processed', 'ignored', 'failed')",
            name="ck_telegram_updates_status",
        ),
        Index("ix_telegram_updates_received_at", "received_at"),
        Index("ix_telegram_updates_channel_user_id", "channel_user_id"),
    )

    update_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="processed")
    channel_user_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)


class TelegramPendingMedia(UUIDPrimaryKeyMixin, WorkspaceScopedMixin, Base):
    """Persistent DB-backed cache for uncaptioned Telegram photos awaiting a follow-up."""

    __tablename__ = "telegram_pending_media"
    __table_args__ = (
        workspace_unique_constraint(),
        UniqueConstraint("workspace_id", "user_id", name="uq_telegram_pending_media_ws_user"),
        Index("ix_telegram_pending_media_expires_at", "expires_at"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    media_asset_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("media_assets.id", ondelete="CASCADE"), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
