"""Closing a send whose outcome was unknown, and the shared bookkeeping of a delivered reply.

Three things can resolve an ``outcome_unknown`` send: an echo carrying our message, the
provider's conversation lookup, or the end of the reconciliation window (``OUTCOME_UNCONFIRMED``,
never a resend). They all land here so that they leave the same records.
"""

import hashlib
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.audit import service as audit
from app.core.clock import Clock
from app.core.context import WorkspaceContext
from app.core.ids import new_id
from app.inbox import attention, drafts
from app.inbox.models import Conversation, Message, ReplyDraft
from app.integrations.instagram.models import SocialAccount
from app.notifications import service as notifications
from app.operations.models import Operation
from app.operations.transitions import apply_operation_event


def text_sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def set_operation(clock: Clock, op: Operation, event: str, *, code: str | None = None) -> None:
    """Apply a state-machine event to the ledger row (the row is locked by the caller)."""
    op.status = apply_operation_event(op.status, event, operation_type=op.operation_type)
    if code is not None:
        op.last_error_code = code
    if event in ("succeed", "fail", "cancel"):
        op.completed_at = clock.now()


def lock_conversation(session: Session, draft: ReplyDraft) -> Conversation:
    return session.scalars(
        select(Conversation)
        .where(
            Conversation.workspace_id == draft.workspace_id,
            Conversation.id == draft.conversation_id,
        )
        .with_for_update()
    ).one()


def record_delivered(
    session: Session,
    clock: Clock,
    ctx: WorkspaceContext,
    op: Operation,
    draft: ReplyDraft,
    account: SocialAccount,
    *,
    message_id: str,
    sent_at: datetime,
    via: str,
) -> None:
    """The reply is out: store it as a message, close the draft, update the conversation.

    Expects the operation to be ``succeeded`` already and the draft to be ``sending`` or
    ``outcome_unknown``. Idempotent on the provider message id.
    """
    conversation = lock_conversation(session, draft)
    session.execute(
        pg_insert(Message)
        .values(
            id=new_id(),
            workspace_id=draft.workspace_id,
            conversation_id=conversation.id,
            social_account_id=account.id,
            direction="outbound",
            sender_kind="business_app",
            external_message_id=message_id,
            text=draft.text,
            attachments=[],
            provider_timestamp=sent_at,
            reply_draft_id=draft.id,
            is_simulated=draft.is_simulated,
        )
        .on_conflict_do_nothing(
            index_elements=["social_account_id", "external_message_id"],
            index_where=Message.external_message_id.is_not(None),
        )
    )
    if conversation.last_outbound_at is None or sent_at > conversation.last_outbound_at:
        conversation.last_outbound_at = sent_at
    if conversation.last_message_at is None or sent_at > conversation.last_message_at:
        conversation.last_message_at = sent_at
    drafts.transition(session, clock, ctx, draft, "succeed")
    attention.refresh(session, conversation)
    audit.record(
        session,
        ctx,
        "reply.sent",
        "reply_draft",
        draft.id,
        {
            "operation_id": op.id,
            "conversation_id": conversation.id,
            "message_id": message_id,
            "via": via,
        },
        is_simulated=draft.is_simulated,
        correlation_id=op.correlation_id,
        clock=clock,
    )


def resolve_unknown_as_sent(
    session: Session,
    clock: Clock,
    ctx: WorkspaceContext,
    op: Operation,
    draft: ReplyDraft,
    account: SocialAccount,
    *,
    message_id: str,
    sent_at: datetime,
    via: str,
) -> None:
    """An echo or the lookup proved the message was delivered."""
    set_operation(clock, op, "succeed")
    op.result = {"message_id": message_id, "resolved_by": via}
    record_delivered(
        session, clock, ctx, op, draft, account, message_id=message_id, sent_at=sent_at, via=via
    )


def resolve_unconfirmed(
    session: Session,
    clock: Clock,
    ctx: WorkspaceContext,
    op: Operation,
    draft: ReplyDraft,
) -> None:
    """Nothing confirmed the send within the window. It is reported and **never repeated**: the
    message may well have been delivered, and a duplicate to a customer is worse than a miss."""
    set_operation(clock, op, "fail", code="OUTCOME_UNCONFIRMED")
    drafts.transition(session, clock, ctx, draft, "fail", reason="OUTCOME_UNCONFIRMED")
    conversation = lock_conversation(session, draft)
    attention.refresh(session, conversation)
    notify_reply_failed(session, clock, ctx, draft, "OUTCOME_UNCONFIRMED")
    audit.record(
        session,
        ctx,
        "reply.outcome_unconfirmed",
        "reply_draft",
        draft.id,
        {"operation_id": op.id, "conversation_id": conversation.id},
        is_simulated=draft.is_simulated,
        correlation_id=op.correlation_id,
        clock=clock,
    )


def record_late_delivery(
    session: Session,
    clock: Clock,
    ctx: WorkspaceContext,
    op: Operation,
    draft: ReplyDraft,
    account: SocialAccount,
    *,
    message_id: str,
    sent_at: datetime,
) -> None:
    """An echo of a send we had given up on: the message *was* delivered. It is recorded as the
    business's own message (not misread as a reply typed in the Instagram app), the draft keeps
    its terminal state, and the audit trail says what happened."""
    conversation = lock_conversation(session, draft)
    session.execute(
        pg_insert(Message)
        .values(
            id=new_id(),
            workspace_id=draft.workspace_id,
            conversation_id=conversation.id,
            social_account_id=account.id,
            direction="outbound",
            sender_kind="business_app",
            external_message_id=message_id,
            text=draft.text,
            attachments=[],
            provider_timestamp=sent_at,
            reply_draft_id=draft.id,
            is_simulated=draft.is_simulated,
        )
        .on_conflict_do_nothing(
            index_elements=["social_account_id", "external_message_id"],
            index_where=Message.external_message_id.is_not(None),
        )
    )
    if conversation.last_outbound_at is None or sent_at > conversation.last_outbound_at:
        conversation.last_outbound_at = sent_at
    attention.refresh(session, conversation)
    audit.record(
        session,
        ctx,
        "reply.late_confirmation",
        "reply_draft",
        draft.id,
        {"operation_id": op.id, "conversation_id": conversation.id, "message_id": message_id},
        is_simulated=draft.is_simulated,
        correlation_id=op.correlation_id,
        clock=clock,
    )


def notify_reply_failed(
    session: Session, clock: Clock, ctx: WorkspaceContext, draft: ReplyDraft, code: str
) -> None:
    notifications.notify_permission_holders(
        session,
        clock,
        ctx,
        permission="reply.approve",
        type="reply.failed",
        severity="attention",
        params={"conversation_id": str(draft.conversation_id), "code": code},
        subject_type="conversation",
        subject_id=draft.conversation_id,
        dedup_key=f"reply-failed:{draft.id}",
        is_simulated=draft.is_simulated,
    )
