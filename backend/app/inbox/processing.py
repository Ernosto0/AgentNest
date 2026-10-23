"""Processing of stored webhook events (workflows.md §C step 2).

One transaction per event, with the conversation row locked, so the events of one conversation
are applied one at a time. Everything here is idempotent: a duplicate message is a no-op, and
an event that is no longer ``received`` is skipped. Time-ordering uses the provider timestamps
(``greatest()``), so out-of-order delivery cannot move a conversation backwards.
"""

import uuid
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.audit import service as audit
from app.core.clock import Clock
from app.core.context import WorkspaceContext
from app.core.ids import new_id
from app.inbox import attention, drafts
from app.inbox.echoes import Echo, claimed_by_a_send
from app.inbox.models import Conversation, InboundEvent, Message
from app.inbox.payloads import DraftReplyPayload, draft_reply_key
from app.inbox.system import system_context
from app.integrations.instagram import queries
from app.integrations.instagram.base import NormalizedInboundEvent
from app.integrations.instagram.models import SocialAccount
from app.integrations.instagram.webhook_format import parse
from app.jobs.queue import enqueue
from app.notifications import service as notifications


def process_inbound_event(
    session: Session,
    clock: Clock,
    workspace_id: uuid.UUID,
    event_id: uuid.UUID,
    *,
    debounce_seconds: int,
) -> None:
    """Apply one stored event and commit. A gone or already handled event is skipped."""
    event = session.get(InboundEvent, event_id)
    if event is None or event.workspace_id != workspace_id or event.status != "received":
        return
    ctx = system_context(session, workspace_id)
    account = (
        queries.get_account_in_workspace(session, workspace_id, event.social_account_id)
        if event.social_account_id
        else None
    )
    if ctx is None or account is None or account.status == "disconnected":
        event.status, event.ignore_reason = "ignored", "ACCOUNT_DISCONNECTED"
        event.processed_at = clock.now()
        session.commit()
        return

    normalized = _normalized(event, account)
    if normalized is not None and normalized.event_type == "delete" and normalized.mid:
        message = session.scalars(
            select(Message)
            .where(
                Message.workspace_id == workspace_id,
                Message.social_account_id == account.id,
                Message.external_message_id == normalized.mid,
            )
            .with_for_update()
        ).one_or_none()
        if message is not None:
            message.is_deleted = True
    if normalized is not None and normalized.customer_id:
        if normalized.event_type == "message":
            _on_customer_message(session, clock, ctx, account, event, normalized, debounce_seconds)
        elif normalized.event_type == "echo":
            _on_echo(session, clock, ctx, account, event, normalized)
    event.status = "processed"
    event.processed_at = clock.now()
    session.commit()


def _normalized(event: InboundEvent, account: SocialAccount) -> NormalizedInboundEvent | None:
    """Rebuild the normalised event from the stored webhook item."""
    if not event.payload:
        return None
    parsed = parse(
        {
            "object": "instagram",
            "entry": [{"id": account.external_account_id, "messaging": [event.payload]}],
        }
    )
    return parsed[0] if parsed else None


def _timestamp(event: NormalizedInboundEvent, clock: Clock) -> datetime:
    return event.provider_timestamp or clock.now()


def _greatest(current: datetime | None, candidate: datetime) -> datetime:
    return candidate if current is None or candidate > current else current


def _lock_conversation(session: Session, account: SocialAccount, customer_id: str) -> Conversation:
    session.execute(
        pg_insert(Conversation)
        .values(
            id=new_id(),
            workspace_id=account.workspace_id,
            social_account_id=account.id,
            customer_external_id=customer_id,
            is_simulated=account.is_simulated,
        )
        .on_conflict_do_nothing(index_elements=["social_account_id", "customer_external_id"])
    )
    return session.scalars(
        select(Conversation)
        .where(
            Conversation.social_account_id == account.id,
            Conversation.customer_external_id == customer_id,
        )
        .with_for_update()
    ).one()


def _insert_message(
    session: Session,
    account: SocialAccount,
    conversation: Conversation,
    event: NormalizedInboundEvent,
    *,
    direction: str,
    sender_kind: str,
    moment: datetime,
) -> uuid.UUID | None:
    """The new message's id, or ``None`` if this provider message id was already stored."""
    values = {
        "id": new_id(),
        "workspace_id": account.workspace_id,
        "conversation_id": conversation.id,
        "social_account_id": account.id,
        "direction": direction,
        "sender_kind": sender_kind,
        "external_message_id": event.mid,
        "text": event.text,
        "attachments": event.attachments,
        "provider_timestamp": moment,
        "is_simulated": account.is_simulated,
    }
    stmt = pg_insert(Message).values(**values)
    if event.mid is not None:
        stmt = stmt.on_conflict_do_nothing(
            index_elements=["social_account_id", "external_message_id"],
            index_where=Message.external_message_id.is_not(None),
        )
    return session.scalar(stmt.returning(Message.id))


def _on_customer_message(
    session: Session,
    clock: Clock,
    ctx: WorkspaceContext,
    account: SocialAccount,
    event: InboundEvent,
    normalized: NormalizedInboundEvent,
    debounce_seconds: int,
) -> None:
    customer_id = normalized.customer_id or ""
    conversation = _lock_conversation(session, account, customer_id)
    moment = _timestamp(normalized, clock)
    message_id = _insert_message(
        session,
        account,
        conversation,
        normalized,
        direction="inbound",
        sender_kind="customer",
        moment=moment,
    )
    if message_id is None:  # the same provider message arrived twice
        return
    conversation.last_inbound_at = _greatest(conversation.last_inbound_at, moment)
    conversation.last_message_at = _greatest(conversation.last_message_at, moment)
    audit.record(
        session,
        ctx,
        "message.received",
        "message",
        message_id,
        {"conversation_id": conversation.id, "event_type": "message"},
        is_simulated=account.is_simulated,
        correlation_id=event.correlation_id,
        clock=clock,
    )
    # The customer wrote again: whatever is waiting for a person is out of date.
    drafts.close_open_drafts(
        session, clock, ctx, conversation, reason="NEW_INBOUND", events=drafts.ON_NEW_INBOUND
    )
    if conversation.handling_mode == "automatic":
        enqueue(
            session,
            "draft_reply",
            DraftReplyPayload(conversation_id=conversation.id),
            workspace_id=account.workspace_id,
            correlation_id=event.correlation_id,
            run_at=clock.now() + timedelta(seconds=debounce_seconds),
            dedup_key=draft_reply_key(conversation.id),
            clock=clock,
        )
    else:
        notifications.notify_permission_holders(
            session,
            clock,
            ctx,
            permission="reply.approve",
            type="conversation.needs_human",
            severity="attention",
            params={"conversation_id": str(conversation.id), "reasons": ["HUMAN_TAKEOVER"]},
            subject_type="conversation",
            subject_id=conversation.id,
            dedup_key=f"needs-human:{conversation.id}",
            is_simulated=account.is_simulated,
        )
    attention.refresh(session, conversation)


def _on_echo(
    session: Session,
    clock: Clock,
    ctx: WorkspaceContext,
    account: SocialAccount,
    event: InboundEvent,
    normalized: NormalizedInboundEvent,
) -> None:
    customer_id = normalized.customer_id or ""
    moment = _timestamp(normalized, clock)
    echo = Echo(
        account.id,
        customer_id,
        normalized.mid,
        normalized.text,
        moment,
        normalized.app_id,
        account.provider_kind,
    )
    if claimed_by_a_send(session, clock, ctx, echo):
        return  # the echo of a message this application sent: the send machinery owns it
    conversation = _lock_conversation(session, account, customer_id)
    message_id = _insert_message(
        session,
        account,
        conversation,
        normalized,
        direction="outbound",
        sender_kind="business_native",
        moment=moment,
    )
    if message_id is None:  # already known (recorded by the send, or a duplicate)
        return
    conversation.last_outbound_at = _greatest(conversation.last_outbound_at, moment)
    conversation.last_message_at = _greatest(conversation.last_message_at, moment)
    audit.record(
        session,
        ctx,
        "message.native_reply_recorded",
        "message",
        message_id,
        {"conversation_id": conversation.id},
        is_simulated=account.is_simulated,
        correlation_id=event.correlation_id,
        clock=clock,
    )
    # The owner answered in the Instagram app: a draft for the same question is obsolete.
    drafts.close_open_drafts(
        session,
        clock,
        ctx,
        conversation,
        reason="OWNER_REPLIED_NATIVELY",
        events=drafts.ON_NATIVE_REPLY,
    )
    attention.refresh(session, conversation)
