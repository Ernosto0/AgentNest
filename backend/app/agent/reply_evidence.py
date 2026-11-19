"""Scoped customer evidence for one DM response obligation.

The model sees multiple inbound messages, so policy must not reduce them to the
last message. Events define the response boundary; derived media belongs to its
original message and cannot allocate a second response slot after it was sent.
"""

import uuid
from dataclasses import dataclass

from sqlalchemy import String, cast, func, select, tuple_
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
    messages = list(
        db.scalars(
            select(Message).where(
                Message.workspace_id == thread.workspace_id,
                Message.social_account_id == thread.social_account_id,
                Message.conversation_id == thread.dm_conversation_id,
                Message.id.in_(ids),
                Message.direction == "inbound",
                Message.is_deleted.is_(False),
            )
        )
    )
    # Native/manual replies discharge earlier customer work too. Use the same
    # chronological tuple as takeover/release so a resolved old complaint does
    # not constrain a later independent question forever.
    outbound = db.scalar(
        select(Message)
        .where(
            Message.workspace_id == thread.workspace_id,
            Message.social_account_id == thread.social_account_id,
            Message.conversation_id == thread.dm_conversation_id,
            Message.direction == "outbound",
            Message.is_deleted.is_(False),
            tuple_(Message.provider_timestamp, Message.created_at, Message.id)
            < (anchor.provider_timestamp, anchor.created_at, anchor.id),
        )
        .order_by(Message.provider_timestamp.desc(), Message.created_at.desc(), Message.id.desc())
        .limit(1)
    )
    if outbound is not None:
        boundary = (outbound.provider_timestamp, outbound.created_at, outbound.id)
        messages = [
            row for row in messages if (row.provider_timestamp, row.created_at, row.id) > boundary
        ]
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
