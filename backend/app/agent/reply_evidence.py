"""Scoped customer evidence for one DM response obligation.

The model sees multiple inbound messages, so policy must not reduce them to the
last message or require every historical message to have an Agent event. Message
history supplies unanswered legacy/human-handled context too. Events retain their
response ownership boundary; derived media cannot allocate a second response slot.
"""

import uuid
from dataclasses import dataclass

from sqlalchemy import String, and_, cast, exists, func, or_, select, tuple_
from sqlalchemy.orm import Session

from app.agent.models import AgentEvent, AgentThread
from app.core.clock import Clock
from app.core.context import WorkspaceContext
from app.inbox.models import Message, MessageImageDescription, MessageTranscript, ReplyDraft

MESSAGE_SOURCES = ("message", "customer_message", "inbound_message")
MAX_RESPONSE_MESSAGES = 100


def escalation_keywords(db: Session, clock: Clock, ctx: WorkspaceContext) -> list[str]:
    from app.agent.knowledge import usable_predicate
    from app.knowledge.models import BusinessFact

    row = db.scalar(
        select(BusinessFact).where(
            usable_predicate(ctx, clock), BusinessFact.key == "escalation.keywords"
        )
    )
    return [str(item) for item in row.value.get("items", [])] if row else []


@dataclass(frozen=True)
class ReplyEvidence:
    text: str
    message_ids: tuple[uuid.UUID, ...]
    image_injection: bool = False
    media_pending: bool = False
    truncated: bool = False


def message_cursor(db: Session, thread: AgentThread, message_id: uuid.UUID) -> int | None:
    return db.scalar(
        select(func.max(AgentEvent.cursor)).where(
            AgentEvent.workspace_id == thread.workspace_id,
            AgentEvent.social_account_id == thread.social_account_id,
            AgentEvent.thread_id == thread.id,
            AgentEvent.source_kind.in_(MESSAGE_SOURCES),
            AgentEvent.source_id == str(message_id),
        )
    )


def latest_customer_message(db: Session, thread: AgentThread) -> Message | None:
    return db.scalar(
        select(Message)
        .join(AgentEvent, AgentEvent.source_id == cast(Message.id, String))
        .where(
            Message.workspace_id == thread.workspace_id,
            Message.social_account_id == thread.social_account_id,
            Message.conversation_id == thread.dm_conversation_id,
            Message.direction == "inbound",
            Message.is_deleted.is_(False),
            AgentEvent.workspace_id == thread.workspace_id,
            AgentEvent.thread_id == thread.id,
            AgentEvent.source_kind.in_(MESSAGE_SOURCES),
        )
        .order_by(AgentEvent.cursor.desc())
        .limit(1)
    )


def response_evidence(
    db: Session, thread: AgentThread, through_message_id: uuid.UUID
) -> ReplyEvidence:
    anchor = db.scalar(
        select(Message).where(
            Message.workspace_id == thread.workspace_id,
            Message.social_account_id == thread.social_account_id,
            Message.conversation_id == thread.dm_conversation_id,
            Message.id == through_message_id,
            Message.direction == "inbound",
            Message.is_deleted.is_(False),
        )
    )
    if anchor is None:
        return ReplyEvidence("", ())
    end = message_cursor(db, thread, anchor.id)
    ids = [anchor.id]
    truncated = False
    if end is not None:
        last_answered = db.scalar(
            select(func.max(AgentEvent.cursor))
            .join(
                ReplyDraft,
                cast(ReplyDraft.covers_through_message_id, String) == AgentEvent.source_id,
            )
            .where(
                AgentEvent.workspace_id == thread.workspace_id,
                AgentEvent.social_account_id == thread.social_account_id,
                AgentEvent.thread_id == thread.id,
                AgentEvent.source_kind.in_(MESSAGE_SOURCES),
                AgentEvent.cursor < end,
                ReplyDraft.workspace_id == thread.workspace_id,
                ReplyDraft.conversation_id == thread.dm_conversation_id,
                ReplyDraft.status == "sent",
            )
        )
        sources = list(
            db.scalars(
                select(AgentEvent.source_id)
                .where(
                    AgentEvent.workspace_id == thread.workspace_id,
                    AgentEvent.social_account_id == thread.social_account_id,
                    AgentEvent.thread_id == thread.id,
                    AgentEvent.source_kind.in_(MESSAGE_SOURCES),
                    AgentEvent.cursor > (last_answered or 0),
                    AgentEvent.cursor <= end,
                )
                .order_by(AgentEvent.cursor)
                .limit(MAX_RESPONSE_MESSAGES + 1)
            )
        )
        truncated = len(sources) > MAX_RESPONSE_MESSAGES
        ids = []
        for source in sources[:MAX_RESPONSE_MESSAGES]:
            try:
                source_id = uuid.UUID(source or "")
            except ValueError:
                truncated = True
                continue
            if source_id not in ids:
                ids.append(source_id)
        if anchor.id not in ids:
            ids.append(anchor.id)
    # Native/manual replies discharge earlier customer work too. Use the same
    # chronological tuple as takeover/release so a resolved old complaint does
    # not constrain a later independent question forever.
    anchor_order = (anchor.provider_timestamp, anchor.created_at, anchor.id)
    outbound = db.scalar(
        select(Message)
        .where(
            Message.workspace_id == thread.workspace_id,
            Message.social_account_id == thread.social_account_id,
            Message.conversation_id == thread.dm_conversation_id,
            Message.direction == "outbound",
            Message.is_deleted.is_(False),
            tuple_(Message.provider_timestamp, Message.created_at, Message.id) < anchor_order,
        )
        .order_by(Message.provider_timestamp.desc(), Message.created_at.desc(), Message.id.desc())
        .limit(1)
    )
    # A sent legacy draft can cover messages with no Agent event. Keep that
    # discharge boundary even if its outbound echo/message has been removed.
    covered = db.scalar(
        select(Message)
        .join(ReplyDraft, ReplyDraft.covers_through_message_id == Message.id)
        .where(
            Message.workspace_id == thread.workspace_id,
            Message.social_account_id == thread.social_account_id,
            Message.conversation_id == thread.dm_conversation_id,
            Message.direction == "inbound",
            tuple_(Message.provider_timestamp, Message.created_at, Message.id) < anchor_order,
            ReplyDraft.workspace_id == thread.workspace_id,
            ReplyDraft.conversation_id == thread.dm_conversation_id,
            ReplyDraft.status == "sent",
        )
        .order_by(Message.provider_timestamp.desc(), Message.created_at.desc(), Message.id.desc())
        .limit(1)
    )
    boundaries = [
        (row.provider_timestamp, row.created_at, row.id)
        for row in (outbound, covered)
        if row is not None
    ]
    # Supplement the event-owned obligation with scoped message history that
    # predates Agent adoption/release. Do not admit messages owned by a later
    # Agent event just because their provider timestamp arrived out of order.
    has_message_event = exists().where(
        AgentEvent.workspace_id == thread.workspace_id,
        AgentEvent.social_account_id == thread.social_account_id,
        AgentEvent.thread_id == thread.id,
        AgentEvent.source_kind.in_(MESSAGE_SOURCES),
        AgentEvent.source_id == cast(Message.id, String),
    )
    message_query = select(Message).where(
        Message.workspace_id == thread.workspace_id,
        Message.social_account_id == thread.social_account_id,
        Message.conversation_id == thread.dm_conversation_id,
        Message.direction == "inbound",
        Message.is_deleted.is_(False),
        or_(
            Message.id.in_(ids),
            and_(
                ~has_message_event,
                tuple_(Message.provider_timestamp, Message.created_at, Message.id) <= anchor_order,
            ),
        ),
    )
    if boundaries:
        message_query = message_query.where(
            tuple_(Message.provider_timestamp, Message.created_at, Message.id) > max(boundaries)
        )
    messages = list(
        db.scalars(
            message_query.order_by(
                Message.provider_timestamp, Message.created_at, Message.id
            ).limit(MAX_RESPONSE_MESSAGES + 1)
        )
    )
    truncated = truncated or len(messages) > MAX_RESPONSE_MESSAGES
    messages = messages[:MAX_RESPONSE_MESSAGES]
    if all(row.id != anchor.id for row in messages):
        messages.append(anchor)
    ids = [row.id for row in messages]
    transcripts = list(
        db.scalars(
            select(MessageTranscript).where(
                MessageTranscript.workspace_id == thread.workspace_id,
                MessageTranscript.message_id.in_(ids),
            )
        )
    )
    images = list(
        db.scalars(
            select(MessageImageDescription).where(
                MessageImageDescription.workspace_id == thread.workspace_id,
                MessageImageDescription.message_id.in_(ids),
            )
        )
    )
    parts = [row.text for row in messages if row.text]
    parts.extend(row.text for row in transcripts if row.status == "succeeded" and row.text)
    parts.extend(row.description for row in images if row.status == "succeeded" and row.description)
    parts.extend(
        row.visible_text for row in images if row.status == "succeeded" and row.visible_text
    )
    if truncated:
        # Explicitly unknown input makes the classifier fail closed, instead of
        # ignoring a portion of a large unanswered conversation.
        parts.append("[additional unanswered customer messages]")
    return ReplyEvidence(
        "\n".join(parts),
        tuple(ids),
        image_injection=any(row.injection_suspected for row in images),
        media_pending=any(row.status == "pending" for row in transcripts)
        or any(row.status == "pending" for row in images),
        truncated=truncated,
    )
