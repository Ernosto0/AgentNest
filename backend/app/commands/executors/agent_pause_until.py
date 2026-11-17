"""Pause through the same service as HTTP, then durably schedule a fenced resume."""

import uuid
from datetime import datetime
from typing import Any

from app.agent.pause_jobs import ResumePayload
from app.agent.state import change_state
from app.commands.results import CommandResult, ExecContext
from app.core.errors import AppError
from app.core.i18n import format_local_slot
from app.jobs.queue import enqueue


def execute(ec: ExecContext, resolution: dict[str, Any]) -> CommandResult:
    when = datetime.fromisoformat(resolution["resume_at"])
    try:
        with ec.session.begin_nested():
            if when <= ec.clock.now() or resolution["timezone"] != ec.ctx.timezone:
                raise AppError("VALIDATION_FAILED")
            account = change_state(
                ec.session,
                ec.clock,
                ec.ctx,
                uuid.UUID(resolution["account_id"]),
                resolution["config_version"],
                "paused",
                repause=True,
            )
            enqueue(
                ec.session,
                "agent_resume_due",
                ResumePayload(
                    account_id=account.social_account_id,
                    config_version=account.config_version,
                    controller_epoch=account.controller_epoch,
                    user_id=uuid.UUID(str(ec.ctx.actor.id)),
                    resume_at=when,
                ),
                workspace_id=ec.ctx.workspace_id,
                correlation_id=ec.command.correlation_id,
                run_at=when,
                dedup_key=f"agent_resume_due:{account.social_account_id}:{account.config_version}",
                clock=ec.clock,
            )
    except AppError as exc:
        return CommandResult(
            "command.management_refused", {"reason": exc.code}, error_code=exc.code
        )
    return CommandResult(
        "command.agent_paused_until",
        {"when": format_local_slot(when, ec.ctx.timezone, ec.user_locale)},
    )
