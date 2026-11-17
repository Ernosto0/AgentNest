"""Reschedule only after a hash-bound decision; all changes share its transaction."""

import uuid
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from app.approvals import service as approvals
from app.commands.manage import RESCHEDULABLE
from app.commands.resolver import content_link
from app.commands.results import CommandResult, ExecContext
from app.content import service, transitions
from app.content.payload import publish_job_key
from app.content.service import ScheduleRequest
from app.core.config import get_settings
from app.core.errors import AppError
from app.core.i18n import format_local_slot
from app.jobs.queue import cancel_queued


def execute(ec: ExecContext, resolution: dict[str, Any]) -> CommandResult:
    content_id = uuid.UUID(resolution["content_id"])
    when = datetime.fromisoformat(resolution["scheduled_at"])
    try:
        with ec.session.begin_nested():
            item = service.get_item(ec.session, ec.ctx, content_id, lock=True)
            if item.version != resolution[
                "content_version"
            ] or item.scheduled_at != datetime.fromisoformat(resolution["old_scheduled_at"]):
                raise AppError("VERSION_CONFLICT")
            if item.status not in RESCHEDULABLE or ec.ctx.timezone != resolution["timezone"]:
                raise AppError("CONFLICT_STATE")
            if when <= ec.clock.now():
                raise AppError("VALIDATION_FAILED", reason="SCHEDULE_IN_PAST")
            approvals.cancel_for_subject(
                ec.session, ec.clock, ec.ctx, "content_item", item.id, "SUBJECT_EDITED"
            )
            cancel_queued(ec.session, publish_job_key(item.id, item.version), ec.clock)
            transitions.apply(ec.session, ec.clock, ec.ctx, item, "edit", scheduled_at=None)
            local = when.astimezone(ZoneInfo(ec.ctx.timezone))
            item = service.apply_submit(
                ec.session,
                ec.clock,
                get_settings(),
                ec.ctx,
                item.id,
                schedule=ScheduleRequest(
                    local_date=local.date(), local_time=local.strftime("%H:%M")
                ),
                self_approve=True,
                expected_version=item.version,
                account_id=item.social_account_id,
            )
    except AppError as exc:
        return CommandResult(
            "command.management_refused", {"reason": exc.code}, error_code=exc.code
        )
    return CommandResult(
        "command.content_rescheduled",
        {"title": item.title, "when": format_local_slot(when, ec.ctx.timezone, ec.user_locale)},
        [content_link(item.id)],
    )
