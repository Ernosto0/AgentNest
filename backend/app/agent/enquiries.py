"""Persist minimal Agent enquiry evidence on its original customer message.

The enum is reporting evidence only, never authority or conversion evidence. No customer
text is copied. A message keeps the same signal across a tool retry or media completion;
normal Message provenance, RLS, deletion and retention govern its lifetime.
"""

import uuid
from datetime import timedelta
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent.models import AccountAgent, AgentEvent, AgentThread
from app.agent.policy import Topic, detect_inbound_topics
from app.agent.tools.broker import BrokerContext
from app.core.clock import Clock
from app.core.config import get_settings
from app.inbox.models import Message, MessageImageDescription, MessageTranscript

EnquiryIntent = Literal["pricing", "booking"]


def record_message_enquiry(
    db: Session,
    clock: Clock,
    *,
    workspace_id: uuid.UUID,
    account_id: uuid.UUID,
    message_id: uuid.UUID,
    text: str | None = None,
    intent: EnquiryIntent | None = None,
) -> None:
    """Record a scoped customer enquiry before reply/action admission can fail."""
    controller = db.scalar(
        select(AccountAgent)
        .where(
            AccountAgent.workspace_id == workspace_id,
            AccountAgent.social_account_id == account_id,
            AccountAgent.controller_mode == "agent",
        )
        .with_for_update()
    )
    if controller is None:
        return
    # Account-first locking matches the controller boundary and serializes the per-message
    # merge, so concurrent price/transcript/tool evidence cannot overwrite a booking label.
    message = db.scalar(
        select(Message)
        .where(
            Message.workspace_id == workspace_id,
            Message.social_account_id == account_id,
            Message.id == message_id,
            Message.direction == "inbound",
            Message.sender_kind == "customer",
            Message.is_deleted.is_(False),
        )
        .with_for_update()
    )
    if message is None:
        return
    if not message.text and not message.attachments:
        return  # an erased/empty source cannot regain a reporting label from a late tool call
    if message.provider_timestamp < clock.now() - timedelta(
        days=get_settings().retention_message_text_days
    ):
        return  # late media/tool completion must not restore expired personal metadata
    if intent is None:
        topics, _, injection = detect_inbound_topics(text if text is not None else message.text)
        if injection:
            return
        if Topic.BOOKING_MUTATION in topics:
            intent = "booking"
        elif Topic.PRICING in topics:
            intent = "pricing"
    if intent is not None and message.agent_enquiry_intent != "booking":
        # Booking wins if a later transcript adds booking to an existing price question.
        message.agent_enquiry_intent = intent


def record_thread_enquiry(
    db: Session,
    clock: Clock,
    context: BrokerContext,
    *,
    intent: EnquiryIntent = "booking",
) -> None:
    """A scoped calendar tool request evidences enquiry before availability/action failure.

    Owner tasks and unrelated/latest-message guesses cannot create customer leads. Resolve
    only the current thread's persisted customer or media event to its original message.
    """
    if context.surface != "dm" or context.source != "customer":
        return
    thread = db.scalar(
        select(AgentThread).where(
            AgentThread.workspace_id == context.workspace.workspace_id,
            AgentThread.social_account_id == context.account_id,
            AgentThread.id == context.thread_id,
            AgentThread.surface == "dm",
        )
    )
    if thread is None:
        return
    event = db.scalar(
        select(AgentEvent).where(
            AgentEvent.workspace_id == thread.workspace_id,
            AgentEvent.social_account_id == thread.social_account_id,
            AgentEvent.thread_id == thread.id,
            AgentEvent.cursor == thread.event_cursor,
        )
    )
    if event is None or not event.source_id:
        return
    try:
        source_id = uuid.UUID(event.source_id)
    except ValueError:
        return
    message_id: uuid.UUID | None = None
    if event.kind == "customer_message" and event.source_kind in {
        "message",
        "customer_message",
        "inbound_message",
    }:
        message_id = source_id
    elif event.source_kind in {"message_transcript", "message_image_description"}:
        model = (
            MessageTranscript
            if event.source_kind == "message_transcript"
            else MessageImageDescription
        )
        message_id = db.scalar(
            select(model.message_id).where(
                model.workspace_id == thread.workspace_id,
                model.id == source_id,
            )
        )
    if message_id is None:
        return
    source = db.scalar(
        select(Message.id).where(
            Message.workspace_id == thread.workspace_id,
            Message.social_account_id == thread.social_account_id,
            Message.conversation_id == thread.dm_conversation_id,
            Message.id == message_id,
        )
    )
    if source is not None:
        record_message_enquiry(
            db,
            clock,
            workspace_id=thread.workspace_id,
            account_id=thread.social_account_id,
            message_id=source,
            intent=intent,
        )
