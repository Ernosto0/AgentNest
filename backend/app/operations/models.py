"""The external operations ledger (ADR-011, data-model.md §3.7).

Every external side effect is a row here **before** it happens, committed first (INV-15).
The row is the only thing a job may consult to learn whether the effect already happened, so
a retry reconciles instead of repeating (INV-05, INV-06). ``idempotency_key`` is unique:
``send_reply:{reply_draft_id}`` allows exactly one send per draft.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
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

OPERATION_TYPES = ("send_reply", "publish_content", "refresh_token")
OPERATION_STATUSES = (
    "pending",
    "in_progress",
    "succeeded",
    "retry_wait",
    "failed",
    "outcome_unknown",
    "cancelled",
)


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


class Operation(UUIDPrimaryKeyMixin, TimestampMixin, WorkspaceScopedMixin, Base):
    __tablename__ = "operations"
    __table_args__ = (
        UniqueConstraint("workspace_id", "id"),
        UniqueConstraint("workspace_id", "social_account_id", "id"),
        UniqueConstraint("idempotency_key"),
        ForeignKeyConstraint(
            ["workspace_id", "social_account_id"],
            ["social_accounts.workspace_id", "social_accounts.id"],
        ),
        CheckConstraint(_in("operation_type", OPERATION_TYPES), name="operation_type"),
        CheckConstraint(_in("status", OPERATION_STATUSES), name="status"),
        CheckConstraint(_in("provider_kind", ("mock", "meta")), name="provider_kind"),
        CheckConstraint("attempts >= 0", name="attempts"),
        Index("ix_operations_status", "status", "started_at"),
        Index("ix_operations_subject", "subject_type", "subject_id"),
        Index("ix_operations_account_status", "social_account_id", "status"),
    )

    operation_type: Mapped[str] = mapped_column(Text, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(Text, nullable=False)
    subject_type: Mapped[str] = mapped_column(Text, nullable=False)
    subject_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    social_account_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    provider_kind: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="pending")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("6"))
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deadline_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # What was sent, enough to recognise it later: {recipient_id, text_sha256}. Never the text.
    provider_ref: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    result: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    last_error_code: Mapped[str | None] = mapped_column(Text)
    last_error_detail: Mapped[str | None] = mapped_column(Text)
    correlation_id: Mapped[uuid.UUID | None] = mapped_column()
    is_simulated: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
