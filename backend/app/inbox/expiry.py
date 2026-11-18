"""Drafts whose messaging window closed (state-machines.md §4: ``expired``).

Instagram allows a reply for 24 hours after the customer's last message. Past that, nothing
may be sent, so a draft still waiting for a person or for the send is retired here. (A pending
approval normally expires first, five minutes before the window ends; this is the backstop for
``needs_human`` and ``queued`` drafts, which have no approval clock of their own.) A person's
reply with the Human Agent tag has a 7-day window and is retired only when that is over.
"""

from sqlalchemy import or_, select, text
from sqlalchemy.orm import Session, sessionmaker

from app.approvals import service as approvals
from app.core.clock import Clock
from app.core.db import set_tenant_context
from app.inbox import attention, drafts
from app.inbox.context import MESSAGING_WINDOW
from app.inbox.models import Conversation, ReplyDraft
from app.inbox.system import system_context
from app.policy.message_tag import HUMAN_AGENT_WINDOW

EXPIRABLE = ("pending_approval", "needs_human", "queued")
BATCH = 100


def expire_closed_window_drafts(session_factory: sessionmaker[Session], clock: Clock) -> int:
    """Expire every waiting draft whose window has closed; one transaction per draft."""
    cutoff = clock.now() - MESSAGING_WINDOW
    with session_factory() as session:
        bind = session.get_bind()
        if bind.dialect.name == "postgresql":
            due = session.execute(
                text(
                    "SELECT id, workspace_id "
                    "FROM public.discover_expired_reply_draft_ids(:cutoff, :limit)"
                ),
                {"cutoff": cutoff, "limit": BATCH},
            ).all()
        else:
            due = session.execute(
                select(ReplyDraft.id, ReplyDraft.workspace_id)
                .join(
                    Conversation,
                    (Conversation.workspace_id == ReplyDraft.workspace_id)
                    & (Conversation.id == ReplyDraft.conversation_id),
                )
                .where(
                    ReplyDraft.status.in_(EXPIRABLE),
                    Conversation.last_inbound_at <= cutoff,
                    # A tagged reply waits for the 7-day window instead of the 24-hour one.
                    or_(
                        ReplyDraft.message_tag.is_(None),
                        Conversation.last_inbound_at
                        <= cutoff - (HUMAN_AGENT_WINDOW - MESSAGING_WINDOW),
                    ),
                )
                .order_by(ReplyDraft.created_at)
                .limit(BATCH)
            ).all()
    expired = 0
    for draft_id, workspace_id in due:
        with session_factory() as session:
            set_tenant_context(session, workspace_id)
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
