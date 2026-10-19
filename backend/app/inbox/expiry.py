"""Drafts whose messaging window closed (state-machines.md §4: ``expired``).

Instagram allows a reply for 24 hours after the customer's last message. Past that, nothing
may be sent, so a draft still waiting for a person or for the send is retired here. (A pending
approval normally expires first, five minutes before the window ends; this is the backstop for
``needs_human`` and ``queued`` drafts, which have no approval clock of their own.)
"""

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.approvals import service as approvals
from app.core.clock import Clock
from app.inbox import attention, drafts
from app.inbox.context import MESSAGING_WINDOW
from app.inbox.models import Conversation, ReplyDraft
from app.inbox.system import system_context

EXPIRABLE = ("pending_approval", "needs_human", "queued")
BATCH = 100


def expire_closed_window_drafts(session_factory: sessionmaker[Session], clock: Clock) -> int:
    """Expire every waiting draft whose window has closed; one transaction per draft."""
    cutoff = clock.now() - MESSAGING_WINDOW
    with session_factory() as session:
        due = session.execute(
            select(ReplyDraft.id, ReplyDraft.workspace_id)
            .join(
                Conversation,
                (Conversation.workspace_id == ReplyDraft.workspace_id)
                & (Conversation.id == ReplyDraft.conversation_id),
            )
            .where(ReplyDraft.status.in_(EXPIRABLE), Conversation.last_inbound_at <= cutoff)
            .order_by(ReplyDraft.created_at)
            .limit(BATCH)
        ).all()
    expired = 0
    for draft_id, workspace_id in due:
        with session_factory() as session:
            ctx = system_context(session, workspace_id, "inbox.expiry")
            draft = drafts.get_draft(session, workspace_id, draft_id, lock=True)
            if ctx is None or draft is None or draft.status not in EXPIRABLE:
                continue
            if draft.status == "pending_approval":
                approvals.cancel_for_subject(
                    session, clock, ctx, drafts.SUBJECT_TYPE, draft.id, "MESSAGING_WINDOW_CLOSED"
                )
            drafts.transition(
                session, clock, ctx, draft, "expire", reason="MESSAGING_WINDOW_CLOSED"
            )
            conversation = session.scalars(
                select(Conversation).where(
                    Conversation.workspace_id == workspace_id,
                    Conversation.id == draft.conversation_id,
                )
            ).one()
            attention.refresh(session, conversation)
            session.commit()
            expired += 1
    return expired
