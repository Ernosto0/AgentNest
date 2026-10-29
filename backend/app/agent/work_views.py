"""Member-safe work projections; public threads never expose a private identity."""

import uuid

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent.control import invalidate_steps, queue_replan
from app.agent.jobs import enqueue_cleanup, wake
from app.agent.models import AgentAction, AgentSession, AgentThread
from app.agent.repository import AgentScopeError, scoped_account, scoped_thread
from app.api.deps import get_clock, require_membership
from app.audit.models import AuditLog
from app.audit.service import record
from app.core.canonical import payload_hash
from app.core.clock import Clock
from app.core.context import WorkspaceContext
from app.core.db import get_db
from app.core.errors import AppError
from app.integrations.instagram.queries import get_account_in_workspace

router = APIRouter(prefix="/workspaces/{workspace_id}", tags=["agent"])


class WorkActionOut(BaseModel):
    id: uuid.UUID
    action_type: str
    status: str
    approval_id: uuid.UUID | None
    operation_id: uuid.UUID | None
    outcome_code: str | None
    is_simulated: bool


class WorkThreadOut(BaseModel):
    id: uuid.UUID
    account_id: uuid.UUID
    surface: str
    source_ref: str
    state: str
    handling_mode: str
    version: int
    customer_id: uuid.UUID | None
    goal: str | None
    is_simulated: bool
    actions: list[WorkActionOut]


class WorkThreadPage(BaseModel):
    items: list[WorkThreadOut]
    next_cursor: uuid.UUID | None


def present(db: Session, thread: AgentThread) -> WorkThreadOut:
    account = get_account_in_workspace(db, thread.workspace_id, thread.social_account_id)
    simulated = bool(account and account.is_simulated)
    goal = db.scalar(
        select(AgentSession)
        .where(
            AgentSession.workspace_id == thread.workspace_id, AgentSession.thread_id == thread.id
        )
        .order_by(AgentSession.created_at.desc())
        .limit(1)
    )
    return WorkThreadOut(
        id=thread.id,
        account_id=thread.social_account_id,
        surface=thread.surface,
        source_ref=thread.source_ref,
        state=thread.state,
        handling_mode=thread.handling_mode,
        version=thread.thread_version,
        customer_id=thread.customer_identity_id if thread.surface == "dm" else None,
        goal=goal.status if goal else None,
        is_simulated=simulated,
        actions=[
            WorkActionOut(
                id=a.id,
                action_type=a.action_type,
                status=a.status,
                approval_id=a.approval_id,
                operation_id=a.operation_id,
                outcome_code=a.outcome_code,
                is_simulated=simulated,
            )
            for a in db.scalars(
                select(AgentAction)
                .where(
                    AgentAction.workspace_id == thread.workspace_id,
                    AgentAction.thread_id == thread.id,
                )
                .order_by(AgentAction.created_at.desc())
                .limit(20)
            )
        ],
    )


@router.get("/accounts/{account_id}/agent/threads", response_model=WorkThreadPage)
def threads(
    account_id: uuid.UUID,
    source_ref: str | None = None,
    limit: int = Query(20, ge=1, le=50),
    cursor: uuid.UUID | None = None,
    ctx: WorkspaceContext = Depends(require_membership()),
    db: Session = Depends(get_db),
) -> WorkThreadPage:
    try:
        scoped_account(db, ctx.workspace_id, account_id)
        if cursor:
            scoped_thread(db, ctx.workspace_id, account_id, cursor)
    except AgentScopeError as exc:
        raise AppError("NOT_FOUND") from exc
    query = select(AgentThread).where(
        AgentThread.workspace_id == ctx.workspace_id,
        AgentThread.social_account_id == account_id,
        AgentThread.surface.in_(("dm", "comment")),
    )
    if source_ref:
        query = query.where(AgentThread.source_ref == source_ref)
    if cursor:
        query = query.where(AgentThread.id > cursor)
    rows = list(db.scalars(query.order_by(AgentThread.id).limit(limit + 1)))
    return WorkThreadPage(
        items=[present(db, row) for row in rows[:limit]],
        next_cursor=rows[limit - 1].id if len(rows) > limit else None,
    )


@router.get("/accounts/{account_id}/agent/threads/{thread_id}", response_model=WorkThreadOut)
def detail(
    account_id: uuid.UUID,
    thread_id: uuid.UUID,
    ctx: WorkspaceContext = Depends(require_membership()),
    db: Session = Depends(get_db),
) -> WorkThreadOut:
    try:
        thread = scoped_thread(db, ctx.workspace_id, account_id, thread_id)
    except AgentScopeError as exc:
        raise AppError("NOT_FOUND") from exc
    if thread.surface not in {"dm", "comment"}:
        raise AppError("NOT_FOUND")
    return present(db, thread)


class WorkControl(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=1)
    client_request_id: uuid.UUID
    handling_mode: str = Field(pattern="^(agent|human)$")


@router.post(
    "/accounts/{account_id}/agent/threads/{thread_id}/control", response_model=WorkThreadOut
)
def control(
    account_id: uuid.UUID,
    thread_id: uuid.UUID,
    body: WorkControl,
    ctx: WorkspaceContext = Depends(require_membership("conversation.takeover")),
    db: Session = Depends(get_db),
    clock: Clock = Depends(get_clock),
) -> WorkThreadOut:
    try:
        account = scoped_account(db, ctx.workspace_id, account_id, lock=True)
        thread = scoped_thread(db, ctx.workspace_id, account_id, thread_id, lock=True)
    except AgentScopeError as exc:
        raise AppError("NOT_FOUND") from exc
    if thread.surface != "comment":
        raise AppError("NOT_FOUND")
    digest = payload_hash(body.model_dump(mode="json"))
    previous = db.scalar(
        select(AuditLog)
        .where(
            AuditLog.workspace_id == ctx.workspace_id,
            AuditLog.resource_id == thread.id,
            AuditLog.action == "agent.thread_transition",
            AuditLog.actor_id == ctx.actor.id,
            AuditLog.metadata_["client_request_id"].astext == str(body.client_request_id),
        )
        .limit(1)
    )
    if previous is not None:
        if previous.metadata_.get("request_hash") != digest:
            raise AppError("VERSION_CONFLICT")
        return present(db, thread)
    if thread.thread_version != body.expected_version:
        raise AppError("VERSION_CONFLICT")
    if body.handling_mode == "agent" and (
        account.controller_mode != "agent" or account.state != "active"
    ):
        raise AppError("CONFLICT_STATE", entity="account_agent", status=account.state)
    thread.handling_mode = body.handling_mode
    thread.thread_version += 1
    thread.ownership_generation += 1
    thread.controller_epoch = account.controller_epoch
    invalidate_steps(db, clock, thread)
    enqueue_cleanup(
        db, clock, ctx.workspace_id, account_id, f"thread:{thread.id}:{thread.ownership_generation}"
    )
    if body.handling_mode == "agent":
        from app.agent.models import ACTIVE_RUN_STATES

        for goal in db.scalars(
            select(AgentSession).where(
                AgentSession.workspace_id == ctx.workspace_id,
                AgentSession.thread_id == thread.id,
                AgentSession.status.in_(ACTIVE_RUN_STATES),
            )
        ):
            queue_replan(db, clock, goal, thread)
            goal.activation_started_at = None
        wake(db, clock, ctx.workspace_id, thread.id, f"release:{thread.ownership_generation}")
    record(
        db,
        ctx,
        "agent.thread_transition",
        "agent_thread",
        thread.id,
        {
            "handling_mode": thread.handling_mode,
            "client_request_id": str(body.client_request_id),
            "request_hash": digest,
        },
        clock=clock,
    )
    db.commit()
    return present(db, thread)


class ExactActionPreview(BaseModel):
    id: uuid.UUID
    account_id: uuid.UUID
    version: int
    payload_hash: str
    status: str
    action_type: str
    text: str | None = None
    target_text: str | None = None
    target_version: int | None = None
    target_ref: str | None = None
    content: dict[str, object] | None = None
    is_simulated: bool


@router.get("/agent-actions/{action_id}", response_model=ExactActionPreview)
def exact_action(
    action_id: uuid.UUID,
    ctx: WorkspaceContext = Depends(require_membership("approvals.view")),
    db: Session = Depends(get_db),
) -> ExactActionPreview:
    from app.agent.router import action_detail
    from app.comments.models import PrivateReplyOpportunity, PublicComment, PublicCommentAction
    from app.inbox.models import ReplyDraft

    action = db.scalar(
        select(AgentAction).where(
            AgentAction.workspace_id == ctx.workspace_id, AgentAction.id == action_id
        )
    )
    if action is None:
        raise AppError("NOT_FOUND")
    account = get_account_in_workspace(db, ctx.workspace_id, action.social_account_id)
    if account is None:
        raise AppError("NOT_FOUND")
    text = None
    target_text = None
    target_version = None
    if action.action_type == "dm.send":
        draft = db.scalar(
            select(ReplyDraft).where(
                ReplyDraft.workspace_id == ctx.workspace_id, ReplyDraft.agent_action_id == action.id
            )
        )
        text = draft.text if draft else None
    elif action.action_type == "comment.private_reply":
        private = db.scalar(
            select(PrivateReplyOpportunity).where(
                PrivateReplyOpportunity.workspace_id == ctx.workspace_id,
                PrivateReplyOpportunity.agent_action_id == action.id,
            )
        )
        text = private.text if private else None
        target = db.get(PublicComment, private.comment_id) if private else None
        if target is not None and target.workspace_id == ctx.workspace_id:
            target_text, target_version = target.text, private.comment_version if private else None
    elif action.action_type.startswith("comment."):
        subject = db.scalar(
            select(PublicCommentAction).where(
                PublicCommentAction.workspace_id == ctx.workspace_id,
                PublicCommentAction.agent_action_id == action.id,
            )
        )
        text = subject.text if subject else None
        target = db.get(PublicComment, subject.comment_id) if subject else None
        if target is not None and target.workspace_id == ctx.workspace_id:
            target_text, target_version = target.text, subject.comment_version if subject else None
    projected = action_detail(action.social_account_id, action.id, ctx, db)
    return ExactActionPreview(
        id=action.id,
        account_id=action.social_account_id,
        version=action.version,
        payload_hash=action.payload_hash,
        status=action.status,
        action_type=action.action_type,
        target_ref=action.target_ref,
        text=text,
        target_text=target_text,
        target_version=target_version,
        content=projected.content.model_dump(mode="json") if projected.content else None,
        is_simulated=account.is_simulated,
    )


class TaskSelectionOut(BaseModel):
    id: uuid.UUID
    label: str
    kind: str


class TaskSelectionPage(BaseModel):
    items: list[TaskSelectionOut]
    next_cursor: uuid.UUID | None


@router.get("/accounts/{account_id}/agent/task-selections", response_model=TaskSelectionPage)
def task_selections(
    account_id: uuid.UUID,
    kind: str = Query(pattern="^(media|content)$"),
    cursor: uuid.UUID | None = None,
    limit: int = Query(20, ge=1, le=50),
    ctx: WorkspaceContext = Depends(require_membership("content.edit")),
    db: Session = Depends(get_db),
) -> TaskSelectionPage:
    from app.content.models import ContentItem, MediaAsset

    try:
        scoped_account(db, ctx.workspace_id, account_id)
    except AgentScopeError as exc:
        raise AppError("NOT_FOUND") from exc
    if kind == "media":
        media_query = select(MediaAsset).where(
            MediaAsset.workspace_id == ctx.workspace_id, MediaAsset.status == "ready"
        )
        if cursor:
            if db.scalar(media_query.where(MediaAsset.id == cursor)) is None:
                raise AppError("NOT_FOUND")
            media_query = media_query.where(MediaAsset.id > cursor)
        media_rows = list(db.scalars(media_query.order_by(MediaAsset.id).limit(limit + 1)))
        return TaskSelectionPage(
            items=[
                TaskSelectionOut(
                    id=row.id,
                    kind=kind,
                    label=row.original_filename or f"{row.width} ? {row.height}",
                )
                for row in media_rows[:limit]
            ],
            next_cursor=media_rows[limit - 1].id if len(media_rows) > limit else None,
        )
    content_query = select(ContentItem).where(
        ContentItem.workspace_id == ctx.workspace_id, ContentItem.social_account_id == account_id
    )
    if cursor:
        if db.scalar(content_query.where(ContentItem.id == cursor)) is None:
            raise AppError("NOT_FOUND")
        content_query = content_query.where(ContentItem.id > cursor)
    content_rows = list(db.scalars(content_query.order_by(ContentItem.id).limit(limit + 1)))
    return TaskSelectionPage(
        items=[
            TaskSelectionOut(id=row.id, kind=kind, label=row.title) for row in content_rows[:limit]
        ],
        next_cursor=content_rows[limit - 1].id if len(content_rows) > limit else None,
    )
