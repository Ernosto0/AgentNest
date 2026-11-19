"""Call-back conversations, not CRM state. Read-only, workspace-local periods.

Legacy intents qualify regardless of draft status. Agent drafts additionally qualify
through persisted pricing-fact impact references (the missed report's PRICE_CATEGORY).
No inference from customer text, human handling, memory, or an invented resolved flag.
"""

import unicodedata
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import Select, String, case, exists, func, literal, or_, select, true
from sqlalchemy.dialects.postgresql import distinct_on
from sqlalchemy.orm import Session

from app.agent.models import AgentAction, AgentEvent, AgentThread
from app.core.clock import Clock
from app.core.context import WorkspaceContext
from app.core.errors import AppError
from app.inbox.models import (
    Conversation,
    Message,
    MessageImageDescription,
    MessageTranscript,
    ReplyDraft,
)
from app.integrations.calendar.models import CalendarAppointment
from app.knowledge.models import BusinessFact, FactReference
from app.operations.models import Operation
from app.reporting.links import Link, conversation_link
from app.reporting.missed_customers import PRICE_CATEGORY
from app.reporting.periods import day_bounds, local_date_of
from app.reporting.weekly_sources import real_message

LEAD_INTENTS = ("pricing", "booking")
MAX_EXPORT_ROWS = 5000


@dataclass(frozen=True)
class Lead:
    workspace_id: uuid.UUID
    conversation_id: uuid.UUID
    customer_handle: str | None
    last_question_at: datetime
    last_question: str | None
    intent: str
    link: Link
    # Preserve the initial control character for CSV formula escaping before cleaning.
    raw_question: str | None = None


@dataclass(frozen=True)
class LeadPage:
    items: list[Lead]
    total: int
    period_from: date
    period_to: date
    timezone: str


def period(
    clock: Clock, ctx: WorkspaceContext, from_date: date | None, to_date: date | None
) -> tuple[date, date]:
    today = local_date_of(clock.now(), ctx.timezone)
    start, end = from_date or today - timedelta(days=29), to_date or today
    for field, code, invalid in (
        ("to", "to_before_from", end < start),
        ("to", "in_future", end > today),
        ("from", "period_too_long", (end - start).days + 1 > 92),
    ):
        if invalid:
            raise AppError(
                "VALIDATION_FAILED", errors=[{"field": field, "code": code, "params": {}}]
            )
    return start, end


def clean_question(value: str | None) -> str | None:
    if value is None:
        return None
    value = "".join(" " if unicodedata.category(c).startswith("C") else c for c in value)
    return value if len(value) <= 300 else value[:299] + "…"


def lead_rows(ctx: WorkspaceContext, start: datetime, end: datetime) -> Select[Any]:
    """One row per conversation; first question controls conversion, last controls display."""
    agent_price = exists().where(
        FactReference.workspace_id == ctx.workspace_id,
        FactReference.referrer_type == "reply_draft",
        FactReference.referrer_id == ReplyDraft.id,
        BusinessFact.workspace_id == ctx.workspace_id,
        BusinessFact.id == FactReference.fact_id,
        BusinessFact.category == PRICE_CATEGORY,
    )
    draft_pairs = (
        select(
            Message.conversation_id,
            Message.id.label("message_id"),
            Message.provider_timestamp.label("at"),
            Message.text,
            case(
                (ReplyDraft.intent == "booking", literal("booking")), else_=literal("pricing")
            ).label("intent"),
        )
        .join(
            ReplyDraft,
            (ReplyDraft.covers_through_message_id == Message.id)
            & (ReplyDraft.conversation_id == Message.conversation_id)
            & (ReplyDraft.workspace_id == ctx.workspace_id),
        )
        .where(
            real_message(Message, ctx),
            Message.direction == "inbound",
            Message.provider_timestamp >= start,
            Message.provider_timestamp < end,
            ReplyDraft.is_simulated.is_(False),
            or_(
                ReplyDraft.intent.in_(LEAD_INTENTS),
                (ReplyDraft.origin == "agent") & agent_price,
            ),
        )
    )
    has_booking_action = exists().where(
        AgentThread.workspace_id == ctx.workspace_id,
        AgentThread.dm_conversation_id == Message.conversation_id,
        AgentAction.workspace_id == ctx.workspace_id,
        AgentAction.thread_id == AgentThread.id,
        AgentAction.action_type.in_(("calendar.book", "calendar.reschedule")),
        or_(
            exists().where(
                AgentEvent.workspace_id == ctx.workspace_id,
                AgentEvent.id == AgentAction.initiating_event_id,
                or_(
                    (AgentEvent.source_kind == "message")
                    & (AgentEvent.source_id == func.cast(Message.id, String)),
                    exists().where(
                        MessageTranscript.workspace_id == ctx.workspace_id,
                        func.cast(MessageTranscript.id, String) == AgentEvent.source_id,
                        MessageTranscript.message_id == Message.id,
                    ),
                    exists().where(
                        MessageImageDescription.workspace_id == ctx.workspace_id,
                        func.cast(MessageImageDescription.id, String) == AgentEvent.source_id,
                        MessageImageDescription.message_id == Message.id,
                    ),
                ),
            ),
            (
                AgentAction.initiating_event_id.is_(None)
                & (Message.provider_timestamp <= AgentAction.created_at)
            ),
        ),
    )
    action_pairs = select(
        Message.conversation_id,
        Message.id.label("message_id"),
        Message.provider_timestamp.label("at"),
        Message.text,
        literal("booking").label("intent"),
    ).where(
        real_message(Message, ctx),
        Message.direction == "inbound",
        Message.provider_timestamp >= start,
        Message.provider_timestamp < end,
        has_booking_action,
    )
    pairs = draft_pairs.union(action_pairs).cte("qualifying_questions")
    first = (
        select(pairs.c.conversation_id, func.min(pairs.c.at).label("first_at"))
        .group_by(pairs.c.conversation_id)
        .cte("first_questions")
    )
    last = (
        select(pairs)
        .ext(distinct_on(pairs.c.conversation_id))
        .order_by(
            pairs.c.conversation_id,
            pairs.c.at.desc(),
            pairs.c.message_id.desc(),
            (pairs.c.intent == "booking").desc(),
        )
        .cte("last_questions")
    )
    unconfirmed_operation = exists().where(
        Operation.workspace_id == ctx.workspace_id,
        Operation.operation_type == "calendar_create_event",
        Operation.subject_id == CalendarAppointment.id,
        Operation.status != "succeeded",
    )
    unconfirmed_agent_booking = exists().where(
        AgentAction.workspace_id == ctx.workspace_id,
        AgentAction.action_type == "calendar.book",
        AgentAction.payload_ref == CalendarAppointment.id,
        AgentAction.status != "succeeded",
    )
    converted = exists().where(
        CalendarAppointment.workspace_id == ctx.workspace_id,
        CalendarAppointment.conversation_id == first.c.conversation_id,
        CalendarAppointment.status != "cancelled",
        CalendarAppointment.created_at >= first.c.first_at,
        ~unconfirmed_operation,
        ~unconfirmed_agent_booking,
    )
    return (
        select(last, Conversation.customer_handle)
        .join(first, first.c.conversation_id == last.c.conversation_id)
        .join(
            Conversation,
            (Conversation.id == last.c.conversation_id)
            & (Conversation.workspace_id == ctx.workspace_id),
        )
        .where(~converted)
    )


def list_leads(
    session: Session,
    clock: Clock,
    ctx: WorkspaceContext,
    from_date: date | None,
    to_date: date | None,
    *,
    limit: int,
    offset: int,
) -> LeadPage:
    start, end = period(clock, ctx, from_date, to_date)
    rows = lead_rows(ctx, day_bounds(start, ctx.timezone)[0], day_bounds(end, ctx.timezone)[1]).cte(
        "leads"
    )
    page = (
        select(rows)
        .order_by(rows.c.at.desc(), rows.c.conversation_id.desc())
        .limit(limit)
        .offset(offset)
        .subquery()
    )
    count = select(func.count().label("total")).select_from(rows).subquery()
    result = session.execute(
        select(count.c.total, page)
        .select_from(count.outerjoin(page, true()))
        .order_by(page.c.at.desc(), page.c.conversation_id.desc())
    ).all()
    items = [
        Lead(
            ctx.workspace_id,
            r.conversation_id,
            r.customer_handle,
            r.at,
            clean_question(r.text),
            r.intent,
            conversation_link(ctx.workspace_id, r.conversation_id),
            r.text,
        )
        for r in result
        if r.conversation_id is not None
    ]
    return LeadPage(items, result[0].total, start, end, ctx.timezone)


def all_leads(
    session: Session,
    clock: Clock,
    ctx: WorkspaceContext,
    from_date: date | None,
    to_date: date | None,
    *,
    cap: int = MAX_EXPORT_ROWS,
) -> tuple[LeadPage, bool]:
    page = list_leads(session, clock, ctx, from_date, to_date, limit=cap, offset=0)
    return page, page.total > len(page.items)
