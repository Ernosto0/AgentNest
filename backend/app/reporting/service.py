"""The daily report (workflows.md section F).

``get_report`` serves a day: **today is always computed live** (``period_end = now``) and never
stored by a read; a past day is the stored row, computed and stored on first read (H3).
``generate_daily_report`` stores whatever it computes (the scheduler and "regenerate").

INV-08: every number is a SQL aggregation (``compute_metrics``); no language model is involved.
INV-19: the day is the workspace's local day. Neither function commits; the caller does.
"""

import uuid
from dataclasses import dataclass, replace
from datetime import date, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.audit import service as audit
from app.core.clock import Clock
from app.core.context import WorkspaceContext
from app.core.errors import AppError
from app.notifications import service as notifications
from app.reporting.definitions import BY_KEY, DEFINITIONS_VERSION
from app.reporting.metrics import Metrics, compute_metrics
from app.reporting.models import DailyReport
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


def _store(session: Session, ctx: WorkspaceContext, report: Report) -> uuid.UUID:
    """Upsert by ``(workspace_id, local_date)``: regeneration overwrites (INV-08: the records
    are the source, the previous value is not needed)."""
    values: dict[str, Any] = {
        "workspace_id": ctx.workspace_id,
        "local_date": report.local_date,
        "timezone": report.timezone,
        "period_start": report.period_start,
        "period_end": report.period_end,
        "metrics": report.metrics,
        "definitions_version": report.definitions_version,
        "has_simulated_data": report.has_simulated_data,
        "generated_at": report.generated_at,
    }
    update = {k: v for k, v in values.items() if k not in ("workspace_id", "local_date")}
    statement = (
        pg_insert(DailyReport)
        .values(**values)
        .on_conflict_do_update(index_elements=["workspace_id", "local_date"], set_=update)
        .returning(DailyReport.id)
    )
    return session.execute(statement).scalar_one()


def get_report(session: Session, clock: Clock, ctx: WorkspaceContext, local_date: date) -> Report:
    """Today live; a past day stored (and stored now if it was never generated)."""
    now = clock.now()
    today = check_not_future(ctx, local_date, now)
    if local_date == today:
        return _compute(session, ctx, local_date, now)
    row = session.scalar(
        select(DailyReport).where(
            DailyReport.workspace_id == ctx.workspace_id, DailyReport.local_date == local_date
        )
    )
    if row is not None:
        return _from_row(row)
    return generate_daily_report(session, clock, ctx, local_date, scheduled=False)


def generate_daily_report(
    session: Session,
    clock: Clock,
    ctx: WorkspaceContext,
    local_date: date,
    *,
    scheduled: bool,
) -> Report:
    """Compute and store the report of ``local_date`` (overwriting a stored one).

    Audits ``report.generated`` in the same transaction. Only a **scheduled** run announces the
    report (``report.daily_ready`` to every ``reports.view`` holder, one per day until read).
    """
    now = clock.now()
    check_not_future(ctx, local_date, now)
    report = _compute(session, ctx, local_date, now)
    report_id = _store(session, ctx, report)
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
    return replace(report, stored=True)


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
