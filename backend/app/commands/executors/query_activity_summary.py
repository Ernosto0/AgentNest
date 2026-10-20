"""``query.activity_summary``: basic counts from the audit log.

Basic by design (INV-08): every number is a SQL count of persisted records, never anything
model-generated. The full daily report with documented metric definitions arrives in Phase 6.
"""

from typing import Any

from sqlalchemy import func, select

from app.audit.models import AuditLog
from app.commands.results import CommandResult, ExecContext
from app.reporting.periods import period_bounds

FACT_ACTIONS = ("fact.created", "fact.updated", "fact.verified", "fact.archived")
APPROVAL_ACTIONS = ("approval.approved", "approval.rejected")


def execute(ec: ExecContext, resolution: dict[str, Any]) -> CommandResult:
    period = str(resolution.get("period", "today"))
    start, end = period_bounds(period, ec.clock.now(), ec.ctx.timezone)
    rows = ec.session.execute(
        select(AuditLog.action, func.count())
        .where(
            AuditLog.workspace_id == ec.ctx.workspace_id,
            AuditLog.occurred_at >= start,
            AuditLog.occurred_at <= end,
        )
        .group_by(AuditLog.action)
    ).all()
    counts = {action: int(n) for action, n in rows}
    return CommandResult(
        "command.activity_basic",
        {
            "period": period,
            "fact_changes": sum(counts.get(a, 0) for a in FACT_ACTIONS),
            "commands": counts.get("command.received", 0),
            "approvals_decided": sum(counts.get(a, 0) for a in APPROVAL_ACTIONS),
            "basic": True,
        },
        [],
    )
