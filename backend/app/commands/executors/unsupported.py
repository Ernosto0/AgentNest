"""``unsupported``: not in the registry by design (agent-runtime.md §3, FR-035).

Suggestions and the pointer into the app are chosen by code from the closed ``reason`` code,
never taken from model text, so a model (or an injected instruction) cannot put anything in
front of the owner here.
"""

from typing import Any

from app.commands.results import CommandResult, ExecContext

DEFAULT_SUGGESTIONS = (
    "command.suggest.update_price",
    "command.suggest.ask_price",
    "command.suggest.activity",
)

# reason -> where the owner can do it themselves
POINTERS: dict[str, dict[str, Any]] = {
    "publish": {"target": "content"},
    "send_message": {"target": "inbox"},
    "approve": {"target": "approvals"},
    "manage_account": {"target": "integrations"},
    "settings": {"target": "automation"},
    "members": {"target": "members"},
}


def execute(ec: ExecContext, resolution: dict[str, Any]) -> CommandResult:
    reason = str(resolution.get("reason", "other"))
    pointer = POINTERS.get(reason)
    return CommandResult(
        "command.unsupported",
        {"reason": reason, "suggestions": list(DEFAULT_SUGGESTIONS)},
        [pointer] if pointer else [],
    )
