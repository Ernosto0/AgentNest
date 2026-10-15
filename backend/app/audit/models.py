"""``audit_logs`` (data-model.md §3.2).

RULE: INSERT-ONLY. No code path may update or delete rows of this table (INV-12, INV-17).
In production the application database role additionally has no UPDATE/DELETE privilege
(Phase 8). ``workspace_id`` is deliberately not a foreign key: it is NULL for system-level
events, and audit rows must survive workspace deletion without being rewritten.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, CheckConstraint, DateTime, Index, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, UUIDPrimaryKeyMixin


class AuditLog(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "audit_logs"
    __table_args__ = (
        CheckConstraint("actor_type IN ('user', 'system', 'agent', 'provider')", name="actor_type"),
        Index("ix_audit_logs_workspace_id_occurred_at", "workspace_id", text("occurred_at DESC")),
        Index(
            "ix_audit_logs_workspace_id_action_occurred_at",
            "workspace_id",
            "action",
            text("occurred_at DESC"),
        ),
        Index("ix_audit_logs_correlation_id", "correlation_id"),
    )

    workspace_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    actor_type: Mapped[str] = mapped_column(Text, nullable=False)
    actor_id: Mapped[str | None] = mapped_column(Text)
    action: Mapped[str] = mapped_column(Text, nullable=False)
    resource_type: Mapped[str | None] = mapped_column(Text)
    resource_id: Mapped[uuid.UUID | None] = mapped_column()
    correlation_id: Mapped[uuid.UUID | None] = mapped_column()
    is_simulated: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    # Column is named "metadata"; the attribute cannot be, because Base.metadata is taken.
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
