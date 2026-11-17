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


class WeeklyMetricOut(BaseModel):
    """One number of the missed-customer report. ``value`` is null when it cannot be known
    (after-hours numbers without a verified opening-hours fact), never a made-up zero."""

    key: str
    value: int | float | None
    previous_value: int | float | None  # the same number over the previous full week
    link: ReportLinkOut | None  # the records behind the number


class PriceInputOut(BaseModel):
    key: str
    label: str
    amount: str  # a decimal string in the estimate's currency
    unit: str | None


class EstimateOut(BaseModel):
    """The lira estimate and all of its inputs. ``amount`` is null unless ``status`` is ``ok``:
    ``hours_missing`` and ``no_verified_price`` mean counts only."""

    status: str  # ok | hours_missing | no_verified_price
    currency: str
    amount: str | None
    price_questions: int | None  # factor 1: after-hours price questions the assistant answered
    conversion_rate: str  # factor 2: a conservative planning rate, e.g. "0.05"
    median_price: str | None  # factor 3: the median of ``price_inputs``
    price_inputs: list[PriceInputOut]  # at most 20, cheapest first
    price_count: int  # how many verified prices the median is over; more than the inputs when cut


class MissedCustomerReportOut(BaseModel):
    week_start: date  # the local Monday
    week_end: date  # the local Sunday
    timezone: str
    period_start: datetime
    period_end: datetime
    generated_at: datetime
    is_partial: bool
    hours_available: bool
    # Simulated and mock-account records are never counted; the flag documents that.
    has_simulated_data: bool
    metrics: list[WeeklyMetricOut]
    estimate: EstimateOut
