"""Replan derived media within its original customer response obligation."""

from sqlalchemy import String, cast, select, tuple_
from sqlalchemy.orm import Session

from app.agent.models import AgentAction, AgentEvent, AgentThread
from app.agent.reply_evidence import (
    MESSAGE_SOURCES,
    latest_customer_message,
    message_cursor,
    response_evidence,
)
from app.agent.repository import record_thread_event, scoped_account, scoped_thread
from app.audit.service import record
from app.core.clock import Clock
from app.inbox.models import Conversation, Message, ReplyDraft
from app.operations.models import Operation


def wake_for_media(
    db: Session,
    clock: Clock,
    *,
    message: Message,
    thread: AgentThread,
    kind: str,
    source_kind: str,
    source_key: str,
    source_id: str,
) -> bool:
    """Wake once only while the original message still needs a response.

    Account-first locks serialize this decision with customer events and the
    send executor. In-flight/uncertain sends keep their reservation. A finished
    response or a newer customer event cannot be reopened by slow media work.
    Pending unsent drafts are retired before the new media cursor is admitted;
    approval cleanup uses its normal deferred lock ordering.
    """
    account = scoped_account(db, message.workspace_id, message.social_account_id, lock=True)
    thread = scoped_thread(
        db, message.workspace_id, message.social_account_id, thread.id, lock=True
    )
    if (
        account.controller_mode != "agent"
        or account.state not in {"active", "paused"}
        or thread.controller_epoch != account.controller_epoch
        or thread.handling_mode != "agent"
    ):
        return False
    if db.scalar(
        select(AgentEvent.id).where(
            AgentEvent.workspace_id == message.workspace_id,
            AgentEvent.thread_id == thread.id,
            AgentEvent.source_kind == source_kind,
            AgentEvent.source_key == source_key,
        )
    ):
        return False
    original_cursor = message_cursor(db, thread, message.id)
    anchor = latest_customer_message(db, thread)
    if original_cursor is None or anchor is None:
        return False
    evidence = response_evidence(db, thread, anchor.id)
    if message.id not in evidence.message_ids:
        return False
    # A native/manual response also discharges the obligation, without an
    # Agent ReplyDraft that could be found by the sent-draft check below.
    native_answer = db.scalar(
        select(Message.id)
        .where(
            Message.workspace_id == thread.workspace_id,
            Message.social_account_id == thread.social_account_id,
            Message.conversation_id == thread.dm_conversation_id,
            Message.direction == "outbound",
            Message.is_deleted.is_(False),
            tuple_(Message.provider_timestamp, Message.created_at, Message.id)
            >= (anchor.provider_timestamp, anchor.created_at, anchor.id),
        )
        .limit(1)
    )
    if native_answer is not None:
        return False
    already_sent = db.scalar(
        select(ReplyDraft.id)
        .join(
            AgentEvent, AgentEvent.source_id == cast(ReplyDraft.covers_through_message_id, String)
        )
        .where(
            ReplyDraft.workspace_id == message.workspace_id,
            ReplyDraft.conversation_id == message.conversation_id,
            ReplyDraft.status == "sent",
            AgentEvent.workspace_id == message.workspace_id,
            AgentEvent.thread_id == thread.id,
            AgentEvent.source_kind.in_(MESSAGE_SOURCES),
            AgentEvent.cursor >= original_cursor,
        )
        .limit(1)
    )
    uncertain = db.scalar(
        select(AgentAction.id)
        .outerjoin(ReplyDraft, ReplyDraft.agent_action_id == AgentAction.id)
        .outerjoin(Operation, Operation.id == AgentAction.operation_id)
        .where(
            AgentAction.workspace_id == message.workspace_id,
            AgentAction.thread_id == thread.id,
            AgentAction.action_type == "dm.send",
            (AgentAction.status.in_(("in_progress", "outcome_unknown")))
            | Operation.status.in_(("in_progress", "outcome_unknown"))
            | ReplyDraft.status.in_(("sending", "outcome_unknown")),
        )
        .limit(1)
    )
    if already_sent is not None or uncertain is not None:
        return False
    from app.agent.jobs import enqueue_cleanup
    from app.inbox import drafts
    from app.inbox.system import system_context

    conversation = db.get(Conversation, message.conversation_id)
    ctx = system_context(db, message.workspace_id, "agent.media")
    if conversation is None or ctx is None or conversation.handling_mode == "human":
        return False
    retired = drafts.close_open_drafts(
        db,
        clock,
        ctx,
        conversation,
        reason="MEDIA_UPDATED",
        events=drafts.ON_FACT_CHANGE,
        defer_approvals=True,
    )
    for draft in retired:
        action = db.get(AgentAction, draft.agent_action_id) if draft.agent_action_id else None
        if action is not None:
            action.status, action.outcome_code = "cancelled", "MEDIA_UPDATED"
            record(
                db,
                ctx,
                "agent.action_transition",
                "agent_action",
                action.id,
                {"to": "cancelled", "reason": "MEDIA_UPDATED"},
                clock=clock,
            )
    record_thread_event(
        db,
        clock,
        workspace_id=message.workspace_id,
        account_id=message.social_account_id,
        thread_id=thread.id,
        kind=kind,
        source_kind=source_kind,
        source_key=source_key,
        source_id=source_id,
        source_version=1,
    )
    enqueue_cleanup(db, clock, message.workspace_id, message.social_account_id, thread.event_cursor)
    return True
