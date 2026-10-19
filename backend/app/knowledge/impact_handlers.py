"""How approved answers react to a change of a fact their template uses (business-knowledge.md §9).

An answer that quotes the changed fact (through a ``{{fact:key}}`` placeholder) is marked
``needs_review``: it keeps being offered to the drafting model, flagged, because its wording
may no longer fit the new value. Nothing is deleted or rewritten.
"""

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.clock import Clock
from app.core.context import WorkspaceContext
from app.knowledge import impact
from app.knowledge.models import ApprovedAnswer, BusinessFact, FactReference


class ApprovedAnswerReferrers:
    referrer_type = "approved_answer"

    def count(self, session: Session, ctx: WorkspaceContext, fact_id: uuid.UUID) -> dict[str, int]:
        rows = session.execute(
            select(ApprovedAnswer.status, func.count())
            .join(
                FactReference,
                (FactReference.workspace_id == ApprovedAnswer.workspace_id)
                & (FactReference.referrer_id == ApprovedAnswer.id),
            )
            .where(
                FactReference.workspace_id == ctx.workspace_id,
                FactReference.referrer_type == self.referrer_type,
                FactReference.fact_id == fact_id,
                ApprovedAnswer.status == "active",
            )
            .group_by(ApprovedAnswer.status)
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
        answers = session.scalars(
            select(ApprovedAnswer)
            .join(
                FactReference,
                (FactReference.workspace_id == ApprovedAnswer.workspace_id)
                & (FactReference.referrer_id == ApprovedAnswer.id),
            )
            .where(
                FactReference.workspace_id == ctx.workspace_id,
                FactReference.referrer_type == self.referrer_type,
                FactReference.fact_id == fact.id,
                ApprovedAnswer.status == "active",
            )
            .with_for_update(of=ApprovedAnswer)
        ).all()
        for answer in answers:
            answer.status = "needs_review"
            answer.updated_at = clock.now()
        return {"needs_review": len(answers)} if answers else {}


impact.register_handler(ApprovedAnswerReferrers())
