"""Approved answers (business-knowledge.md §9): answers the owner approved once and wants
reused. This module is the single place that reads and writes the table.

Drafting reads the ``active`` and ``needs_review`` answers in the reply language. The model may
pick one by id; code renders its template from verified facts and runs the claim validator on
it like any other reply, so an answer with a stale literal value can never be sent.
"""

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.context import WorkspaceContext
from app.knowledge.models import ApprovedAnswer

DRAFTING_STATUSES = ("active", "needs_review")


@dataclass(frozen=True)
class AnswerView:
    id: uuid.UUID
    title: str
    intent: str
    example_questions: tuple[str, ...]
    answer_template: str
    language: str
    status: str
    version: int


def _view(answer: ApprovedAnswer) -> AnswerView:
    return AnswerView(
        id=answer.id,
        title=answer.title,
        intent=answer.intent,
        example_questions=tuple(answer.example_questions),
        answer_template=answer.answer_template,
        language=answer.language,
        status=answer.status,
        version=answer.version,
    )


def list_for_drafting(session: Session, ctx: WorkspaceContext, language: str) -> list[AnswerView]:
    rows = session.scalars(
        select(ApprovedAnswer)
        .where(
            ApprovedAnswer.workspace_id == ctx.workspace_id,
            ApprovedAnswer.language == language,
            ApprovedAnswer.status.in_(DRAFTING_STATUSES),
        )
        .order_by(ApprovedAnswer.created_at, ApprovedAnswer.id)
    )
    return [_view(row) for row in rows]


def get_answer(
    session: Session, ctx: WorkspaceContext, answer_id: uuid.UUID, *, lock: bool = False
) -> ApprovedAnswer | None:
    stmt = select(ApprovedAnswer).where(
        ApprovedAnswer.workspace_id == ctx.workspace_id, ApprovedAnswer.id == answer_id
    )
    return session.scalars(stmt.with_for_update() if lock else stmt).one_or_none()
