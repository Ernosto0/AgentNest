"""Agent calendar tools: availability, appointment listing, booking, and modification."""

import uuid
from datetime import UTC, date, datetime, time, timedelta
from typing import Any, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent.delegation import CALENDAR_ACTIONS, authorize_action
from app.agent.grounding import CalendarEvidence, GroundedReply
from app.agent.models import ACTIVE_RUN_STATES, AgentAction, AgentEvent, AgentSession, AgentThread
from app.agent.repository import admit_action, scoped_thread
from app.agent.tools.broker import BrokerContext, ToolInputError
from app.approvals.models import Approval
from app.core.canonical import payload_hash
from app.core.clock import Clock
from app.core.config import get_settings
from app.core.db import get_session_factory
from app.core.ids import new_id
from app.identity.models import Workspace
from app.inbox.models import Conversation
from app.integrations.calendar import queries as cal_queries
from app.jobs.queue import enqueue
from app.knowledge.claims import length_issue
from app.operations import calendar as cal_ops
from app.operations.calendar import CalendarEffectPayload
from app.operations.models import Operation


class CalendarAvailabilityArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    local_date: date
    local_time: str | None = Field(default=None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    days: int = Field(default=1, ge=1, le=7)
    duration_minutes: int | None = Field(default=None, ge=15, le=240)


class CalendarListAppointmentsArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    local_date: date | None = None
    days: int = Field(default=7, ge=1, le=30)


class CalendarBookArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    local_date: date
    local_time: str = Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    duration_minutes: int | None = Field(default=None, ge=15, le=240)
    title: str = Field(min_length=1, max_length=150)
    customer_name: str | None = Field(default=None, max_length=120)
    customer_contact: str | None = Field(default=None, max_length=120)
    description: str | None = Field(default=None, max_length=500)


class CalendarModifyArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    appointment_id: uuid.UUID
    expected_version: int = Field(ge=1)
    operation: Literal["reschedule", "cancel"]
    new_local_date: date | None = None
    new_local_time: str | None = Field(default=None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    duration_minutes: int | None = Field(default=None, ge=15, le=240)
    reason: str | None = Field(default=None, max_length=300)


def _tz(db: Session, workspace_id: uuid.UUID) -> tuple[ZoneInfo, str]:
    ws = db.get(Workspace, workspace_id)
    name = (ws.timezone if ws else None) or "Europe/Istanbul"
    try:
        return ZoneInfo(name), name
    except ZoneInfoNotFoundError:
        return ZoneInfo("UTC"), "UTC"


def _local_dt(tz: ZoneInfo, d: date, hm: str) -> datetime:
    parts = hm.split(":")
    return datetime.combine(d, time(int(parts[0]), int(parts[1])), tzinfo=tz).astimezone(UTC)


def queue_calendar_action(db: Session, clock: Clock, action: AgentAction) -> None:
    action.status = "queued"
    enqueue(
        db,
        "calendar_effect",
        CalendarEffectPayload(action_id=action.id),
        workspace_id=action.workspace_id,
        correlation_id=action.id,
        dedup_key=f"calendar_effect:{action.id}:{action.version}",
        clock=clock,
    )


def result(db: Session, action: AgentAction) -> dict[str, Any]:
    if action.operation_id:
        op = db.get(Operation, action.operation_id)
        if op is not None:
            action.status = {
                "succeeded": "succeeded",
                "failed": "failed",
                "cancelled": "cancelled",
                "in_progress": "in_progress",
                "outcome_unknown": "outcome_unknown",
            }.get(op.status, action.status)
    appt = (
        cal_queries.get_appointment_in_workspace(db, action.workspace_id, action.payload_ref)
        if action.payload_ref
        else None
    )
    return {
        "action_id": str(action.id),
        "action_type": action.action_type,
        "status": action.status,
        "appointment_id": str(appt.id)
        if appt is not None
        else (str(action.payload_ref) if action.payload_ref else None),
        "appointment_version": appt.version if appt is not None else None,
        "approval_id": str(action.approval_id) if action.status == "waiting_approval" else None,
        "operation_id": str(action.operation_id) if action.operation_id else None,
    }


def availability(
    db: Session, clock: Clock, context: BrokerContext, args: BaseModel
) -> dict[str, Any]:
    req = CalendarAvailabilityArgs.model_validate(args)
    tz, _ = _tz(db, context.workspace.workspace_id)
    w_start = datetime.combine(req.local_date, time(0, 0), tzinfo=tz).astimezone(UTC)
    w_end = datetime.combine(
        req.local_date + timedelta(days=req.days), time(0, 0), tzinfo=tz
    ).astimezone(UTC)
    req_start = _local_dt(tz, req.local_date, req.local_time) if req.local_time else None

    res = cal_ops.check_availability(
        get_session_factory(),
        clock,
        get_settings(),
        context.workspace.workspace_id,
        window_start=w_start,
        window_end=w_end,
        duration_minutes=req.duration_minutes,
        requested_start_at=req_start,
        session=db,
    )
    return {
        "calendar_connected": res.calendar_connected,
        "timezone": res.timezone,
        "slot_duration_minutes": res.slot_duration_minutes,
        "hours_verified": res.hours_verified,
        "requested_slot_available": res.requested_slot_available,
        "available_slots": [
            {
                "local_date": s.local_date,
                "local_start_time": s.local_start_time,
                "local_end_time": s.local_end_time,
            }
            for s in res.available_slots[:24]
        ],
    }


def list_appointments(
    db: Session, clock: Clock, context: BrokerContext, args: BaseModel
) -> dict[str, Any]:
    req = CalendarListAppointmentsArgs.model_validate(args)
    thread = scoped_thread(
        db, context.workspace.workspace_id, context.account_id, context.thread_id
    )
    tz, tz_name = _tz(db, context.workspace.workspace_id)
    start_date = req.local_date or clock.now().astimezone(tz).date()
    w_start = datetime.combine(start_date, time(0, 0), tzinfo=tz).astimezone(UTC)
    w_end = datetime.combine(
        start_date + timedelta(days=req.days), time(0, 0), tzinfo=tz
    ).astimezone(UTC)

    customer_id = thread.customer_identity_id if context.surface == "dm" else None
    if context.surface == "dm" and customer_id is None:
        return {"timezone": tz_name, "items": []}

    rows = cal_queries.list_appointments_in_window(
        db,
        context.workspace.workspace_id,
        w_start,
        w_end,
        customer_identity_id=customer_id,
    )
    items = []
    for r in rows[:20]:
        ls = r.start_at.astimezone(tz)
        le = r.end_at.astimezone(tz)
        items.append(
            {
                "id": str(r.id),
                "version": r.version,
                "title": r.title[:150],
                "local_date": ls.date().isoformat(),
                "local_start_time": ls.strftime("%H:%M"),
                "local_end_time": le.strftime("%H:%M"),
                "status": r.status,
                "customer_name": r.customer_name if context.surface == "owner_task" else None,
            }
        )
    return {"timezone": tz_name, "items": items}


def _active_goal_and_event(db: Session, thread: AgentThread) -> tuple[AgentSession, AgentEvent]:
    goal = db.scalar(
        select(AgentSession).where(
            AgentSession.thread_id == thread.id,
            AgentSession.status.in_(ACTIVE_RUN_STATES),
        )
    )
    event = db.scalar(
        select(AgentEvent).where(
            AgentEvent.thread_id == thread.id,
            AgentEvent.cursor == thread.event_cursor,
        )
    )
    if goal is None or event is None:
        raise ToolInputError("active agent session and event required")
    return goal, event


def _requester_user_id(context: BrokerContext) -> uuid.UUID | None:
    if context.source == "owner_task" and context.workspace.actor.id:
        try:
            return uuid.UUID(context.workspace.actor.id)
        except ValueError:
            return None
    return None


def book(db: Session, clock: Clock, context: BrokerContext, args: BaseModel) -> dict[str, Any]:
    req = CalendarBookArgs.model_validate(args)
    thread = scoped_thread(
        db, context.workspace.workspace_id, context.account_id, context.thread_id, lock=True
    )
    if thread.handling_mode != "agent":
        raise ToolInputError("thread unavailable")

    conn = cal_queries.get_active_connection_for_workspace(db, context.workspace.workspace_id)
    if conn is None or conn.status not in ("connected", "degraded"):
        return {"ok": False, "error": "CALENDAR_NOT_CONNECTED"}

    tz, tz_name = _tz(db, context.workspace.workspace_id)
    duration = req.duration_minutes or conn.default_slot_duration_minutes
    start_utc = _local_dt(tz, req.local_date, req.local_time)
    end_utc = start_utc + timedelta(minutes=duration)

    day_start = datetime.combine(req.local_date, time(0, 0), tzinfo=tz).astimezone(UTC)
    day_end = datetime.combine(
        req.local_date + timedelta(days=1), time(0, 0), tzinfo=tz
    ).astimezone(UTC)
    avail = cal_ops.check_availability(
        get_session_factory(),
        clock,
        get_settings(),
        context.workspace.workspace_id,
        window_start=day_start,
        window_end=day_end,
        duration_minutes=duration,
        requested_start_at=start_utc,
        session=db,
    )
    if avail.requested_slot_available is not True:
        return {
            "ok": False,
            "error": "SLOT_UNAVAILABLE",
            "available_slots": [
                {
                    "local_date": s.local_date,
                    "local_start_time": s.local_start_time,
                    "local_end_time": s.local_end_time,
                }
                for s in avail.available_slots[:10]
            ],
        }

    customer_name = req.customer_name
    customer_contact = req.customer_contact
    if context.surface == "dm" and thread.dm_conversation_id:
        conv = db.get(Conversation, thread.dm_conversation_id)
        if conv is not None:
            customer_name = customer_name or conv.customer_handle or conv.customer_external_id
            customer_contact = customer_contact or (
                f"@{conv.customer_handle}" if conv.customer_handle else None
            )

    goal, event = _active_goal_and_event(db, thread)
    appt_id = new_id()
    intent_payload: dict[str, Any] = {
        "appointment_id": str(appt_id),
        "title": req.title.strip(),
        "description": req.description.strip() if req.description else None,
        "customer_name": customer_name,
        "customer_contact": customer_contact,
        "start_at": start_utc.isoformat(),
        "end_at": end_utc.isoformat(),
        "local_date": req.local_date.isoformat(),
        "local_time": req.local_time,
        "duration_minutes": duration,
        "timezone": tz_name,
        "conversation_id": str(thread.dm_conversation_id) if thread.dm_conversation_id else None,
        "customer_identity_id": (
            str(thread.customer_identity_id) if thread.customer_identity_id else None
        ),
        "created_by_source": context.source,
    }
    p_hash = payload_hash(intent_payload)
    target_ref = f"calendar:{conn.id}:{req.local_date.isoformat()}T{req.local_time}"

    action = admit_action(
        db,
        workspace_id=thread.workspace_id,
        account_id=thread.social_account_id,
        thread_id=thread.id,
        session_id=goal.id,
        source_event_id=event.id,
        action_type="calendar.book",
        target_ref=target_ref,
        semantic_slot=f"calendar.book:{req.local_date.isoformat()}:{req.local_time}",
        payload_hash=p_hash,
        clock=clock,
    )
    if action.content_intent is not None:
        return {"ok": True, **result(db, action)}

    action.payload_ref = appt_id
    action.content_intent = intent_payload
    action.ownership_generation = thread.ownership_generation

    decision = authorize_action(
        db,
        clock,
        context.workspace,
        action.id,
        source=context.source,
        requester_user_id=_requester_user_id(context),
        target_owned=True,
        visibility_allowed=True,
        claims_valid=True,
        quota_available=True,
    )
    if decision.kind == "automatic":
        queue_calendar_action(db, clock, action)
    elif decision.kind == "ask" and action.approval_id:
        approval = db.get(Approval, action.approval_id)
        if approval is not None:
            approval.summary = {
                **approval.summary,
                "title": req.title.strip(),
                "customer_name": customer_name,
                "local_date": req.local_date.isoformat(),
                "local_time": req.local_time,
                "duration_minutes": duration,
                "timezone": tz_name,
            }
    else:
        action.status = "cancelled"
        action.outcome_code = decision.reason
        return {"ok": False, "status": "blocked", "reason": decision.reason}

    db.flush()
    return {"ok": True, **result(db, action)}


def modify(db: Session, clock: Clock, context: BrokerContext, args: BaseModel) -> dict[str, Any]:
    req = CalendarModifyArgs.model_validate(args)
    thread = scoped_thread(
        db, context.workspace.workspace_id, context.account_id, context.thread_id, lock=True
    )
    if thread.handling_mode != "agent":
        raise ToolInputError("thread unavailable")

    appt = cal_queries.get_appointment_in_workspace(
        db, context.workspace.workspace_id, req.appointment_id, lock=True
    )
    if appt is None or appt.status != "scheduled":
        return {"ok": False, "error": "APPOINTMENT_NOT_FOUND"}
    if context.surface == "dm" and (
        thread.customer_identity_id is None
        or appt.customer_identity_id != thread.customer_identity_id
    ):
        return {"ok": False, "error": "APPOINTMENT_NOT_FOUND"}
    if appt.version != req.expected_version:
        return {"ok": False, "error": "VERSION_CONFLICT", "current_version": appt.version}

    conn = cal_queries.get_active_connection_for_workspace(db, context.workspace.workspace_id)
    if conn is None or conn.status not in ("connected", "degraded"):
        return {"ok": False, "error": "CALENDAR_NOT_CONNECTED"}

    tz, tz_name = _tz(db, context.workspace.workspace_id)
    action_type: Literal["calendar.reschedule", "calendar.cancel"] = (
        "calendar.reschedule" if req.operation == "reschedule" else "calendar.cancel"
    )

    intent_payload: dict[str, Any] = {
        "appointment_id": str(appt.id),
        "expected_version": appt.version,
        "title": appt.title,
        "customer_name": appt.customer_name,
        "timezone": tz_name,
        "reason": req.reason,
    }

    if req.operation == "reschedule":
        if req.new_local_date is None or req.new_local_time is None:
            raise ToolInputError("new_local_date and new_local_time required for reschedule")
        current_duration = int((appt.end_at - appt.start_at).total_seconds() // 60)
        duration = req.duration_minutes or max(15, current_duration)
        new_start_utc = _local_dt(tz, req.new_local_date, req.new_local_time)
        new_end_utc = new_start_utc + timedelta(minutes=duration)

        day_start = datetime.combine(req.new_local_date, time(0, 0), tzinfo=tz).astimezone(UTC)
        day_end = datetime.combine(
            req.new_local_date + timedelta(days=1), time(0, 0), tzinfo=tz
        ).astimezone(UTC)
        avail = cal_ops.check_availability(
            get_session_factory(),
            clock,
            get_settings(),
            context.workspace.workspace_id,
            window_start=day_start,
            window_end=day_end,
            duration_minutes=duration,
            requested_start_at=new_start_utc,
            session=db,
        )
        if avail.requested_slot_available is not True:
            return {
                "ok": False,
                "error": "SLOT_UNAVAILABLE",
                "available_slots": [
                    {
                        "local_date": s.local_date,
                        "local_start_time": s.local_start_time,
                        "local_end_time": s.local_end_time,
                    }
                    for s in avail.available_slots[:10]
                ],
            }
        intent_payload.update(
            {
                "new_start_at": new_start_utc.isoformat(),
                "new_end_at": new_end_utc.isoformat(),
                "local_date": req.new_local_date.isoformat(),
                "local_time": req.new_local_time,
                "duration_minutes": duration,
            }
        )
    else:
        ls = appt.start_at.astimezone(tz)
        intent_payload.update(
            {
                "local_date": ls.date().isoformat(),
                "local_time": ls.strftime("%H:%M"),
            }
        )

    goal, event = _active_goal_and_event(db, thread)
    p_hash = payload_hash(intent_payload)
    target_ref = f"appointment:{appt.id}:v{appt.version}"

    action = admit_action(
        db,
        workspace_id=thread.workspace_id,
        account_id=thread.social_account_id,
        thread_id=thread.id,
        session_id=goal.id,
        source_event_id=event.id,
        action_type=action_type,
        target_ref=target_ref,
        semantic_slot=f"{action_type}:{appt.id}:v{appt.version}",
        payload_hash=p_hash,
        clock=clock,
    )
    if action.content_intent is not None:
        return {"ok": True, **result(db, action)}

    action.payload_ref = appt.id
    action.content_intent = intent_payload
    action.ownership_generation = thread.ownership_generation

    decision = authorize_action(
        db,
        clock,
        context.workspace,
        action.id,
        source=context.source,
        requester_user_id=_requester_user_id(context),
        target_owned=True,
        visibility_allowed=True,
        claims_valid=True,
        quota_available=True,
    )
    if decision.kind == "automatic":
        queue_calendar_action(db, clock, action)
    elif decision.kind == "ask" and action.approval_id:
        approval = db.get(Approval, action.approval_id)
        if approval is not None:
            approval.summary = {
                **approval.summary,
                "title": appt.title,
                "customer_name": appt.customer_name,
                "local_date": intent_payload.get("local_date"),
                "local_time": intent_payload.get("local_time"),
                "timezone": tz_name,
            }
    else:
        action.status = "cancelled"
        action.outcome_code = decision.reason
        return {"ok": False, "status": "blocked", "reason": decision.reason}

    db.flush()
    return {"ok": True, **result(db, action)}


def render_calendar_reply(
    db: Session,
    clock: Clock,
    context: BrokerContext,
    thread: AgentThread,
    evidence: CalendarEvidence,
    language: Literal["tr", "en"],
) -> GroundedReply:
    tz, _ = _tz(db, context.workspace.workspace_id)
    if evidence.kind in ("booked", "rescheduled", "cancelled"):
        if evidence.appointment_id is None or evidence.appointment_version is None:
            return GroundedReply(errors=("CALENDAR_SOURCE_INVALID",))
        appt = cal_queries.get_appointment_in_workspace(
            db, context.workspace.workspace_id, evidence.appointment_id
        )
        if appt is None or appt.version != evidence.appointment_version:
            return GroundedReply(errors=("CALENDAR_SOURCE_INVALID",))
        if context.surface == "dm" and (
            thread.customer_identity_id is None
            or appt.customer_identity_id != thread.customer_identity_id
        ):
            return GroundedReply(errors=("CALENDAR_SOURCE_INVALID",))
        expected_status = "cancelled" if evidence.kind == "cancelled" else "scheduled"
        if appt.status != expected_status:
            return GroundedReply(errors=("CALENDAR_SOURCE_INVALID",))
        ls = appt.start_at.astimezone(tz)
        le = appt.end_at.astimezone(tz)
        d_str = ls.date().isoformat()
        s_str = ls.strftime("%H:%M")
        e_str = le.strftime("%H:%M")
        if evidence.kind == "booked":
            text = (
                f"Randevunuz {d_str} tarihinde {s_str}–{e_str} saatleri için "
                f"oluşturuldu ({appt.title})."
                if language == "tr"
                else (
                    f"Your appointment ({appt.title}) has been scheduled for "
                    f"{d_str} at {s_str}–{e_str}."
                )
            )
        elif evidence.kind == "rescheduled":
            text = (
                f"Randevunuz {d_str} tarihinde {s_str}–{e_str} saatlerine "
                f"güncellendi ({appt.title})."
                if language == "tr"
                else (
                    f"Your appointment ({appt.title}) has been rescheduled to "
                    f"{d_str} at {s_str}–{e_str}."
                )
            )
        else:
            text = (
                f"{d_str} tarihli {s_str} randevunuz ({appt.title}) iptal edildi."
                if language == "tr"
                else f"Your appointment ({appt.title}) on {d_str} at {s_str} has been cancelled."
            )
        if length_issue(text, max_bytes=1000):
            return GroundedReply(errors=("REPLY_LENGTH_INVALID",))
        return GroundedReply(text)

    if evidence.kind == "pending_approval":
        pending = db.scalar(
            select(AgentAction)
            .where(
                AgentAction.workspace_id == context.workspace.workspace_id,
                AgentAction.thread_id == thread.id,
                AgentAction.action_type.in_(CALENDAR_ACTIONS),
                AgentAction.status == "waiting_approval",
            )
            .order_by(AgentAction.created_at.desc())
            .limit(1)
        )
        if pending is None or not pending.content_intent:
            return GroundedReply(errors=("CALENDAR_SOURCE_INVALID",))
        d_str = str(pending.content_intent.get("local_date") or "")
        s_str = str(pending.content_intent.get("local_time") or "")
        text = (
            f"{d_str} tarihi saat {s_str} için randevu talebiniz alındı ve "
            "işletme onayına iletildi."
            if language == "tr"
            else (
                f"Your appointment request for {d_str} at {s_str} has been received "
                "and sent for owner approval."
            )
        )
        return GroundedReply(text)

    if evidence.kind == "available_slot":
        if not evidence.local_date or not evidence.local_start_time:
            return GroundedReply(errors=("CALENDAR_SOURCE_INVALID",))
        try:
            slot_date = date.fromisoformat(evidence.local_date)
        except ValueError:
            return GroundedReply(errors=("CALENDAR_SOURCE_INVALID",))
        req_start = _local_dt(tz, slot_date, evidence.local_start_time)
        day_start = datetime.combine(slot_date, time(0, 0), tzinfo=tz).astimezone(UTC)
        day_end = datetime.combine(slot_date + timedelta(days=1), time(0, 0), tzinfo=tz).astimezone(
            UTC
        )
        avail = cal_ops.check_availability(
            get_session_factory(),
            clock,
            get_settings(),
            context.workspace.workspace_id,
            window_start=day_start,
            window_end=day_end,
            requested_start_at=req_start,
            session=db,
        )
        if avail.requested_slot_available is not True:
            return GroundedReply(errors=("CALENDAR_SOURCE_INVALID",))
        text = (
            f"{evidence.local_date} tarihinde saat {evidence.local_start_time} "
            "randevu için müsaittir."
            if language == "tr"
            else (
                f"{evidence.local_date} at {evidence.local_start_time} is available "
                "for an appointment."
            )
        )
        return GroundedReply(text)

    return GroundedReply(errors=("CALENDAR_SOURCE_INVALID",))
