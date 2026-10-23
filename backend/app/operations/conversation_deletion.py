"""Scoped conversation erasure after uncertain sends have been reconciled."""

import uuid

from sqlalchemy import delete, null, select, update
from sqlalchemy.orm import Session

from app.core.clock import Clock
from app.inbox.models import Conversation, InboundEvent, Message, ReplyDraft
from app.jobs.models import Job
from app.jobs.queue import cancel_queued, enqueue
from app.knowledge.models import ApprovedAnswer, FactReference
from app.operations.models import Operation
from app.operations.payloads import DeleteAccountConversationsPayload


def pending(
    session: Session, workspace_id: uuid.UUID, *, account_id: uuid.UUID | None = None
) -> bool:
    statement = select(Job.id).where(
        Job.workspace_id == workspace_id,
        Job.job_type == "delete_account_conversations",
        Job.status.in_(("queued", "running", "dead")),
    )
    if account_id is not None:
        statement = statement.where(Job.payload["social_account_id"].astext == str(account_id))
    return session.scalar(statement.limit(1)) is not None


def unresolved(session: Session, workspace_id: uuid.UUID, account_id: uuid.UUID) -> bool:
    return (
        session.scalar(
            select(Operation.id)
            .where(
                Operation.workspace_id == workspace_id,
                Operation.social_account_id == account_id,
                Operation.operation_type == "send_reply",
                Operation.status.in_(("in_progress", "outcome_unknown")),
            )
            .limit(1)
        )
        is not None
    )


def wipe(session: Session, clock: Clock, workspace_id: uuid.UUID, account_id: uuid.UUID) -> None:
    """Caller holds the disconnected account; no unresolved sends. Preserve audit/ledger rows."""
    conversation_ids = select(Conversation.id).where(
        Conversation.workspace_id == workspace_id, Conversation.social_account_id == account_id
    )
    draft_ids = select(ReplyDraft.id).where(
        ReplyDraft.workspace_id == workspace_id, ReplyDraft.conversation_id.in_(conversation_ids)
    )
    message_ids = select(Message.id).where(
        Message.workspace_id == workspace_id, Message.conversation_id.in_(conversation_ids)
    )
    for conversation_id in session.scalars(conversation_ids):
        cancel_queued(session, f"draft_reply:{conversation_id}", clock)
        cancel_queued(session, f"draft_reply:{conversation_id}:requested", clock)
    session.execute(
        delete(FactReference).where(
            FactReference.workspace_id == workspace_id,
            FactReference.referrer_type == "reply_draft",
            FactReference.referrer_id.in_(draft_ids),
        )
    )
    # Break references without ON DELETE CASCADE, including the message/draft cycle.
    session.execute(
        update(ApprovedAnswer)
        .where(
            ApprovedAnswer.workspace_id == workspace_id,
            ApprovedAnswer.created_from_message_id.in_(message_ids),
        )
        .values(created_from_message_id=None)
    )
    session.execute(
        update(Message)
        .where(Message.workspace_id == workspace_id, Message.reply_draft_id.in_(draft_ids))
        .values(reply_draft_id=None)
    )
    session.execute(
        update(ReplyDraft)
        .where(ReplyDraft.workspace_id == workspace_id, ReplyDraft.superseded_by_id.in_(draft_ids))
        .values(superseded_by_id=None)
    )
    session.execute(
        delete(ReplyDraft).where(
            ReplyDraft.workspace_id == workspace_id,
            ReplyDraft.conversation_id.in_(conversation_ids),
        )
    )
    session.execute(
        delete(Message).where(
            Message.workspace_id == workspace_id, Message.conversation_id.in_(conversation_ids)
        )
    )
    session.execute(
        delete(Conversation).where(
            Conversation.workspace_id == workspace_id, Conversation.social_account_id == account_id
        )
    )


def request(session: Session, clock: Clock, workspace_id: uuid.UUID, account_id: uuid.UUID) -> None:
    session.execute(
        update(InboundEvent)
        .where(
            InboundEvent.workspace_id == workspace_id, InboundEvent.social_account_id == account_id
        )
        .values(payload=null())
    )
    if unresolved(session, workspace_id, account_id):
        enqueue(
            session,
            "delete_account_conversations",
            DeleteAccountConversationsPayload(social_account_id=account_id),
            workspace_id=workspace_id,
            correlation_id=None,
            dedup_key=f"delete_account_conversations:{account_id}",
            clock=clock,
        )
    else:
        wipe(session, clock, workspace_id, account_id)
