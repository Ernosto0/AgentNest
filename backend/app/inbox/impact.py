"""How reply drafts react to a change of a fact they quote (business-knowledge.md §8, AC-C5).

A draft that still waits (for approval, or queued for sending) and rendered an older version of
the changed fact is retired and drafted again, so the next reply carries the new value. A
message that was already sent is never touched (INV-17); a draft being sent right now cannot be
recalled and is left alone.
"""

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.clock import Clock
from app.core.context import WorkspaceContext
from app.inbox import attention, drafts
from app.inbox.models import Conversation, ReplyDraft
from app.inbox.payloads import DraftReplyPayload
from app.jobs.queue import enqueue
from app.knowledge import impact
from app.knowledge.models import BusinessFact, FactReference

LIVE_STATUSES = ("pending_approval", "queued")


class ReplyDraftReferrers:
    referrer_type = "reply_draft"

    def count(self, session: Session, ctx: WorkspaceContext, fact_id: uuid.UUID) -> dict[str, int]:
        rows = session.execute(
            select(ReplyDraft.status, func.count())
            .join(
                FactReference,
                (FactReference.workspace_id == ReplyDraft.workspace_id)
                & (FactReference.referrer_id == ReplyDraft.id),
            )
            .where(
                FactReference.workspace_id == ctx.workspace_id,
                FactReference.referrer_type == self.referrer_type,
                FactReference.fact_id == fact_id,
                ReplyDraft.status.in_(LIVE_STATUSES),
            )
            .group_by(ReplyDraft.status)
        ).all()
        return {status: int(number) for status, number in rows}

    def apply_change(
        self,
        session: Session,
        clock: Clock,
        ctx: WorkspaceContext,
        fact: BusinessFact,
        change: impact.ChangeKind,
        old_version: int,
    ) -> dict[str, int]:
        outdated = session.scalars(
            select(ReplyDraft)
            .join(
                FactReference,
                (FactReference.workspace_id == ReplyDraft.workspace_id)
                & (FactReference.referrer_id == ReplyDraft.id),
            )
            .where(
                FactReference.workspace_id == ctx.workspace_id,
                FactReference.referrer_type == self.referrer_type,
                FactReference.fact_id == fact.id,
                FactReference.fact_version != fact.current_version,
                ReplyDraft.status.in_(LIVE_STATUSES),
            )
            .with_for_update(of=ReplyDraft)
        ).all()
        outcome = {"superseded": 0, "cancelled": 0, "redrafted": 0}
        for draft in outdated:
            conversation = session.scalars(
                select(Conversation)
                .where(
                    Conversation.workspace_id == draft.workspace_id,
                    Conversation.id == draft.conversation_id,
                )
                .with_for_update()
            ).one()
            closed = drafts.close_open_drafts(
                session,
                clock,
                ctx,
                conversation,
                reason="FACT_CHANGED",
                events=drafts.ON_FACT_CHANGE,
            )
            if not closed:
                continue
            outcome["superseded" if closed[0].status == "superseded" else "cancelled"] += 1
            # Draft again with the new value (the job decides whether a reply is still possible).
            enqueue(
                session,
                "draft_reply",
                DraftReplyPayload(
                    conversation_id=conversation.id, message_id=draft.covers_through_message_id
                ),
                workspace_id=draft.workspace_id,
                correlation_id=None,
                dedup_key=f"draft_reply:{conversation.id}:{draft.covers_through_message_id}:fact",
                clock=clock,
            )
            outcome["redrafted"] += 1
            attention.refresh(session, conversation)
        return {key: value for key, value in outcome.items() if value}


impact.register_handler(ReplyDraftReferrers())
