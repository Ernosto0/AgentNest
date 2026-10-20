"""``query.activity_summary``: what happened in a period, from the daily report's numbers.

INV-08: every number comes from ``reporting.compute_metrics`` (SQL over persisted records), the
same code as the report, so the answer for "today" equals the report's ``inbound_messages`` at the
same instant (AC-E4). Nothing here is estimated or written by the model.

The periods are ``today`` (the local day so far), ``yesterday`` and ``last_7_days`` (the last
seven local days, ending now), all computed in the workspace timezone (INV-19).
"""

from typing import Any

from app.commands.results import CommandResult, ExecContext
from app.reporting.metrics import compute_metrics
from app.reporting.periods import local_date_of, period_bounds

PERIODS = ("today", "yesterday", "last_7_days")

# The metrics the answer names (plan H5): result parameter -> report metric key.
METRICS = {
    "inbound_messages": "inbound_messages",
    "conversations": "conversations_with_inbound",
    "replies_sent": "replies_sent",
    "replies_auto": "replies_sent_auto",
    "replies_approved": "replies_sent_approved",
    "replies_by_owner": "replies_sent_by_owner",
    "escalations": "escalations",
    "attention_now": "attention_now",
}


def execute(ec: ExecContext, resolution: dict[str, Any]) -> CommandResult:
    period = str(resolution.get("period", "today"))
    if period not in PERIODS:
        period = "today"
    now = ec.clock.now()
    start, end = period_bounds(period, now, ec.ctx.timezone)
    metrics = compute_metrics(ec.session, ec.ctx, start, end, now)
    params: dict[str, Any] = {"period": period}
    for name, key in METRICS.items():
        params[name] = metrics.value(key)
    params["is_simulated"] = metrics.has_simulated_data
    # "Raporu aç": a past period opens its day; the others open today's report.
    report_date = local_date_of(start if period == "yesterday" else now, ec.ctx.timezone)
    link = {"target": "report", "date": report_date.isoformat()}
    return CommandResult("command.activity_summary", params, [link])
