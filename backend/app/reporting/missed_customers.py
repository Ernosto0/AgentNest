"""The weekly missed-customer report (D-03): what the assistant saved the owner, in lira.

A week is a **local** Monday 00:00 to the next Monday 00:00 in the workspace timezone (INV-19);
the current week is partial and ends now. The numbers are SQL aggregations over real persisted
messages and drafts (``weekly_sources``); simulated and mock-account records never count (INV-09).
No language model is involved (INV-08): the opening hours and the prices come only from usable,
verified facts.

The lira figure is an **estimate with its basis**, never a bare number::

    estimate = after-hours price questions the assistant answered
               x CONVERSION_RATE
               x median of the verified TRY prices

It exists only when the workspace has a verified opening-hours fact (otherwise "after hours" is
unknown) and at least one verified price in lira. Without them the report shows counts only and
says why. The rate is deliberately conservative and shown next to the result.

Nothing here commits; the caller does.
"""

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import ROUND_DOWN, Decimal, InvalidOperation
from statistics import median
from typing import Any, Literal

from sqlalchemy.orm import Session

from app.core.clock import Clock
from app.core.context import WorkspaceContext
from app.core.errors import AppError
from app.core.i18n import normalize_locale
from app.notifications import service as notifications
from app.reporting import drilldown
from app.reporting.metrics import compute_metric
from app.reporting.periods import day_bounds, local_date_of
from app.reporting.weekly_sources import (
    WEEKLY_BY_KEY,
    WEEKLY_DEFINITIONS,
    hours_fact,
    usable_facts,
)

MISSED_CUSTOMERS_READY = "report.missed_customers_ready"

# The share of after-hours price questions that would have become a paying customer. A
# deliberately conservative planning figure, not a measurement: 5 in 100. It is shown in the
# report beside every lira amount, so the owner can judge it. Change it here only, with the docs.
CONVERSION_RATE = Decimal("0.05")
ESTIMATE_CURRENCY = "TRY"
CENTS = Decimal("0.01")
MAX_PRICE_INPUTS = 20
PRICE_CATEGORY = "pricing"

# The metrics whose value is unknown (not zero) when there is no verified opening-hours fact.
NEEDS_HOURS = frozenset({"after_hours_dms", "after_hours_price_answers"})

EstimateStatus = Literal["ok", "hours_missing", "no_verified_price"]


@dataclass(frozen=True)
class WeeklyMetric:
    key: str
    value: int | float | None
    previous_value: int | float | None  # the same metric over the previous full week


@dataclass(frozen=True)
class PriceInput:
    key: str
    label: dict[str, Any]
    amount: Decimal
    unit: str | None


@dataclass(frozen=True)
class Estimate:
    """The lira estimate and every input of its formula. ``amount`` is None unless ``ok``."""

    status: EstimateStatus
    currency: str
    amount: Decimal | None
    price_questions: int | None  # after-hours price questions answered (the first factor)
    conversion_rate: Decimal  # the second factor
    median_price: Decimal | None  # the third factor, from ``price_inputs``
    price_inputs: list[PriceInput] = field(
        default_factory=list
    )  # at most MAX_PRICE_INPUTS, cheapest first
    price_count: int = (
        0  # how many verified prices the median is over (may exceed the inputs shown)
    )


@dataclass(frozen=True)
class MissedCustomerReport:
    week_start: date  # the local Monday
    week_end: date  # the local Sunday (inclusive)
    timezone: str
    period_start: datetime
    period_end: datetime
    generated_at: datetime
    is_partial: bool
    hours_available: bool
    metrics: list[WeeklyMetric]
    estimate: Estimate

    def value(self, key: str) -> int | float | None:
        return next(m.value for m in self.metrics if m.key == key)

    @property
    def empty(self) -> bool:
        """Nothing to tell: no metric of this week is above zero."""
        return not any(isinstance(m.value, int | float) and m.value > 0 for m in self.metrics)


def week_start_of(day: date) -> date:
    """The Monday of the week that contains ``day``."""
    return day - timedelta(days=day.weekday())


def week_bounds(week_start: date, timezone: str) -> tuple[datetime, datetime]:
    """``[start, end)`` in UTC of the local week from ``week_start`` (a 167 or 169 hour week
    when it contains a clock change)."""
    return (
        day_bounds(week_start, timezone)[0],
        day_bounds(week_start + timedelta(days=7), timezone)[0],
    )


def previous_full_week(now: datetime, timezone: str) -> date:
    """The Monday of the last week that has ended, in the workspace timezone."""
    return week_start_of(local_date_of(now, timezone)) - timedelta(days=7)


def check_week(ctx: WorkspaceContext, week_start: date, now: datetime) -> date:
    """The Monday of ``week_start``'s week; a week that has not begun is a validation error."""
    monday = week_start_of(week_start)
    if monday > week_start_of(local_date_of(now, ctx.timezone)):
        raise AppError(
            "VALIDATION_FAILED",
            errors=[{"field": "week_start", "code": "in_future", "params": {}}],
        )
    return monday


def _price_inputs(session: Session, ctx: WorkspaceContext, now: datetime) -> list[PriceInput]:
    """The verified, in-window, uncontested prices in lira, cheapest first."""
    found: list[PriceInput] = []
    for fact in usable_facts(session, ctx, now):
        if fact.category != PRICE_CATEGORY or fact.value_type != "money":
            continue
        if fact.value.get("currency") != ESTIMATE_CURRENCY:
            continue
        try:
            amount = Decimal(str(fact.value.get("amount")))
        except InvalidOperation:
            continue
        if not amount.is_finite() or amount <= 0:
            continue
        unit = fact.value.get("unit")
        found.append(PriceInput(fact.key, dict(fact.label), amount, unit if unit else None))
    return sorted(found, key=lambda p: (p.amount, p.key))


def build_estimate(
    price_questions: int | None, hours_available: bool, prices: list[PriceInput]
) -> Estimate:
    """``price_questions x CONVERSION_RATE x median price``, or counts only (see the module)."""
    shown = prices[:MAX_PRICE_INPUTS]

    def estimate(
        status: EstimateStatus, amount: Decimal | None, middle: Decimal | None
    ) -> Estimate:
        return Estimate(
            status,
            ESTIMATE_CURRENCY,
            amount,
            price_questions,
            CONVERSION_RATE,
            middle,
            shown,
            len(prices),
        )

    if not hours_available or price_questions is None:
        return estimate("hours_missing", None, None)
    if not prices:
        return estimate("no_verified_price", None, None)
    middle = Decimal(median([p.amount for p in prices])).quantize(CENTS)
    amount = (Decimal(price_questions) * CONVERSION_RATE * middle).quantize(
        CENTS, rounding=ROUND_DOWN
    )
    return estimate("ok", amount, middle)


def build_report(
    session: Session, clock: Clock, ctx: WorkspaceContext, week_start: date
) -> MissedCustomerReport:
    """The report of the local week of ``week_start``, live (the current week ends now)."""
    now = clock.now()
    monday = check_week(ctx, week_start, now)
    start, week_end = week_bounds(monday, ctx.timezone)
    end = min(now, week_end)
    previous_start, previous_end = week_bounds(monday - timedelta(days=7), ctx.timezone)
    hours_available = hours_fact(session, ctx, now) is not None

    metrics: list[WeeklyMetric] = []
    for definition in WEEKLY_DEFINITIONS:
        if definition.key in NEEDS_HOURS and not hours_available:
            metrics.append(WeeklyMetric(definition.key, None, None))
            continue
        current = compute_metric(session, ctx, definition, start, end, now).value
        before = compute_metric(session, ctx, definition, previous_start, previous_end, now).value
        metrics.append(WeeklyMetric(definition.key, current, before))

    price_questions = next(m.value for m in metrics if m.key == "after_hours_price_answers")
    estimate = build_estimate(
        None if price_questions is None else int(price_questions),
        hours_available,
        _price_inputs(session, ctx, now),
    )
    return MissedCustomerReport(
        week_start=monday,
        week_end=monday + timedelta(days=6),
        timezone=ctx.timezone,
        period_start=start,
        period_end=end,
        generated_at=now,
        is_partial=end < week_end,
        hours_available=hours_available,
        metrics=metrics,
        estimate=estimate,
    )


def metric_items(
    session: Session,
    clock: Clock,
    ctx: WorkspaceContext,
    week_start: date,
    key: str,
    *,
    locale: str | None,
    cursor: str | None = None,
    limit: int = drilldown.DEFAULT_LIMIT,
) -> drilldown.Drilldown:
    """One page of the records behind ``key`` for the week; their count is the number.

    Runs the very row set that produced the metric (the number and the list agree by
    construction). Customers are shown by handle only, never message text.
    """
    definition = WEEKLY_BY_KEY.get(key)
    if definition is None:
        raise AppError("NOT_FOUND")
    now = clock.now()
    monday = check_week(ctx, week_start, now)
    if key in NEEDS_HOURS and hours_fact(session, ctx, now) is None:
        raise AppError("NOT_FOUND")  # "after hours" is unknown without verified hours
    position = drilldown.decode_cursor(cursor, ctx, monday, key) if cursor is not None else None
    start, week_end = week_bounds(monday, ctx.timezone)
    end = min(now, week_end)
    value = compute_metric(session, ctx, definition, start, end, now).value
    rows = definition.rows(session, ctx, start, end, now).subquery("rows")
    items, next_cursor = drilldown.rows_page(
        session,
        ctx,
        rows,
        local_date=monday,
        key=key,
        snapshot_id=None,
        position=position,
        limit=limit,
        language=normalize_locale(locale),
    )
    return drilldown.Drilldown(key, value, items, next_cursor, None)


def notify_ready(
    session: Session, clock: Clock, ctx: WorkspaceContext, report: MissedCustomerReport
) -> None:
    """One notification per week to every ``reports.view`` holder (deduped while unread).

    Counts only: a lira amount never leaves the report page, where its formula is shown. The
    report is never simulated (simulated records are excluded), so the notification is not.
    """
    notifications.notify_permission_holders(
        session,
        clock,
        ctx,
        permission="reports.view",
        type=MISSED_CUSTOMERS_READY,
        severity="info",
        params={
            "week_start": report.week_start.isoformat(),
            "after_hours_dms": report.value("after_hours_dms"),
            "unanswered_conversations": report.value("unanswered_conversations"),
        },
        dedup_key=f"missed-customers:{report.week_start.isoformat()}",
        is_simulated=False,
    )


def generate_weekly_report(
    session: Session, clock: Clock, ctx: WorkspaceContext, week_start: date
) -> MissedCustomerReport:
    """The scheduled run: build the report and announce it when there is something to tell."""
    report = build_report(session, clock, ctx, week_start)
    if not report.empty:
        notify_ready(session, clock, ctx, report)
    return report
