"""``content.create_draft``: a draft with a queued generation (workflows.md §E step 1).

No confirmation: it creates only a draft, which is non-destructive and still needs a schedule
and an approval before anything is published (agent-runtime.md §3). It runs in the command's own
transaction (``stage_request`` does not commit) as the requester, with their ``content.edit``.

The ``client_request_id`` is derived from the command, so a replayed interpretation job asks for
the same draft again and gets the first one (G7) instead of paying for a second generation.
"""

from typing import Any

from app.commands.resolver import content_link
from app.commands.results import CommandResult, ExecContext
from app.content import generation


def execute(ec: ExecContext, resolution: dict[str, Any]) -> CommandResult:
    item, _created = generation.stage_request(
        ec.session,
        ec.clock,
        ec.ctx,
        content_type=resolution["content_type"],
        objective=resolution["objective"],
        notes=resolution.get("notes"),
        client_request_id=f"command:{ec.command.id}",
    )
    return CommandResult(
        "command.draft_created",
        {"title": item.title, "content_type": item.content_type},
        [content_link(item.id)],
    )
