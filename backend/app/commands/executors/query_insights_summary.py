"""``query.insights_summary``: performance from stored, coverage-checked insights."""

from typing import Any

from app.commands.narrator import narrate_fallback
from app.commands.results import CommandResult, ExecContext
from app.insights import service
from app.integrations.instagram import queries


def execute(ec: ExecContext, resolution: dict[str, Any]) -> CommandResult:
    accounts = queries.list_accounts(ec.session, ec.ctx)
    account = next((a for a in accounts if a.status != "disconnected"), None)

    if not account:
        params = {"reach": 0, "views": 0, "interactions": 0, "days": 7, "is_simulated": False}
        reply_text = (
            "Henüz bağlı bir Instagram hesabı bulunmuyor."
            if ec.user_locale.lower().startswith("tr")
            else "No connected Instagram account found."
        )
        return CommandResult("command.insights_summary", params, [], reply_text=reply_text)

    range_val = str(resolution.get("range", "7d"))
    days = 28 if range_val == "28d" else 7
    summary = service.get_summary(
        ec.session, ec.ctx.workspace_id, account.id, range_days=days, clock=ec.clock
    )

    params = {
        "reach": summary.reach,
        "views": summary.views,
        "interactions": summary.interactions,
        "days": days,
        "is_simulated": summary.is_simulated,
        "status": summary.status,
    }

    reply_text = narrate_fallback(
        message_key="command.insights_summary",
        params=params,
        user_locale=ec.user_locale,
        user_query=getattr(ec.command, "raw_text", ""),
    )

    link = {"target": "more/reports"}
    return CommandResult("command.insights_summary", params, [link], reply_text=reply_text)
