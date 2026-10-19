"""Registers ``reply_draft`` as an approval subject (workflows.md §D).

The callback runs in the **same transaction** as the decision, so a draft is never queued for
sending unless its approval is recorded as approved, and a failing callback leaves the approval
pending. Imported by ``app.handlers.load_handlers`` in the API and the worker.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.approvals import callbacks
from app.approvals.models import Approval
from app.core.clock import Clock
from app.core.context import WorkspaceContext
from app.core.errors import AppError
from app.inbox import attention, drafts
from app.inbox.models import Conversation
from app.inbox.payloads import SendReplyPayload
from app.jobs.queue import enqueue


def on_decided(session: Session, clock: Clock, ctx: WorkspaceContext, approval: Approval) -> None:
    draft = drafts.get_draft(session, approval.workspace_id, approval.subject_id, lock=True)
    if draft is None:
        raise AppError("NOT_FOUND")
    if draft.status != "pending_approval" or draft.version != approval.subject_version:
        if approval.status == "expired":
            return  # nothing waits for this approval any more
        # Never queue a send for a draft that is no longer the one that was approved.
        raise AppError("APPROVAL_STALE")
    if approval.status == "approved":
        drafts.transition(session, clock, ctx, draft, "approve")
        enqueue(
            session,
            "send_reply",
            SendReplyPayload(reply_draft_id=draft.id),
            workspace_id=draft.workspace_id,
            correlation_id=None,
            dedup_key=f"send_reply:{draft.id}",
            clock=clock,
        )
    elif approval.status == "rejected":
        drafts.transition(session, clock, ctx, draft, "reject")
    elif approval.status == "expired":
        drafts.transition(session, clock, ctx, draft, "expire", reason="APPROVAL_EXPIRED")
    else:  # cancelled approvals are handled by whoever cancelled them
        return
    conversation = session.scalars(
        select(Conversation).where(
            Conversation.workspace_id == draft.workspace_id,
            Conversation.id == draft.conversation_id,
        )
    ).one()
    attention.refresh(session, conversation)


def subject_version(session: Session, ctx: WorkspaceContext, subject_id: uuid.UUID) -> int | None:
    """The draft's version while it still awaits this decision; ``None`` once it moved on, which
    makes any decision on its approval stale."""
    draft = drafts.get_draft(session, ctx.workspace_id, subject_id)
    if draft is None or draft.status != "pending_approval":
        return None
    return draft.version


def subject_status(session: Session, ctx: WorkspaceContext, subject_id: uuid.UUID) -> str | None:
    draft = drafts.get_draft(session, ctx.workspace_id, subject_id)
    return draft.status if draft else None


callbacks.register(
    drafts.SUBJECT_TYPE,
    on_decided,
    current_version=subject_version,
    status_of=subject_status,
)
