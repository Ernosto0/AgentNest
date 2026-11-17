"""Deterministic, workspace-local previews for management commands."""

from dataclasses import replace
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent.models import AccountAgent
from app.ai.schemas import AgentPauseUntil, CommandTime, ContentReschedule
from app.commands import resolver as r
from app.commands.results import CommandResult
from app.content.scheduling import ScheduleError, local_to_utc
from app.core.context import WorkspaceContext
from app.core.i18n import format_local_slot
from app.integrations.instagram.models import SocialAccount

RESCHEDULABLE = ("pending_approval", "scheduled", "on_hold")


def agent_snapshot(session: Session, ctx: WorkspaceContext) -> dict[str, Any] | None:
    accounts = session.scalars(
        select(AccountAgent).where(
            AccountAgent.workspace_id == ctx.workspace_id,
            AccountAgent.controller_mode == "agent",
            AccountAgent.state.in_(("active", "paused")),
        )
    ).all()
    if len(accounts) != 1:
        return None
    account = accounts[0]
    social = session.scalar(
        select(SocialAccount).where(
            SocialAccount.id == account.social_account_id,
            SocialAccount.workspace_id == ctx.workspace_id,
        )
    )
    return {
        "account_id": str(account.social_account_id),
        "config_version": account.config_version,
        "state": account.state,
        "controller_epoch": account.controller_epoch,
        "is_simulated": social is not None and social.provider_kind == "mock",
    }


def instant(
    time: CommandTime, context: r.ContentContext, default: datetime | None = None
) -> datetime:
    if context.now is None:
        raise ValueError("missing clock")
    today = context.now.astimezone(ZoneInfo(context.timezone)).date()
    if time.local_date in ("today", "tomorrow"):
        day = today + timedelta(days=int(time.local_date == "tomorrow"))
    elif time.local_date:
        day = date.fromisoformat(time.local_date)
    elif default:
        day = default.astimezone(ZoneInfo(context.timezone)).date()
    else:
        raise ValueError("missing date")
    wall = "09:00" if time.local_time == "morning" else time.local_time
    result, _ = local_to_utc(day, wall, context.timezone)
    if result <= context.now:
        raise ScheduleError("SCHEDULE_IN_PAST")
    if result > context.now + timedelta(days=60):
        raise ScheduleError("SCHEDULE_TOO_FAR")
    return result


def rejected(code: str) -> r.Rejected:
    return r.Rejected(
        code, CommandResult("command.management_refused", {"reason": code}, error_code=code)
    )


def resolve_reschedule(
    proposal: ContentReschedule, context: r.ContentContext | None, locale: str
) -> r.Outcome:
    if context is None:
        return rejected("REFERENCE_NOT_FOUND")
    matches, _ = r._find_content(proposal.content_ref, context, RESCHEDULABLE)
    if not matches:
        return r._not_found(proposal.content_ref.description)
    if len(matches) > 1:
        question = r._content_choice(proposal.type, matches, context, locale)
        return replace(question, pending={**question.pending, "time": proposal.time.model_dump()})
    return reschedule_item(matches[0], proposal.time, context, locale)


def reschedule_item(
    item: r.ContentSnapshot, time: CommandTime, context: r.ContentContext, locale: str
) -> r.Outcome:
    if item.status not in RESCHEDULABLE or item.scheduled_at is None:
        return rejected("CONFLICT_STATE")
    try:
        when = instant(time, context, item.scheduled_at)
    except (ValueError, ScheduleError) as exc:
        return rejected(exc.code if isinstance(exc, ScheduleError) else "VALIDATION_FAILED")
    return r.Confirm(
        "content.reschedule",
        "command.reschedule_content",
        {
            "content_id": str(item.id),
            "content_version": item.version,
            "old_scheduled_at": item.scheduled_at.isoformat(),
            "scheduled_at": when.isoformat(),
            "timezone": context.timezone,
        },
        {
            "label": item.title,
            "old_formatted": format_local_slot(item.scheduled_at, context.timezone, locale),
            "new_formatted": format_local_slot(when, context.timezone, locale),
            "timezone": context.timezone,
            "content_id": str(item.id),
            "is_simulated": item.is_simulated,
        },
    )


def resolve_pause(
    proposal: AgentPauseUntil,
    context: r.ContentContext | None,
    agent: dict[str, Any] | None,
    locale: str,
) -> r.Outcome:
    if context is None or agent is None:
        return rejected("CONFLICT_STATE")
    try:
        when = instant(proposal.time, context)
    except (ValueError, ScheduleError) as exc:
        return rejected(exc.code if isinstance(exc, ScheduleError) else "VALIDATION_FAILED")
    return r.Confirm(
        "agent.pause_until",
        "command.pause_agent",
        {
            **agent,
            "resume_at": when.isoformat(),
            "timezone": context.timezone,
        },
        {
            "resume_at": format_local_slot(when, context.timezone, locale),
            "timezone": context.timezone,
            "is_simulated": bool(agent.get("is_simulated", False)),
        },
    )
