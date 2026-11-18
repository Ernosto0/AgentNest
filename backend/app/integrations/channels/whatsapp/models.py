"""Global ingress deduplication ledger (no tenant or plaintext sender)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Index, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class WhatsAppWebhookEvent(Base):
    __tablename__ = "whatsapp_webhook_events"
    __table_args__ = (
        CheckConstraint("status IN ('processed', 'ignored', 'failed')", name="status"),
        Index("ix_whatsapp_webhook_events_received_at", "received_at"),
    )

    message_id: Mapped[str] = mapped_column(Text, primary_key=True)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    wa_id_hash: Mapped[str | None] = mapped_column(Text)
    error: Mapped[str | None] = mapped_column(Text)
