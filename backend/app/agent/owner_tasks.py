"""Authenticated member tasks for one account agent; customer events never enter here."""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent.models import AgentSession, AgentThread, OwnerTask
from app.agent.repository import AgentScopeError, add_event_and_wake, scoped_account
from app.core.clock import Clock
from app.core.context import ActorRef, WorkspaceContext
from app.core.errors import AppError
from app.identity.models import User, Workspace, WorkspaceMember
from app.identity.permissions import has_permission
from app.identity.service import workspace_context


def submit(
    db: Session,
    clock: Clock,
    ctx: WorkspaceContext,
    account_id: uuid.UUID,
    request_text: str,
    client_request_id: uuid.UUID,
) -> OwnerTask:
    if (
        ctx.actor.type != "user"
        or ctx.actor.id is None
        or not has_permission(ctx.role, "commands.use")
    ):
        raise AppError("FORBIDDEN", permission="commands.use")
    user_id = uuid.UUID(ctx.actor.id)
    account = scoped_account(db, ctx.workspace_id, account_id, lock=True)
    if account.controller_mode != "agent" or account.state != "active":
        raise AppError("CONFLICT_STATE", entity="account_agent", status=account.state)
    prior = db.scalar(
        select(OwnerTask).where(
            OwnerTask.workspace_id == ctx.workspace_id,
            OwnerTask.social_account_id == account_id,
            OwnerTask.requester_user_id == user_id,
            OwnerTask.client_request_id == client_request_id,
        )
    )
    if prior is not None:
        if prior.request_text != request_text:
            raise AppError("CONFLICT_STATE", entity="owner_task", status="request_id_reused")
        return prior
    now = clock.now()
    thread = AgentThread(
        workspace_id=ctx.workspace_id,
        social_account_id=account_id,
        surface="owner_task",
        source_ref=f"owner-task:{client_request_id}:{user_id}",
        controller_epoch=account.controller_epoch,
        state="queued",
        handling_mode="agent",
        thread_version=1,
        event_cursor=0,
        created_at=now,
        updated_at=now,
    )
    db.add(thread)
    db.flush()
    task = OwnerTask(
        workspace_id=ctx.workspace_id,
        social_account_id=account_id,
        thread_id=thread.id,
        requester_user_id=user_id,
        requester_role=ctx.role or "",
        source_channel="api",
        client_request_id=client_request_id,
        request_text=request_text,
        created_at=now,
        updated_at=now,
    )
    db.add(task)
    db.flush()
    add_event_and_wake(
        db,
        workspace_id=ctx.workspace_id,
        account_id=account_id,
        thread_id=thread.id,
        kind="owner_task",
        source_kind="owner_task",
        source_key=str(task.id),
        source_id=str(task.id),
        source_version=1,
        clock=clock,
    )
    db.commit()
    return task


def get(db: Session, ctx: WorkspaceContext, account_id: uuid.UUID, task_id: uuid.UUID) -> OwnerTask:
    if ctx.actor.type != "user" or ctx.actor.id is None:
        raise AppError("FORBIDDEN", permission="commands.use")
    task = db.scalar(
        select(OwnerTask).where(
            OwnerTask.id == task_id,
            OwnerTask.workspace_id == ctx.workspace_id,
            OwnerTask.social_account_id == account_id,
            OwnerTask.requester_user_id == uuid.UUID(ctx.actor.id),
        )
    )
    if task is None:
        raise AppError("NOT_FOUND")
    return task


def current_context(db: Session, task: OwnerTask) -> WorkspaceContext | None:
    """Reconstruct current membership; a stored role is never ongoing authority."""
    member = db.get(WorkspaceMember, (task.workspace_id, task.requester_user_id))
    user = db.get(User, task.requester_user_id)
    workspace = db.get(Workspace, task.workspace_id)
    if (
        member is None
        or user is None
        or not user.is_active
        or workspace is None
        or workspace.status != "active"
        or not has_permission(member.role, "commands.use")
    ):
        return None
    return workspace_context(workspace, ActorRef.user(user.id), member.role)


def for_thread(db: Session, thread: AgentThread) -> OwnerTask:
    task = db.scalar(
        select(OwnerTask).where(
            OwnerTask.workspace_id == thread.workspace_id,
            OwnerTask.social_account_id == thread.social_account_id,
            OwnerTask.thread_id == thread.id,
        )
    )
    if task is None or thread.surface != "owner_task":
        raise AgentScopeError("owner task thread missing")
    return task


def outcome(db: Session, task: OwnerTask) -> tuple[str, str | None]:
    goal = db.scalar(
        select(AgentSession)
        .where(
            AgentSession.workspace_id == task.workspace_id,
            AgentSession.thread_id == task.thread_id,
        )
        .order_by(AgentSession.created_at.desc())
        .limit(1)
    )
    return (goal.status, goal.outcome_code) if goal is not None else ("queued", None)
