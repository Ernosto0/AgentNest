"""Reply-draft state changes with their side effects (state-machines.md §4).

``transition`` applies one event through the pure state machine as a **conditional update**
(``WHERE status = :expected``), so a concurrent change surfaces as ``CONFLICT_STATE`` instead of
a lost update. ``close_open_drafts`` is how a new inbound message, a native owner reply, a
takeover or a fact change retires the drafts they make obsolete, and it withdraws their pending
approvals (INV-16).
"""

import uuid
from collections.abc import Mapping

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.approvals import service as approvals
from app.audit import service as audit
from app.core.clock import Clock
from app.core.context import WorkspaceContext
from app.core.errors import AppError
from app.inbox.models import OPEN_DRAFT_STATUSES, Conversation, ReplyDraft
from app.inbox.transitions import apply_draft_event

SUBJECT_TYPE = "reply_draft"


def get_draft(
    session: Session, workspace_id: uuid.UUID, draft_id: uuid.UUID, *, lock: bool = False
) -> ReplyDraft | None:
    stmt = select(ReplyDraft).where(
        ReplyDraft.workspace_id == workspace_id, ReplyDraft.id == draft_id
    )
    return session.scalars(stmt.with_for_update() if lock else stmt).one_or_none()


def get_open_draft(
    session: Session, workspace_id: uuid.UUID, conversation_id: uuid.UUID, *, lock: bool = False
) -> ReplyDraft | None:
    stmt = select(ReplyDraft).where(
        ReplyDraft.workspace_id == workspace_id,
        ReplyDraft.conversation_id == conversation_id,
        ReplyDraft.status.in_(OPEN_DRAFT_STATUSES),
    )
    return session.scalars(stmt.with_for_update() if lock else stmt).one_or_none()


def recent_drafts(
    session: Session, workspace_id: uuid.UUID, conversation_id: uuid.UUID, limit: int = 5
) -> list[ReplyDraft]:
    """The conversation's latest drafts, newest first (open or not)."""
    return list(
        session.scalars(
            select(ReplyDraft)
            .where(
                ReplyDraft.workspace_id == workspace_id,
                ReplyDraft.conversation_id == conversation_id,
            )
            .order_by(ReplyDraft.created_at.desc(), ReplyDraft.id)
            .limit(limit)
        )
    )


def transition(
    session: Session,
    clock: Clock,
    ctx: WorkspaceContext,
    draft: ReplyDraft,
    event: str,
    *,
    reason: str | None = None,
    superseded_by_id: uuid.UUID | None = None,
) -> ReplyDraft:
    """Apply ``event`` to ``draft`` (conditional update, audited). No commit."""
    previous = draft.status
    new_status = apply_draft_event(previous, event)
    session.flush()
    values: dict[str, object] = {"status": new_status, "updated_at": clock.now()}
    if reason is not None:
        values["failure_code"] = reason
    if superseded_by_id is not None:
        values["superseded_by_id"] = superseded_by_id
    if event == "edit":
        values["version"] = ReplyDraft.version + 1
    result = session.execute(
        update(ReplyDraft)
        .where(ReplyDraft.id == draft.id, ReplyDraft.status == previous)
        .values(**values)
        .execution_options(synchronize_session=False)
    )
    if result.rowcount != 1:  # type: ignore[attr-defined]
        raise AppError("CONFLICT_STATE", entity="reply_draft", status=previous, event=event)
    session.refresh(draft)
    audit.record(
        session,
        ctx,
        f"reply_draft.{new_status}",
        "reply_draft",
        draft.id,
        {
            "from": previous,
            "event": event,
            "reason": reason,
            "conversation_id": draft.conversation_id,
        },
        is_simulated=draft.is_simulated,
        clock=clock,
    )
    return draft


def close_open_drafts(
    session: Session,
    clock: Clock,
    ctx: WorkspaceContext,
    conversation: Conversation,
    *,
    reason: str,
    events: Mapping[str, str],
    superseded_by_id: uuid.UUID | None = None,
) -> list[ReplyDraft]:
    """Retire the conversation's open draft when it is in a state listed in ``events``
    (``status -> event``), withdrawing a pending approval. Drafts in other states (for example
    one that is already being sent) are left alone. No commit."""
    draft = get_open_draft(session, conversation.workspace_id, conversation.id, lock=True)
    if draft is None or draft.status not in events:
        return []
    if draft.status == "pending_approval":
        approvals.cancel_for_subject(session, clock, ctx, SUBJECT_TYPE, draft.id, reason)
    transition(
        session,
        clock,
        ctx,
        draft,
        events[draft.status],
        reason=reason,
        superseded_by_id=superseded_by_id,
    )
    return [draft]


# Which drafts each trigger retires (workflows.md §C, G2 in the Phase 4 plan).
ON_NEW_INBOUND = {"pending_approval": "supersede", "needs_human": "supersede"}
ON_NATIVE_REPLY = {
    "pending_approval": "supersede",
    "needs_human": "supersede",
    "queued": "cancel",
}
ON_TAKEOVER = {"pending_approval": "supersede"}
ON_FACT_CHANGE = {
    "pending_approval": "supersede",
    "needs_human": "supersede",
    "queued": "cancel",
}
