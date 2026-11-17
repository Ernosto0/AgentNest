"""Owner-answer learning: which answers need a typed editor, and what was learned this month.

A fact counts as "learned from the owner" when its history holds a version written by accepting
a candidate whose source is an owner answer (insert-only ``fact_versions`` evidence, INV-17).
Later owner edits of the same fact do not add to the count, and a fact counts once.
"""

import uuid
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from pydantic import BaseModel
from sqlalchemy import String, cast, func, select
from sqlalchemy.orm import Session

from app.core.canonical import payload_hash
from app.core.clock import Clock
from app.core.context import WorkspaceContext
from app.knowledge.claims import validate_claims
from app.knowledge.models import BusinessFact, FactCandidate, FactVersion
from app.knowledge.render import RenderResult
from app.owner_requests.models import OwnerAnswer, OwnerQuestion

# Claim-validator codes that mean "this free text carries a structured value", and the typed
# editor that normalises it. Words such as "free" or a bare number have no typed value: the owner
# still sees the exact text before saving it, so they keep the one-tap path.
_EDITOR_FOR_CODE = (
    ("MONEY", "money"),
    ("TIME", "weekly_hours"),
    ("PHONE", "phone"),
    ("EMAIL", "email"),
    ("URL", "url"),
)


def editor_type(candidate: FactCandidate) -> str | None:
    """The typed editor an owner-answer candidate must go through, or ``None`` for one tap."""
    if candidate.source_type != "owner_answer" or candidate.value_type != "text":
        return None
    text = str(candidate.proposed_value.get("text", ""))
    codes = {issue.code for issue in validate_claims(text, RenderResult(text), "tr").issues}
    for code, kind in _EDITOR_FOR_CODE:
        if code in codes:
            return kind
    return None


def knowledge_fence(db: Session, workspace: uuid.UUID) -> str:
    """Content-free aggregate invalidation, without loading business bodies."""
    parts = []
    for model in (BusinessFact, FactCandidate):
        row = db.execute(
            select(
                func.count(model.id),
                func.sum(
                    func.hashtextextended(func.concat(model.id, model.status, model.updated_at), 0)
                ),
            ).where(model.workspace_id == workspace)
        ).one()
        parts.append([row[0], str(row[1]) if row[1] is not None else None])
    return payload_hash(parts)


def answer_fence(db: Session, candidate: FactCandidate) -> str | None:
    """The fence before the owner decides the candidate their own answer proposed."""
    if candidate.owner_answer_id is None:
        return None
    return knowledge_fence(db, candidate.workspace_id)


def rebase_answer_fence(db: Session, candidate: FactCandidate, before: str | None) -> None:
    """Deciding the answer's own candidate must not invalidate that answer (D-05).

    An owner answer is usable as evidence only while the knowledge fence it was recorded under
    still holds. Saving or rejecting its candidate changes the fence by itself, so the question
    moves to the new fence, but only if it was current just before: any other change stays stale.
    """
    if before is None or candidate.owner_answer_id is None:
        return
    db.flush()
    question = db.scalar(
        select(OwnerQuestion)
        .join(OwnerAnswer, OwnerAnswer.question_id == OwnerQuestion.id)
        .where(
            OwnerAnswer.id == candidate.owner_answer_id,
            OwnerQuestion.workspace_id == candidate.workspace_id,
        )
    )
    if question is not None and question.knowledge_fence == before:
        question.knowledge_fence = knowledge_fence(db, candidate.workspace_id)


class LearnedFact(BaseModel):
    fact_id: uuid.UUID
    key: str
    category: str
    label: dict[str, str]
    value_type: str
    learned_at: datetime


class LearnedMonth(BaseModel):
    month: str  # YYYY-MM in the workspace timezone
    count: int
    items: list[LearnedFact]


def month_bounds(now: datetime, timezone: str) -> tuple[datetime, datetime]:
    """Start (inclusive) and end (exclusive) of ``now``'s calendar month, as UTC instants."""
    tz = ZoneInfo(timezone)
    start = now.astimezone(tz).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    following = (
        start.replace(year=start.year + 1, month=1)
        if start.month == 12
        else start.replace(month=start.month + 1)
    )
    return start.astimezone(UTC), following.astimezone(UTC)


def learned_month(db: Session, clock: Clock, ctx: WorkspaceContext) -> LearnedMonth:
    start, end = month_bounds(clock.now(), ctx.timezone)
    learned = (
        select(FactVersion.fact_id, func.min(FactVersion.created_at).label("learned_at"))
        .join(FactCandidate, cast(FactCandidate.id, String) == FactVersion.source_ref)
        .where(
            FactVersion.workspace_id == ctx.workspace_id,
            FactCandidate.workspace_id == ctx.workspace_id,
            FactVersion.source_type == "candidate_accepted",
            FactVersion.status == "verified",
            FactCandidate.source_type == "owner_answer",
            FactCandidate.owner_answer_id.is_not(None),
            FactCandidate.status == "accepted",
            FactVersion.created_at >= start,
            FactVersion.created_at < end,
        )
        .group_by(FactVersion.fact_id)
        .subquery()
    )
    rows = db.execute(
        select(BusinessFact, learned.c.learned_at)
        .join(learned, learned.c.fact_id == BusinessFact.id)
        .where(BusinessFact.workspace_id == ctx.workspace_id, BusinessFact.status != "archived")
        .order_by(learned.c.learned_at.desc(), BusinessFact.id)
    ).all()
    local = start.astimezone(ZoneInfo(ctx.timezone))
    return LearnedMonth(
        month=local.strftime("%Y-%m"),
        count=len(rows),
        items=[
            LearnedFact(
                fact_id=fact.id,
                key=fact.key,
                category=fact.category,
                label=fact.label,
                value_type=fact.value_type,
                learned_at=at,
            )
            for fact, at in rows
        ],
    )
