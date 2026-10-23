"""The daily report (workflows.md section F).

``get_report`` serves a day: **today is always computed live** (``period_end = now``) and never
stored by a read; a past day is the stored row, computed and stored on first read (H3).
``generate_daily_report`` appends an immutable generation and its contributing membership.

INV-08: every number is a SQL aggregation (``compute_metrics``); no language model is involved.
INV-19: the day is the workspace's local day. Neither function commits; the caller does.
"""

import uuid
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from sqlalchemy import func, insert, literal, select, union_all
from sqlalchemy.orm import Session

from app.audit import service as audit
from app.core.clock import Clock
from app.core.context import WorkspaceContext
from app.core.errors import AppError
from app.identity.models import Workspace
from app.notifications import service as notifications
from app.reporting.definitions import BY_KEY, DEFINITIONS, DEFINITIONS_VERSION
from app.reporting.metrics import Metrics, compute_metrics, compute_stored_metrics
from app.reporting.models import DailyReport, ReportItem, ReportSourceGap
from app.reporting.periods import day_bounds, local_date_of

DAILY_READY = "report.daily_ready"
GENERATED = "report.generated"


@dataclass(frozen=True)
class Report:
    local_date: date
    timezone: str
    period_start: datetime
    period_end: datetime
    generated_at: datetime
    is_partial: bool  # the period ends before the end of the local day
    definitions_version: str
    has_simulated_data: bool
    # key -> {"value": ..., "breakdown": {...}?}; the stored shape of ``daily_reports.metrics``.
    metrics: dict[str, dict[str, Any]]
    stored: bool
    snapshot_id: uuid.UUID | None = None
    evidence_complete: bool = True

    def value(self, key: str) -> int | float | None:
        entry = self.metrics.get(key)
        return None if entry is None else entry.get("value")


def _validation(field: str, code: str) -> AppError:
    return AppError("VALIDATION_FAILED", errors=[{"field": field, "code": code, "params": {}}])


def _stored_metrics(metrics: Metrics) -> dict[str, dict[str, Any]]:
    stored: dict[str, dict[str, Any]] = {}
    for metric in metrics.metrics:
        entry: dict[str, Any] = {"value": metric.value}
        if metric.breakdown is not None:
            entry["breakdown"] = metric.breakdown
        stored[metric.key] = entry
    return stored


def _is_partial(period_end: datetime, local_date: date, timezone: str) -> bool:
    return period_end < day_bounds(local_date, timezone)[1]


def _from_row(row: DailyReport) -> Report:
    return Report(
        local_date=row.local_date,
        timezone=row.timezone,
        period_start=row.period_start,
        period_end=row.period_end,
        generated_at=row.generated_at,
        is_partial=_is_partial(row.period_end, row.local_date, row.timezone),
        definitions_version=row.definitions_version,
        has_simulated_data=row.has_simulated_data,
        metrics=dict(row.metrics),
        stored=True,
        snapshot_id=row.id,
        evidence_complete=row.evidence_complete,
    )


def check_not_future(ctx: WorkspaceContext, local_date: date, now: datetime) -> date:
    today = local_date_of(now, ctx.timezone)
    if local_date > today:
        raise _validation("date", "in_future")
    return today


def _compute(session: Session, ctx: WorkspaceContext, local_date: date, now: datetime) -> Report:
    """The report of ``local_date`` as of ``now``: the whole day, or up to ``now`` for today."""
    start, day_end = day_bounds(local_date, ctx.timezone)
    end = min(now, day_end)
    metrics = compute_metrics(session, ctx, start, end, now)
    return Report(
        local_date=local_date,
        timezone=ctx.timezone,
        period_start=start,
        period_end=end,
        generated_at=now,
        is_partial=end < day_end,
        definitions_version=metrics.definitions_version,
        has_simulated_data=metrics.has_simulated_data,
        metrics=_stored_metrics(metrics),
        stored=False,
    )


def stored_report(
    session: Session, ctx: WorkspaceContext, local_date: date, snapshot_id: uuid.UUID | None = None
) -> DailyReport | None:
    statement = select(DailyReport).where(
        DailyReport.workspace_id == ctx.workspace_id, DailyReport.local_date == local_date
    )
    if snapshot_id is not None:
        statement = statement.where(DailyReport.id == snapshot_id)
    return session.scalar(statement.order_by(DailyReport.revision.desc()).limit(1))


def check_sources(session: Session, ctx: WorkspaceContext, start: datetime, end: datetime) -> None:
    missing = sorted(
        set(
            session.scalars(
                select(ReportSourceGap.metric_key).where(
                    ReportSourceGap.workspace_id == ctx.workspace_id,
                    ReportSourceGap.start_at < end,
                    ReportSourceGap.end_at >= start,
                )
            )
        )
    )
    if missing:
        raise AppError("REPORT_SOURCES_RETAINED_OUT", metrics=missing)


def _capture(session: Session, ctx: WorkspaceContext, row: DailyReport, now: datetime) -> None:
    """One INSERT/SELECT sees all registry sources at one PostgreSQL statement snapshot."""
    sources = []
    for definition in DEFINITIONS:
        rows = definition.rows(session, ctx, row.period_start, row.period_end, now).subquery()
        sources.append(
            select(
                func.gen_random_uuid(),
                literal(ctx.workspace_id),
                literal(row.id),
                literal(definition.key),
                *rows.c,
            )
        )
    session.execute(
        insert(ReportItem).from_select(
            [
                "id",
                "workspace_id",
                "report_id",
                "metric_key",
                "subject_type",
                "subject_id",
                "occurred_at",
                "is_simulated",
                "link_id",
                "measure",
                "group_key",
            ],
            union_all(*sources),
        )
    )


def get_report(
    session: Session,
    clock: Clock,
    ctx: WorkspaceContext,
    local_date: date,
    *,
    snapshot_id: uuid.UUID | None = None,
) -> Report:
    """Today live; a past day stored (and stored now if it was never generated)."""
    now = clock.now()
    today = check_not_future(ctx, local_date, now)
    if snapshot_id is not None:
        snapshot = stored_report(session, ctx, local_date, snapshot_id)
        if snapshot is None:
            raise AppError("NOT_FOUND")
        return _from_row(snapshot)
    if local_date == today:
        start, end = day_bounds(local_date, ctx.timezone)
        check_sources(session, ctx, start, min(now, end))
        return _compute(session, ctx, local_date, now)
    row = stored_report(session, ctx, local_date)
    if row is not None:
        return _from_row(row)
    return generate_daily_report(session, clock, ctx, local_date, scheduled=False, if_missing=True)


def generate_daily_report(
    session: Session,
    clock: Clock,
    ctx: WorkspaceContext,
    local_date: date,
    *,
    scheduled: bool,
    if_missing: bool = False,
) -> Report:
    """Capture a new immutable generation; retained-out sources refuse regeneration.

    Audits ``report.generated`` in the same transaction. Only a **scheduled** run announces the
    report (``report.daily_ready`` to every ``reports.view`` holder, one per day until read).
    """
    now = clock.now()
    check_not_future(ctx, local_date, now)
    # Serialize generation numbers, including first-read races, within one tenant.
    workspace = session.scalar(
        select(Workspace.id).where(Workspace.id == ctx.workspace_id).with_for_update()
    )
    if workspace is None:
        raise AppError("NOT_FOUND")
    previous = stored_report(session, ctx, local_date)
    if if_missing and previous is not None:
        return _from_row(previous)
    start, day_end = day_bounds(local_date, ctx.timezone)
    end = min(now, day_end)
    check_sources(session, ctx, start, end)
    row = DailyReport(
        workspace_id=ctx.workspace_id,
        local_date=local_date,
        revision=1 if previous is None else previous.revision + 1,
        timezone=ctx.timezone,
        period_start=start,
        period_end=end,
        definitions_version=DEFINITIONS_VERSION,
        generated_at=now,
        evidence_complete=True,
    )
    session.add(row)
    session.flush()
    _capture(session, ctx, row, now)
    # A concurrent retention commit must not yield an apparently complete generation.
    check_sources(session, ctx, start, end)
    computed = compute_stored_metrics(session, ctx, row.id)
    row.metrics = _stored_metrics(computed)
    row.has_simulated_data = computed.has_simulated_data
    session.flush()
    report = _from_row(row)
    report_id = row.id
    audit.record(
        session,
        ctx,
        GENERATED,
        "daily_report",
        report_id,
        {
            "local_date": local_date.isoformat(),
            "scheduled": scheduled,
            "definitions_version": report.definitions_version,
            "is_partial": report.is_partial,
        },
        is_simulated=report.has_simulated_data,
        clock=clock,
    )
    if scheduled:
        notifications.notify_permission_holders(
            session,
            clock,
            ctx,
            permission="reports.view",
            type=DAILY_READY,
            severity="info",
            params={"local_date": local_date.isoformat()},
            subject_type="daily_report",
            subject_id=report_id,
            dedup_key=f"report:{local_date.isoformat()}",
            is_simulated=report.has_simulated_data,
        )
    return report


def known_keys(report: Report) -> list[str]:
    """The stored keys that the current registry still defines, in registry order."""
    return [key for key in BY_KEY if key in report.metrics]


__all__ = [
    "DEFINITIONS_VERSION",
    "Report",
    "generate_daily_report",
    "get_report",
    "known_keys",
]
