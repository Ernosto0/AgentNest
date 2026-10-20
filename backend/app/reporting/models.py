"""``daily_reports`` (data-model.md section 3.8).

One row per workspace and local date. Regeneration overwrites it: the previous value is not
needed because the records are the source (INV-08).
"""

from datetime import date, datetime
from typing import Any

from sqlalchemy import Boolean, Date, DateTime, Text, UniqueConstraint
from sqlalchemy import text as sql_text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, UUIDPrimaryKeyMixin, WorkspaceScopedMixin


class DailyReport(UUIDPrimaryKeyMixin, WorkspaceScopedMixin, Base):
    __tablename__ = "daily_reports"
    __table_args__ = (
        UniqueConstraint("workspace_id", "id"),
        UniqueConstraint("workspace_id", "local_date"),
    )

    local_date: Mapped[date] = mapped_column(Date, nullable=False)
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
