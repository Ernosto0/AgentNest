"""Scoped typed question lists, details and explicit information decisions."""

import uuid
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent.repository import AgentScopeError, scoped_account
from app.api.deps import get_clock, require_membership
from app.core.clock import Clock
from app.core.context import WorkspaceContext
from app.core.db import get_db
from app.core.errors import AppError
from app.owner_requests import service
from app.owner_requests.models import OwnerAnswer, OwnerQuestion

router = APIRouter(
    prefix="/workspaces/{workspace_id}/accounts/{account_id}/owner-questions",
    tags=["owner-questions"],
)


class QuestionOut(BaseModel):
    id: uuid.UUID
    thread_id: uuid.UUID
    customer_id: uuid.UUID
    source_cursor: int
    required_info: service.RequiredInfo
    visibility: service.Visibility
    body: str | None
    state: Literal["pending", "answered", "expired", "cancelled"]
    version: int
    answer_id: uuid.UUID | None
    expires_at: datetime


class QuestionPage(BaseModel):
    items: list[QuestionOut]
    next_cursor: uuid.UUID | None


class AnswerOut(BaseModel):
    id: uuid.UUID
    question_id: uuid.UUID
    version: int
    kind: Literal["answer", "proposal", "cancel"]
    body: str | None
    author_role: str
    candidate_id: uuid.UUID | None
    expires_at: datetime


class AnswerPage(BaseModel):
    items: list[AnswerOut]
    next_cursor: uuid.UUID | None


def question_out(q: OwnerQuestion, clock: Clock) -> QuestionOut:
    return QuestionOut(
        id=q.id,
        thread_id=q.thread_id,
        customer_id=q.customer_identity_id,
        source_cursor=q.source_cursor,
        required_info=q.required_info,
        visibility=q.visibility,
        body=q.body if q.expires_at > clock.now() else None,
        state="expired"
        if q.expires_at <= clock.now() and q.state in {"pending", "answered"}
        else q.state,
        version=q.version,
        answer_id=q.answer_id,
        expires_at=q.expires_at,
    )


def answer_out(a: OwnerAnswer, clock: Clock) -> AnswerOut:
    return AnswerOut(
        id=a.id,
        question_id=a.question_id,
        version=a.version,
        kind=a.kind,
        body=a.body if a.expires_at > clock.now() else None,
        author_role=a.author_role,
        candidate_id=a.candidate_id,
        expires_at=a.expires_at,
    )


@router.get("", response_model=QuestionPage)
def list_questions(
    account_id: uuid.UUID,
    limit: int = Query(20, ge=1, le=50),
    cursor: uuid.UUID | None = None,
    customer_id: uuid.UUID | None = None,
    ctx: WorkspaceContext = Depends(require_membership()),
    db: Session = Depends(get_db),
    clock: Clock = Depends(get_clock),
) -> QuestionPage:
    try:
        scoped_account(db, ctx.workspace_id, account_id)
    except AgentScopeError as exc:
        raise AppError("NOT_FOUND") from exc
    query = select(OwnerQuestion).where(
        OwnerQuestion.workspace_id == ctx.workspace_id,
        OwnerQuestion.social_account_id == account_id,
    )
    if customer_id:
        from app.memory.service import scoped_identity

        try:
            scoped_identity(db, ctx, account_id, customer_id)
        except AgentScopeError as exc:
            raise AppError("NOT_FOUND") from exc
        query = query.where(OwnerQuestion.customer_identity_id == customer_id)
    if cursor:
        query = query.where(OwnerQuestion.id > cursor)
    rows = list(db.scalars(query.order_by(OwnerQuestion.id).limit(limit + 1)))
    return QuestionPage(
        items=[question_out(q, clock) for q in rows[:limit]],
        next_cursor=rows[limit - 1].id if len(rows) > limit else None,
    )


@router.get("/{question_id}", response_model=QuestionOut)
def detail(
    account_id: uuid.UUID,
    question_id: uuid.UUID,
    ctx: WorkspaceContext = Depends(require_membership()),
    db: Session = Depends(get_db),
    clock: Clock = Depends(get_clock),
) -> QuestionOut:
    return question_out(service.question_scope(db, ctx, account_id, question_id), clock)


@router.get("/{question_id}/answers", response_model=AnswerPage)
def list_answers(
    account_id: uuid.UUID,
    question_id: uuid.UUID,
    limit: int = Query(20, ge=1, le=50),
    cursor: uuid.UUID | None = None,
    ctx: WorkspaceContext = Depends(require_membership()),
    db: Session = Depends(get_db),
    clock: Clock = Depends(get_clock),
) -> AnswerPage:
    service.question_scope(db, ctx, account_id, question_id)
    query = select(OwnerAnswer).where(
        OwnerAnswer.workspace_id == ctx.workspace_id, OwnerAnswer.question_id == question_id
    )
    if cursor:
        query = query.where(OwnerAnswer.id > cursor)
    rows = list(db.scalars(query.order_by(OwnerAnswer.id).limit(limit + 1)))
    return AnswerPage(
        items=[answer_out(a, clock) for a in rows[:limit]],
        next_cursor=rows[limit - 1].id if len(rows) > limit else None,
    )


@router.post("/{question_id}/answer", response_model=AnswerOut)
def answer(
    account_id: uuid.UUID,
    question_id: uuid.UUID,
    body: service.AnswerRequest,
    ctx: WorkspaceContext = Depends(require_membership("owner_questions.propose")),
    db: Session = Depends(get_db),
    clock: Clock = Depends(get_clock),
) -> AnswerOut:
    a = service.decide(db, clock, ctx, account_id, question_id, body)
    db.commit()
    return answer_out(a, clock)


@router.post("/{question_id}/cancel", response_model=AnswerOut)
def cancel(
    account_id: uuid.UUID,
    question_id: uuid.UUID,
    body: service.CancelRequest,
    ctx: WorkspaceContext = Depends(require_membership("owner_questions.answer")),
    db: Session = Depends(get_db),
    clock: Clock = Depends(get_clock),
) -> AnswerOut:
    a = service.decide(db, clock, ctx, account_id, question_id, body)
    db.commit()
    return answer_out(a, clock)
