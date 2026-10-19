"""``query.pending_approvals``: what is waiting for a decision (read-only; never decides)."""

from typing import Any

from app.approvals import repository as approvals_repo
from app.commands.results import CommandResult, ExecContext

MAX_LISTED = 5


def execute(ec: ExecContext, resolution: dict[str, Any]) -> CommandResult:
    now = ec.clock.now()
    pending = [
        a
        for a in approvals_repo.list_approvals(ec.session, ec.ctx, status="pending", limit=100)
        if a.expires_at > now  # a due one is about to expire: not waiting for anyone
    ]
    items = [
        {
            "id": str(a.id),
            "action": a.action,
            "label": a.summary.get("label"),
            "new_formatted": a.summary.get("new_formatted"),
        }
        for a in pending[:MAX_LISTED]
    ]
    return CommandResult(
        "command.pending_approvals",
        {"count": len(pending), "items": items},
        [{"target": "approvals"}],
    )
