"""``content.cancel_scheduled`` (workflows.md §B and §E step 7).

Runs inside the approval's decided-callback, in the same transaction as the decision, as the
**human who decided** (INV-04): ``ec.ctx`` is the decider, and the service call below is the very
one behind the cancel route. The confirmation is bound to ``{content_id, content_version}``: an
item that was edited, submitted again or cancelled since the owner looked is **not** cancelled.
The command fails (``VERSION_CONFLICT`` / ``CONFLICT_STATE``) and the decision stands, like
``FACT_CHANGED_MEANWHILE`` for facts (INV-16). The cancel runs in a savepoint, so a refusal
half-way leaves nothing behind.
"""

import uuid
from typing import Any

from app.commands.resolver import content_link
from app.commands.results import CommandResult, ExecContext
from app.content import service
from app.core.errors import AppError
from app.core.i18n import format_local_slot

STALE_CODES = ("VERSION_CONFLICT", "CONFLICT_STATE", "NOT_FOUND")


def execute(ec: ExecContext, resolution: dict[str, Any]) -> CommandResult:
    content_id = uuid.UUID(resolution["content_id"])
    try:
        with ec.session.begin_nested():
            item = service.apply_cancel(
                ec.session,
                ec.clock,
                ec.ctx,
                content_id,
                expected_version=int(resolution["content_version"]),
            )
    except AppError as exc:
        if exc.code not in STALE_CODES:
            raise
        return CommandResult(
            "command.content_changed_meanwhile",
            {},
            [content_link(content_id)] if exc.code != "NOT_FOUND" else [],
            error_code=exc.code,
        )
    when = (
        format_local_slot(item.scheduled_at, ec.ctx.timezone, ec.user_locale)
        if item.scheduled_at
        else None
    )
    return CommandResult(
        "command.content_cancelled",
        {"title": item.title, "when": when},
        [content_link(item.id)],
    )
