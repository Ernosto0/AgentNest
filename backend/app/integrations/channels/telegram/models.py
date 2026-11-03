"""Database models for Telegram channel integration (ADR-012, INV-06)."""

from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, Index, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


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
