"""Explicit member moderation requests recorded directly in the shared operation ledger."""

import uuid
from datetime import timedelta
from typing import Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent.models import AgentAction
from app.agent.repository import scoped_account
from app.api.deps import get_clock, require_membership
from app.audit.service import record
from app.comments.models import PublicMedia
from app.comments.reservations import unresolved
from app.comments.router import comment_scope
from app.core.canonical import payload_hash
from app.core.clock import Clock
from app.core.context import WorkspaceContext
from app.core.db import get_db
from app.core.errors import AppError
from app.identity.permissions import has_permission
from app.integrations.instagram import queries
from app.jobs.queue import enqueue
from app.operations.models import Operation

router = APIRouter(
    prefix="/workspaces/{workspace_id}/accounts/{account_id}/comments", tags=["comments"]
)


class ManualModeration(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=1)
    effect: Literal["hide", "unhide", "delete"]
    client_request_id: uuid.UUID


class ManualModerationOut(BaseModel):
    operation_id: uuid.UUID
    status: str
    effect: str
    is_simulated: bool


def out(op: Operation) -> ManualModerationOut:
    return ManualModerationOut(
        operation_id=op.id,
        status=op.status,
        effect=op.operation_type.removeprefix("comment_"),
        is_simulated=op.is_simulated,
    )


@router.post("/{comment_id}/moderate", status_code=202, response_model=ManualModerationOut)
def moderate(
    account_id: uuid.UUID,
    comment_id: uuid.UUID,
    body: ManualModeration,
    ctx: WorkspaceContext = Depends(require_membership("comments.moderate")),
    db: Session = Depends(get_db),
    clock: Clock = Depends(get_clock),
) -> ManualModerationOut:
    from app.operations.manual_comments import ManualCommentPayload

    if (
        ctx.actor.type != "user"
        or ctx.actor.id is None
        or not has_permission(ctx.role, "comments.moderate")
    ):
        raise AppError("FORBIDDEN", permission="comments.moderate")
    target = comment_scope(db, ctx, account_id, comment_id)
    scoped_account(db, ctx.workspace_id, account_id, lock=True)
    key = f"manual_comment:{ctx.workspace_id}:{account_id}:{ctx.actor.id}:{body.client_request_id}"
    digest = payload_hash(
        {
            "comment_id": str(comment_id),
            "expected_version": body.expected_version,
            "effect": body.effect,
        }
    )
    previous = db.scalar(
        select(Operation).where(
            Operation.workspace_id == ctx.workspace_id, Operation.idempotency_key == key
        )
    )
    if previous is not None:
        if previous.provider_ref.get("request_hash") != digest:
            raise AppError("VERSION_CONFLICT")
        return out(previous)
    db.refresh(target, with_for_update=True)
    account = queries.get_account_in_workspace(db, ctx.workspace_id, account_id)
    media = db.get(PublicMedia, target.media_id)
    if (
        account is None
        or account.provider_kind != "mock"
        or account.status not in {"connected", "degraded"}
        or account.capabilities.get("comment_moderate") is not True
    ):
        raise AppError("CONFLICT_STATE", entity="social_account", status="unavailable")
    if (
        media is None
        or media.ownership_state != "verified_synthetic"
        or media.state == "deleted"
        or target.is_owner
    ):
        raise AppError("CONFLICT_STATE", entity="comment", status=target.state)
    if target.version != body.expected_version:
        raise AppError("VERSION_CONFLICT")
    if (body.effect == "unhide" and target.state != "hidden") or (
        body.effect != "unhide" and target.state != "visible"
    ):
        raise AppError("CONFLICT_STATE", entity="comment", status=target.state)
    agent_pending = db.scalar(
        select(AgentAction.id)
        .where(
            AgentAction.workspace_id == ctx.workspace_id,
            AgentAction.social_account_id == account_id,
            AgentAction.target_ref == str(comment_id),
            AgentAction.action_type.like("comment.%"),
            AgentAction.status.in_(
                (
                    "proposed",
                    "waiting_approval",
                    "authorized",
                    "queued",
                    "in_progress",
                    "outcome_unknown",
                )
            ),
        )
        .limit(1)
    )
    if agent_pending is not None or unresolved(db, ctx.workspace_id, account_id, comment_id):
        raise AppError("CONFLICT_STATE", entity="comment", status="pending_effect")
    op = Operation(
        workspace_id=ctx.workspace_id,
        social_account_id=account_id,
        operation_type=f"comment_{body.effect}",
        idempotency_key=key,
        subject_type="public_comment",
        subject_id=comment_id,
        provider_kind=account.provider_kind,
        status="pending",
        max_attempts=1,
        attempts=0,
        deadline_at=clock.now() + timedelta(minutes=5),
        provider_ref={
            "actor_id": ctx.actor.id,
            "comment_version": target.version,
            "media_version": media.version,
            "effect": body.effect,
            "request_hash": digest,
        },
        is_simulated=account.is_simulated,
        created_at=clock.now(),
    )
    db.add(op)
    db.flush()
    enqueue(
        db,
        "manual_comment_effect",
        ManualCommentPayload(operation_id=op.id),
        workspace_id=ctx.workspace_id,
        correlation_id=op.id,
        dedup_key=f"manual_comment_effect:{op.id}",
        clock=clock,
    )
    record(
        db,
        ctx,
        "operation.started",
        "operation",
        op.id,
        {"status": "pending", "effect": body.effect},
        is_simulated=account.is_simulated,
        clock=clock,
    )
    db.commit()
    return out(op)


class ManualModerationPage(BaseModel):
    items: list[ManualModerationOut]
    next_cursor: uuid.UUID | None


@router.get("/{comment_id}/moderation-operations", response_model=ManualModerationPage)
def history(
    account_id: uuid.UUID,
    comment_id: uuid.UUID,
    limit: int = Query(20, ge=1, le=50),
    cursor: uuid.UUID | None = None,
    ctx: WorkspaceContext = Depends(require_membership("comments.view")),
    db: Session = Depends(get_db),
) -> ManualModerationPage:
    comment_scope(db, ctx, account_id, comment_id)
    query = select(Operation).where(
        Operation.workspace_id == ctx.workspace_id,
        Operation.social_account_id == account_id,
        Operation.subject_type == "public_comment",
        Operation.subject_id == comment_id,
    )
    if cursor:
        if db.scalar(query.where(Operation.id == cursor)) is None:
            raise AppError("NOT_FOUND")
        query = query.where(Operation.id < cursor)
    rows = list(db.scalars(query.order_by(Operation.id.desc()).limit(limit + 1)))
    return ManualModerationPage(
        items=[out(op) for op in rows[:limit]],
        next_cursor=rows[limit - 1].id if len(rows) > limit else None,
    )
