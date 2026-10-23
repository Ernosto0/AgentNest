"""Immutable report generations, content-free membership and source-retention gaps."""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKeyConstraint,
    Integer,
    Numeric,
    Text,
    UniqueConstraint,
)
from sqlalchemy import text as sql_text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, UUIDPrimaryKeyMixin, WorkspaceScopedMixin


class DailyReport(UUIDPrimaryKeyMixin, WorkspaceScopedMixin, Base):
    __tablename__ = "daily_reports"
    __table_args__ = (
        UniqueConstraint("workspace_id", "id"),
        UniqueConstraint("workspace_id", "local_date", "revision"),
    )

    local_date: Mapped[date] = mapped_column(Date, nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    evidence_complete: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    timezone: Mapped[str] = mapped_column(Text, nullable=False)
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    metrics: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=sql_text("'{}'::jsonb")
    )
    definitions_version: Mapped[str] = mapped_column(Text, nullable=False)
    has_simulated_data: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=sql_text("false")
    )
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ReportItem(UUIDPrimaryKeyMixin, WorkspaceScopedMixin, Base):
    """No FK to a source record: its membership must survive source retention."""

    __tablename__ = "report_items"
    __table_args__ = (
        UniqueConstraint("workspace_id", "id"),
        UniqueConstraint(
            "workspace_id",
            "report_id",
            "metric_key",
            "subject_type",
            "subject_id",
            name="uq_report_items_membership",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "report_id"],
            ["daily_reports.workspace_id", "daily_reports.id"],
            ondelete="CASCADE",
        ),
    )

    report_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    metric_key: Mapped[str] = mapped_column(Text, nullable=False)
    subject_type: Mapped[str] = mapped_column(Text, nullable=False)
    subject_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    occurred_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_simulated: Mapped[bool] = mapped_column(Boolean, nullable=False)
    link_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    measure: Mapped[Decimal | None] = mapped_column(Numeric)
    group_key: Mapped[str | None] = mapped_column(Text)


class ReportSourceGap(UUIDPrimaryKeyMixin, WorkspaceScopedMixin, Base):
    """An inclusive range where a metric's sources were deleted; no customer content."""

    __tablename__ = "report_source_gaps"
    __table_args__ = (
        UniqueConstraint("workspace_id", "id"),
        UniqueConstraint(
            "workspace_id", "metric_key", "start_at", "end_at", name="uq_report_source_gap_period"
        ),
    )

    metric_key: Mapped[str] = mapped_column(Text, nullable=False)
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
