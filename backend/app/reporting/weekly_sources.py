"""Row sets of the weekly missed-customer report (D-03). No text inference or LLM calls.

They follow the registry's seven-column convention (``definitions.py``), so the number and the
drill-down list behind it run the very same SELECT. Only **real** records count (INV-09): a
simulated message, a message of a simulated conversation and a message on a mock account are all
left out, whichever flag a malformed row carries. Every query filters by ``workspace_id`` (INV-01).
The weekly metrics are a separate registry: the daily report's stored definitions are unchanged.
"""

from datetime import date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import Select, and_, exists, false, func, or_, select
from sqlalchemy.orm import Session, aliased

from app.core.context import WorkspaceContext
from app.inbox.models import Conversation, Message, ReplyDraft
from app.integrations.instagram.models import SocialAccount
from app.knowledge.models import BusinessFact, FactCandidate
from app.knowledge.values import WEEKDAYS
from app.reporting.definitions import Definition, _row


def usable_facts(session: Session, ctx: WorkspaceContext, now: datetime) -> list[BusinessFact]:
    today = now.astimezone(ZoneInfo(ctx.timezone)).date()
    contested = exists().where(
        FactCandidate.workspace_id == ctx.workspace_id,
        FactCandidate.fact_key == BusinessFact.key,
        FactCandidate.status == "pending",
        FactCandidate.relation == "contest",
    )
    return list(
        session.scalars(
            select(BusinessFact).where(
                BusinessFact.workspace_id == ctx.workspace_id,
                BusinessFact.status == "verified",
                or_(BusinessFact.valid_from.is_(None), BusinessFact.valid_from <= today),
                or_(BusinessFact.valid_until.is_(None), BusinessFact.valid_until >= today),
                ~contested,
            )
        )
    )


def hours_fact(session: Session, ctx: WorkspaceContext, now: datetime) -> BusinessFact | None:
    return next(
        (
            f
            for f in usable_facts(session, ctx, now)
            if f.key == "hours.weekly" and f.value_type == "weekly_hours"
        ),
        None,
    )


def real_message(message: Any, ctx: WorkspaceContext) -> Any:
    """Check all provenance boundaries, including malformed false flags on mock accounts."""
    return and_(
        message.workspace_id == ctx.workspace_id,
        message.is_simulated.is_(False),
        message.is_deleted.is_(False),
        exists().where(
            Conversation.workspace_id == ctx.workspace_id,
            Conversation.id == message.conversation_id,
            Conversation.is_simulated.is_(False),
        ),
        exists().where(
            SocialAccount.workspace_id == ctx.workspace_id,
            SocialAccount.id == message.social_account_id,
            SocialAccount.provider_kind != "mock",
        ),
    )


def _local_instant(day: date, value: str, zone: ZoneInfo) -> datetime:
    """The instant of wall-clock ``HH:MM`` (or ``24:00``) on ``day`` in ``zone`` (INV-19)."""
    hour, minute = map(int, value.split(":"))
    if hour == 24:
        return datetime.combine(day + timedelta(days=1), time.min, zone)
    return datetime.combine(day, time(hour, minute), zone)


def outside_hours(
    session: Session,
    ctx: WorkspaceContext,
    start: datetime,
    end: datetime,
    now: datetime,
    timestamp: Any,
) -> Any:
    """True for a ``timestamp`` outside the verified weekly opening hours, in the workspace
    timezone. A range opens at its opening time and ends before its closing time. A workspace
    without a usable hours fact has no "outside hours" (the caller reports hours as missing)."""
    fact = hours_fact(session, ctx, now)
    if fact is None:
        return false()
    zone = ZoneInfo(ctx.timezone)
    day = start.astimezone(zone).date()
    last = end.astimezone(zone).date()
    exceptions = {e["date"]: e for e in fact.value.get("exceptions", [])}
    intervals = []
    while day <= last:
        exception = exceptions.get(day.isoformat())
        if exception is not None:
            ranges = [] if exception.get("closed", True) else exception.get("ranges", [])
        else:
            ranges = fact.value.get(WEEKDAYS[day.weekday()], [])
        for opens, closes in ranges:
            intervals.append(
                and_(
                    timestamp >= _local_instant(day, opens, zone),
                    timestamp < _local_instant(day, closes, zone),
                )
            )
        day += timedelta(days=1)
    return ~or_(false(), *intervals)


def after_hours(
    session: Session, ctx: WorkspaceContext, start: datetime, end: datetime, now: datetime
) -> Select[Any]:
    return select(
        *_row(
            "message",
            Message.id,
            Message.provider_timestamp,
            Message.is_simulated,
            Message.conversation_id,
        )
    ).where(
        real_message(Message, ctx),
        Message.direction == "inbound",
        Message.provider_timestamp >= start,
        Message.provider_timestamp < end,
        outside_hours(session, ctx, start, end, now, Message.provider_timestamp),
    )


def first_replies(
    session: Session, ctx: WorkspaceContext, start: datetime, end: datetime, now: datetime
) -> Select[Any]:
    """First inbound in this period per conversation, to first real reply before period end."""
    incoming = (
        select(Message.conversation_id, func.min(Message.provider_timestamp).label("at"))
        .where(
            real_message(Message, ctx),
            Message.direction == "inbound",
            Message.provider_timestamp >= start,
            Message.provider_timestamp < end,
        )
        .group_by(Message.conversation_id)
        .subquery()
    )
    reply = (
        select(func.min(Message.provider_timestamp))
        .where(
            real_message(Message, ctx),
            Message.conversation_id == incoming.c.conversation_id,
            Message.direction == "outbound",
            Message.provider_timestamp >= incoming.c.at,
            Message.provider_timestamp < end,
        )
        .correlate(incoming)
        .scalar_subquery()
    )
    return select(
        *_row(
            "conversation",
            incoming.c.conversation_id,
            incoming.c.at,
            false(),
            incoming.c.conversation_id,
            measure=func.extract("epoch", reply - incoming.c.at) / 60,
        )
    ).where(reply.is_not(None))


def unanswered(
    session: Session, ctx: WorkspaceContext, start: datetime, end: datetime, now: datetime
) -> Select[Any]:
    incoming = (
        select(Message.conversation_id, func.max(Message.provider_timestamp).label("at"))
        .where(
            real_message(Message, ctx),
            Message.direction == "inbound",
            Message.provider_timestamp >= start,
            Message.provider_timestamp < end,
        )
        .group_by(Message.conversation_id)
        .subquery()
    )
    answered = exists().where(
        real_message(Message, ctx),
        Message.conversation_id == incoming.c.conversation_id,
        Message.direction == "outbound",
        Message.provider_timestamp >= incoming.c.at,
        Message.provider_timestamp < end,
    )
    return select(
        *_row(
            "conversation",
            incoming.c.conversation_id,
            incoming.c.at,
            false(),
            incoming.c.conversation_id,
        )
    ).where(~answered)


def answered_questions(
    session: Session,
    ctx: WorkspaceContext,
    start: datetime,
    end: datetime,
    now: datetime,
    *,
    after: bool = False,
) -> Select[Any]:
    """One covered inbound question, with persisted intent and an actually sent assistant reply."""
    outgoing = aliased(Message)
    sent = (
        exists()
        .where(
            real_message(outgoing, ctx),
            outgoing.direction == "outbound",
            outgoing.conversation_id == Message.conversation_id,
            outgoing.reply_draft_id == ReplyDraft.id,
            outgoing.provider_timestamp >= Message.provider_timestamp,
            outgoing.provider_timestamp < end,
        )
        .correlate(Message, ReplyDraft)
    )
    answered = exists().where(
        ReplyDraft.workspace_id == ctx.workspace_id,
        ReplyDraft.conversation_id == Message.conversation_id,
        ReplyDraft.covers_through_message_id == Message.id,
        ReplyDraft.is_simulated.is_(False),
        ReplyDraft.status == "sent",
        ReplyDraft.source.in_(("ai", "approved_answer")),
        ReplyDraft.intent.in_(("pricing",) if after else ("pricing", "booking")),
        sent,
    )
    query = select(
        *_row(
            "message",
            Message.id,
            Message.provider_timestamp,
            Message.is_simulated,
            Message.conversation_id,
        )
    ).where(
        real_message(Message, ctx),
        Message.direction == "inbound",
        Message.provider_timestamp >= start,
        Message.provider_timestamp < end,
        answered,
    )
    if after:
        query = query.where(
            outside_hours(session, ctx, start, end, now, Message.provider_timestamp)
        )
    return query


def after_hours_prices(
    session: Session, ctx: WorkspaceContext, start: datetime, end: datetime, now: datetime
) -> Select[Any]:
    return answered_questions(session, ctx, start, end, now, after=True)


WEEKLY_DEFINITIONS: tuple[Definition, ...] = (
    Definition("after_hours_dms", "period", "missed_customers", False, "count", after_hours),
    Definition(
        "first_reply_median_minutes",
        "period",
        "missed_customers",
        False,
        "median",
        first_replies,
    ),
    Definition(
        "unanswered_conversations", "period", "missed_customers", False, "count", unanswered
    ),
    Definition(
        "answered_questions", "period", "missed_customers", False, "count", answered_questions
    ),
    Definition(
        "after_hours_price_answers",
        "period",
        "missed_customers",
        False,
        "count",
        after_hours_prices,
    ),
)
WEEKLY_BY_KEY: dict[str, Definition] = {d.key: d for d in WEEKLY_DEFINITIONS}
