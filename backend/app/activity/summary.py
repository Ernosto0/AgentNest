"""Activity summary (api-design.md section 2.8): counts over recent local days of the workspace.

One bounded aggregate: the workspace's rows in the period are grouped by action, actor type and
the few metadata codes the classification reads, so the result has at most a few hundred rows
however long the history is. Each group is then classified with the same rules as the feed, so
the numbers match what the filters return.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.activity import classify
from app.audit.models import AuditLog
from app.core.clock import Clock
from app.core.context import WorkspaceContext
from app.reporting.periods import day_bounds

DEFAULT_DAYS = 7
MAX_DAYS = 90
# Every metadata field any rule reads.
_FIELDS: tuple[str, ...] = tuple(
    sorted({name for rule in classify.RULES.values() for name in rule.fields})
)


@dataclass(frozen=True)
class Summary:
    days: int
    period_start: datetime
    period_end: datetime
    total: int  # key activity: everything that is not routine detail
    routine: int
    failure: int
    warning: int
    success: int


def summarize(
    session: Session, ctx: WorkspaceContext, clock: Clock, days: int = DEFAULT_DAYS
) -> Summary:
    now = clock.now()
    local_today = now.astimezone(ZoneInfo(ctx.timezone)).date()
    start, _ = day_bounds(local_today - timedelta(days=days - 1), ctx.timezone)
    columns = [AuditLog.metadata_[name].astext.label(name) for name in _FIELDS]
    statement = (
        select(AuditLog.action, AuditLog.actor_type, *columns, func.count().label("n"))
        .where(
            AuditLog.workspace_id == ctx.workspace_id,
            AuditLog.occurred_at >= start,
            AuditLog.occurred_at <= now,
        )
        .group_by(AuditLog.action, AuditLog.actor_type, *columns)
    )
    counts = {"failure": 0, "warning": 0, "success": 0, "info": 0}
    total = routine = 0
    for row in session.execute(statement):
        metadata = {name: getattr(row, name) for name in _FIELDS}
        found = classify.classify(row.action, row.actor_type, metadata)
        n = int(row.n)
        if found.routine:
            routine += n
            continue
        total += n
        counts[found.level] += n
    return Summary(
        days=days,
        period_start=start,
        period_end=now,
        total=total,
        routine=routine,
        failure=counts["failure"],
        warning=counts["warning"],
        success=counts["success"],
    )
