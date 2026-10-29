"""Member-authenticated account task intake and inspection."""

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select, true
from sqlalchemy.orm import Session

from app.agent import owner_tasks
from app.agent.models import AgentAction, OwnerTask
from app.agent.repository import AgentScopeError, scoped_account
from app.api.deps import get_clock, require_membership
from app.core.clock import Clock
from app.core.context import WorkspaceContext
from app.core.db import get_db
from app.core.errors import AppError
from app.core.pagination import Page

router = APIRouter(
    prefix="/workspaces/{workspace_id}/accounts/{account_id}/agent/tasks", tags=["agent"]
)


class TaskCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(min_length=1, max_length=4000)
    client_request_id: uuid.UUID
    media_asset_id: uuid.UUID | None = None
    content_id: uuid.UUID | None = None


class TaskAnswer(TaskCreate):
    expected_version: int = Field(ge=1)


class TaskOut(BaseModel):
    id: uuid.UUID
    account_id: uuid.UUID
    source_channel: str
    status: str
    outcome_code: str | None
    created_at: datetime
    clarification: str | None
    question_version: int | None
    actions: list["ContentResult"]


class ContentResult(BaseModel):
    action_id: uuid.UUID
    action_type: str
    status: str
    outcome_code: str | None = None
    approval_id: uuid.UUID | None = None
    content_id: uuid.UUID | None = None
    content_status: str | None = None
    is_simulated: bool | None = None


def _out(db: Session, task: OwnerTask) -> TaskOut:
    from app.agent.content import result

    status, code = owner_tasks.outcome(db, task)
    return TaskOut(
        id=task.id,
        account_id=task.social_account_id,
        source_channel=task.source_channel,
        status=status,
        outcome_code=code,
        created_at=task.created_at,
        clarification=task.clarification,
        question_version=len(task.answers) + 1 if task.clarification else None,
        actions=[
            ContentResult.model_validate(result(db, action))
            for action in db.scalars(
                select(AgentAction)
                .where(
                    AgentAction.workspace_id == task.workspace_id,
                    AgentAction.thread_id == task.thread_id,
                    AgentAction.content_intent.is_not(None),
                )
                .order_by(AgentAction.created_at, AgentAction.id)
            ).all()
        ],
    )


@router.post("", status_code=202, response_model=TaskOut)
def submit_task(
    account_id: uuid.UUID,
    body: TaskCreate,
    ctx: WorkspaceContext = Depends(require_membership("commands.use")),
    db: Session = Depends(get_db),
    clock: Clock = Depends(get_clock),
) -> TaskOut:
    text = body.text.strip()
    if not text:
        raise AppError("VALIDATION_FAILED")
    try:
        task = owner_tasks.submit(
            db,
            clock,
            ctx,
            account_id,
            text,
            body.client_request_id,
            media_asset_id=body.media_asset_id,
            content_id=body.content_id,
        )
    except AgentScopeError as exc:
        raise AppError("NOT_FOUND") from exc
    return _out(db, task)


@router.get("", response_model=Page[TaskOut])
def list_tasks(
    account_id: uuid.UUID,
    limit: int = 20,
    cursor: uuid.UUID | None = None,
    ctx: WorkspaceContext = Depends(require_membership("commands.use")),
    db: Session = Depends(get_db),
) -> Page[TaskOut]:
    if ctx.actor.id is None:
        raise AppError("FORBIDDEN", permission="commands.use")
    try:
        scoped_account(db, ctx.workspace_id, account_id)
    except AgentScopeError as exc:
        raise AppError("NOT_FOUND") from exc
    if cursor is not None:
        owner_tasks.get(db, ctx, account_id, cursor)
    limit = min(max(limit, 1), 100)
    tasks = db.scalars(
        select(OwnerTask)
        .where(
            OwnerTask.workspace_id == ctx.workspace_id,
            OwnerTask.social_account_id == account_id,
            OwnerTask.requester_user_id == uuid.UUID(ctx.actor.id),
            OwnerTask.id < cursor if cursor else true(),
        )
        .order_by(OwnerTask.id.desc())
        .limit(limit + 1)
    ).all()
    return Page(
        items=[_out(db, task) for task in tasks[:limit]],
        next_cursor=str(tasks[limit - 1].id) if len(tasks) > limit else None,
    )


@router.get("/{task_id}", response_model=TaskOut)
def get_task(
    account_id: uuid.UUID,
    task_id: uuid.UUID,
    ctx: WorkspaceContext = Depends(require_membership("commands.use")),
    db: Session = Depends(get_db),
) -> TaskOut:
    return _out(db, owner_tasks.get(db, ctx, account_id, task_id))


@router.post("/{task_id}/answers", status_code=202, response_model=TaskOut)
def answer_task(
    account_id: uuid.UUID,
    task_id: uuid.UUID,
    body: TaskAnswer,
    ctx: WorkspaceContext = Depends(require_membership("commands.use")),
    db: Session = Depends(get_db),
    clock: Clock = Depends(get_clock),
) -> TaskOut:
    try:
        task = owner_tasks.answer(
            db,
            clock,
            ctx,
            account_id,
            task_id,
            body.text,
            body.client_request_id,
            body.expected_version,
            media_asset_id=body.media_asset_id,
            content_id=body.content_id,
        )
    except AgentScopeError as exc:
        raise AppError("NOT_FOUND") from exc
    return _out(db, task)
