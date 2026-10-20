"""``query.content_status``: where one post stands (read-only).

The status is the item's own state, never a success the request implies (INV-18): "scheduled"
is not "published". Simulated items say so (INV-09). Only the title, type, state and time are
returned; the caption and the media stay in the content screen the link opens.
"""

import uuid
from typing import Any

from app.commands.resolver import content_link
from app.commands.results import CommandResult, ExecContext
from app.content import service
from app.core.i18n import format_local_slot


def execute(ec: ExecContext, resolution: dict[str, Any]) -> CommandResult:
    item = service.get_item(ec.session, ec.ctx, uuid.UUID(resolution["content_id"]))
    moment = item.published_at if item.status == "published" else item.scheduled_at
    when = format_local_slot(moment, ec.ctx.timezone, ec.user_locale) if moment else None
    return CommandResult(
        "command.content_status",
        {
            "title": item.title,
            "content_type": item.content_type,
            "status": item.status,
            "when": when,
            "is_simulated": item.is_simulated,
            "hold_reason": item.hold_reason,
            "error_code": item.last_error_code,
        },
        [content_link(item.id)],
    )
