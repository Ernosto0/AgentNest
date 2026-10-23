"""Response and request models of the report routes (api-design.md section 2.8)."""

import datetime as dt
import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict


class ReportLinkOut(BaseModel):
    """Where something leads: an API path and/or a frontend route."""

    api: str | None
    route: str | None


class MetricOut(BaseModel):
    key: str
    value: int | float | None
    kind: str  # period | snapshot
    section: str
    # ``pending_approvals_now`` only: the count per approval action.
    breakdown: dict[str, int] | None
    link: ReportLinkOut
    screen_link: ReportLinkOut | None


class SummarySectionOut(BaseModel):
    section: str
    title: str
    lines: list[str]


class SummaryOut(BaseModel):
    empty: bool
    text: str
    sections: list[SummarySectionOut]


class DailyReportOut(BaseModel):
    snapshot_id: uuid.UUID | None
    evidence_complete: bool
    local_date: date
    timezone: str
    period_start: datetime
    period_end: datetime
    generated_at: datetime
    is_partial: bool
    definitions_version: str
    has_simulated_data: bool
    metrics: list[MetricOut]
    summary: SummaryOut


class GenerateReportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    date: dt.date


class MetricItemOut(BaseModel):
    kind: str
    id: uuid.UUID
    label: str
    occurred_at: datetime | None
    is_simulated: bool
    # Original response duration in minutes; round the aggregated median, not each measure.
    measure: float | None
    link: ReportLinkOut | None


class MetricItemsOut(BaseModel):
    snapshot_id: uuid.UUID | None
    key: str
    value: int | float | None
    items: list[MetricItemOut]
    next_cursor: str | None
