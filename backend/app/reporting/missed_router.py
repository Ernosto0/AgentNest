"""The weekly missed-customer report routes (D-03, api-design.md section 2.8).

Owner and manager only (``reports.view``): the report carries a lira estimate. The week is the
local Monday-to-Sunday week of ``week_start`` (any date in it); the current week is live and
partial. A foreign workspace id is a 404 (INV-01).
"""

from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import current_auth, get_clock, require_membership
from app.core.clock import Clock
from app.core.context import WorkspaceContext
from app.core.db import get_db
from app.core.i18n import normalize_locale
from app.identity.service import AuthenticatedSession
from app.reporting import drilldown, links, missed_customers
from app.reporting.periods import local_date_of
from app.reporting.schemas import (
    EstimateOut,
    MetricItemOut,
    MetricItemsOut,
    MissedCustomerReportOut,
    PriceInputOut,
    ReportLinkOut,
    WeeklyMetricOut,
)

router = APIRouter(prefix="/workspaces/{workspace_id}/reports/missed-customers", tags=["reports"])

VIEW = "reports.view"


def _label(label: dict[str, Any], key: str, locale: str) -> str:
    for candidate in (locale, "tr", "en"):
        value = label.get(candidate)
        if isinstance(value, str) and value:
            return value
    return key


def present(
    report: missed_customers.MissedCustomerReport, ctx: WorkspaceContext, locale: str | None
) -> MissedCustomerReportOut:
    language = normalize_locale(locale)
    estimate = report.estimate
    return MissedCustomerReportOut(
        week_start=report.week_start,
        week_end=report.week_end,
        timezone=report.timezone,
        period_start=report.period_start,
        period_end=report.period_end,
        generated_at=report.generated_at,
        is_partial=report.is_partial,
        hours_available=report.hours_available,
        has_simulated_data=False,
        metrics=[
            WeeklyMetricOut(
                key=m.key,
                value=m.value,
                previous_value=m.previous_value,
                link=(
                    None
                    if m.value is None
                    else ReportLinkOut(
                        **links.missed_metric_link(ctx.workspace_id, report.week_start, m.key)
                    )
                ),
            )
            for m in report.metrics
        ],
        estimate=EstimateOut(
            status=estimate.status,
            currency=estimate.currency,
            amount=None if estimate.amount is None else f"{estimate.amount:.2f}",
            price_questions=estimate.price_questions,
            conversion_rate=f"{estimate.conversion_rate:f}",
            median_price=None if estimate.median_price is None else f"{estimate.median_price:.2f}",
            price_inputs=[
                PriceInputOut(
                    key=p.key,
                    label=_label(p.label, p.key, language),
                    amount=f"{p.amount:.2f}",
                    unit=p.unit,
                )
                for p in estimate.price_inputs
            ],
            price_count=estimate.price_count,
        ),
    )


@router.get("", response_model=MissedCustomerReportOut)
def get_missed_customer_report(
    week_start: date | None = Query(default=None),
    ctx: WorkspaceContext = Depends(require_membership(VIEW)),
    auth: AuthenticatedSession = Depends(current_auth),
    db: Session = Depends(get_db),
    clock: Clock = Depends(get_clock),
) -> MissedCustomerReportOut:
    """The week of ``week_start`` (default: this week so far), computed from the records."""
    day = week_start or local_date_of(clock.now(), ctx.timezone)
    report = missed_customers.build_report(db, clock, ctx, day)
    return present(report, ctx, auth.user.ui_locale)


@router.get("/{week_start}/metrics/{key}", response_model=MetricItemsOut)
def get_missed_customer_items(
    week_start: date,
    key: str,
    cursor: str | None = None,
    limit: int = Query(default=drilldown.DEFAULT_LIMIT, ge=1, le=drilldown.MAX_LIMIT),
    ctx: WorkspaceContext = Depends(require_membership(VIEW)),
    auth: AuthenticatedSession = Depends(current_auth),
    db: Session = Depends(get_db),
    clock: Clock = Depends(get_clock),
) -> MetricItemsOut:
    """The records behind one number of the week; their count is the number."""
    result = missed_customers.metric_items(
        db, clock, ctx, week_start, key, locale=auth.user.ui_locale, cursor=cursor, limit=limit
    )
    return MetricItemsOut(
        snapshot_id=None,
        key=result.key,
        value=result.value,
        items=[
            MetricItemOut(
                kind=i.kind,
                id=i.id,
                label=i.label,
                occurred_at=i.occurred_at,
                is_simulated=i.is_simulated,
                measure=i.measure,
                link=None if i.link is None else ReportLinkOut(**i.link),
            )
            for i in result.items
        ],
        next_cursor=result.next_cursor,
    )
