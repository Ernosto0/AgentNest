"""Report routes (api-design.md section 2.8).

Everyone can read the report of their workspace, but staff see the inbox-related metrics only
(``reports.view_inbox_metrics``, H2): the other keys are left out of their report and their
drill-down is 403. Generating needs the full ``reports.view``. The summary is rendered in the
reader's UI language. A foreign workspace id is a 404 (INV-01).
"""

import uuid
from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import current_auth, get_clock, require_membership
from app.core.clock import Clock
from app.core.context import WorkspaceContext
from app.core.db import get_db
from app.core.errors import AppError
from app.identity.permissions import has_permission
from app.identity.service import AuthenticatedSession
from app.reporting import drilldown, links, service
from app.reporting.definitions import BY_KEY, INBOX_KEYS
from app.reporting.periods import local_date_of
from app.reporting.schemas import (
    DailyReportOut,
    GenerateReportRequest,
    MetricItemOut,
    MetricItemsOut,
    MetricOut,
    ReportLinkOut,
    SummaryOut,
    SummarySectionOut,
)
from app.reporting.summary import build_summary

router = APIRouter(prefix="/workspaces/{workspace_id}/reports/daily", tags=["reports"])

VIEW = "reports.view"
VIEW_INBOX = "reports.view_inbox_metrics"


def _link(value: links.Link | None) -> ReportLinkOut | None:
    return None if value is None else ReportLinkOut(**value)


def _visible_keys(ctx: WorkspaceContext, report: service.Report) -> list[str]:
    keys = service.known_keys(report)
    if has_permission(ctx.role, VIEW):
        return keys
    return [key for key in keys if key in INBOX_KEYS]


def _present(report: service.Report, ctx: WorkspaceContext, locale: str | None) -> DailyReportOut:
    keys = _visible_keys(ctx, report)
    metrics = []
    for key in keys:
        definition = BY_KEY[key]
        entry = report.metrics[key]
        breakdown = entry.get("breakdown")
        metrics.append(
            MetricOut(
                key=key,
                value=entry.get("value"),
                kind=definition.kind,
                section=definition.section,
                breakdown=None if breakdown is None else {k: int(v) for k, v in breakdown.items()},
                link=ReportLinkOut(
                    **links.metric_link(
                        ctx.workspace_id, report.local_date, key, report.snapshot_id
                    )
                ),
                screen_link=_link(links.screen_link(ctx.workspace_id, key)),
            )
        )
    summary = build_summary(report.metrics, keys, locale)
    return DailyReportOut(
        snapshot_id=report.snapshot_id,
        evidence_complete=report.evidence_complete,
        local_date=report.local_date,
        timezone=report.timezone,
        period_start=report.period_start,
        period_end=report.period_end,
        generated_at=report.generated_at,
        is_partial=report.is_partial,
        definitions_version=report.definitions_version,
        # A staff report is built from inbox keys only; the flag still covers the whole report,
        # which is the safe direction for the SIMULATED badge (INV-09).
        has_simulated_data=report.has_simulated_data,
        metrics=metrics,
        summary=SummaryOut(
            empty=summary.empty,
            text=summary.text,
            sections=[
                SummarySectionOut(section=s.section, title=s.title, lines=s.lines)
                for s in summary.sections
            ],
        ),
    )


@router.get("", response_model=DailyReportOut)
def get_daily_report(
    local_date: date | None = Query(default=None, alias="date"),
    snapshot_id: uuid.UUID | None = None,
    ctx: WorkspaceContext = Depends(require_membership(VIEW_INBOX)),
    auth: AuthenticatedSession = Depends(current_auth),
    db: Session = Depends(get_db),
    clock: Clock = Depends(get_clock),
) -> DailyReportOut:
    """Today live, a past day as stored (stored now if it never was)."""
    day = local_date or local_date_of(clock.now(), ctx.timezone)
    report = service.get_report(db, clock, ctx, day, snapshot_id=snapshot_id)
    db.commit()  # a past day that was not stored yet has just been
    return _present(report, ctx, auth.user.ui_locale)


@router.post("/generate", response_model=DailyReportOut)
def generate_daily_report(
    body: GenerateReportRequest,
    ctx: WorkspaceContext = Depends(require_membership(VIEW)),
    auth: AuthenticatedSession = Depends(current_auth),
    db: Session = Depends(get_db),
    clock: Clock = Depends(get_clock),
) -> DailyReportOut:
    """Capture a new generation without overwriting historical evidence."""
    report = service.generate_daily_report(db, clock, ctx, body.date, scheduled=False)
    db.commit()
    return _present(report, ctx, auth.user.ui_locale)


@router.get("/{local_date}/metrics/{key}", response_model=MetricItemsOut)
def get_metric_items(
    local_date: date,
    key: str,
    cursor: str | None = None,
    snapshot_id: uuid.UUID | None = None,
    limit: int = Query(default=drilldown.DEFAULT_LIMIT, ge=1, le=drilldown.MAX_LIMIT),
    ctx: WorkspaceContext = Depends(require_membership(VIEW_INBOX)),
    auth: AuthenticatedSession = Depends(current_auth),
    db: Session = Depends(get_db),
    clock: Clock = Depends(get_clock),
) -> MetricItemsOut:
    """The records behind one number; their count is the number (AC-E3)."""
    if key not in BY_KEY:
        raise AppError("NOT_FOUND")
    if key not in INBOX_KEYS and not has_permission(ctx.role, VIEW):
        raise AppError("FORBIDDEN", permission=VIEW)
    result = drilldown.metric_items(
        db,
        clock,
        ctx,
        local_date,
        key,
        locale=auth.user.ui_locale,
        cursor=cursor,
        limit=limit,
        snapshot_id=snapshot_id,
    )
    db.commit()  # the first direct drill-down of an unstored past day captures its report
    return MetricItemsOut(
        snapshot_id=result.snapshot_id,
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
                link=_link(i.link),
            )
            for i in result.items
        ],
        next_cursor=result.next_cursor,
    )
