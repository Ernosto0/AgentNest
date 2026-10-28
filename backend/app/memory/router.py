"""Typed, paginated customer memory inspection/correction. General DSAR API is Phase 8."""

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent.repository import AgentScopeError
from app.api.deps import get_clock, require_membership
from app.core.clock import Clock
from app.core.context import WorkspaceContext
from app.core.db import get_db
from app.core.errors import AppError
from app.memory import service
from app.memory.models import CustomerMemory, MemorySource

router = APIRouter(
    prefix="/workspaces/{workspace_id}/accounts/{account_id}/customers/{customer_id}",
    tags=["customer-memory"],
)


class MemoryOut(BaseModel):
    id: uuid.UUID
    topic: str
    kind: str
    body: str | None
    version: int
    expires_at: datetime


class MemoryPage(BaseModel):
    items: list[MemoryOut]
    next_cursor: uuid.UUID | None


class SourceOut(BaseModel):
    id: uuid.UUID
    memory_id: uuid.UUID
    memory_version: int
    message_id: uuid.UUID | None
    removed: bool
    observed_at: datetime


class SourcePage(BaseModel):
    items: list[SourceOut]
    next_cursor: uuid.UUID | None


class ChangedOut(BaseModel):
    changed: bool = True


def identity(db: Session, ctx: WorkspaceContext, account: uuid.UUID, customer: uuid.UUID) -> None:
    try:
        service.scoped_identity(db, ctx, account, customer)
    except AgentScopeError as exc:
        raise AppError("NOT_FOUND") from exc


@router.get("/memory", response_model=MemoryPage)
def inspect_memory(
    account_id: uuid.UUID,
    customer_id: uuid.UUID,
    limit: int = Query(20, ge=1, le=50),
    cursor: uuid.UUID | None = None,
    ctx: WorkspaceContext = Depends(require_membership()),
    db: Session = Depends(get_db),
    clock: Clock = Depends(get_clock),
) -> MemoryPage:
    identity(db, ctx, account_id, customer_id)
    query = select(CustomerMemory).where(
        CustomerMemory.workspace_id == ctx.workspace_id,
        CustomerMemory.social_account_id == account_id,
        CustomerMemory.customer_identity_id == customer_id,
    )
    if cursor:
        query = query.where(CustomerMemory.id > cursor)
    rows = list(db.scalars(query.order_by(CustomerMemory.id).limit(limit + 1)))
    return MemoryPage(
        items=[
            MemoryOut(
                id=m.id,
                topic=m.topic,
                kind=m.kind,
                body=m.body if service.memory_deadline(m) > clock.now() else None,
                version=m.version,
                expires_at=service.memory_deadline(m),
            )
            for m in rows[:limit]
        ],
        next_cursor=rows[limit - 1].id if len(rows) > limit else None,
    )


@router.get("/sources", response_model=SourcePage)
def inspect_sources(
    account_id: uuid.UUID,
    customer_id: uuid.UUID,
    limit: int = Query(20, ge=1, le=50),
    cursor: uuid.UUID | None = None,
    ctx: WorkspaceContext = Depends(require_membership()),
    db: Session = Depends(get_db),
) -> SourcePage:
    identity(db, ctx, account_id, customer_id)
    query = select(MemorySource).where(
        MemorySource.workspace_id == ctx.workspace_id,
        MemorySource.social_account_id == account_id,
        MemorySource.customer_identity_id == customer_id,
    )
    if cursor:
        query = query.where(MemorySource.id > cursor)
    rows = list(db.scalars(query.order_by(MemorySource.id).limit(limit + 1)))
    return SourcePage(
        items=[
            SourceOut(
                id=s.id,
                memory_id=s.memory_id,
                memory_version=s.memory_version,
                message_id=s.message_id if not s.removed else None,
                removed=s.removed,
                observed_at=s.observed_at,
            )
            for s in rows[:limit]
        ],
        next_cursor=rows[limit - 1].id if len(rows) > limit else None,
    )


@router.post("/memory/{memory_id}/correct", response_model=ChangedOut)
def correct_memory(
    account_id: uuid.UUID,
    customer_id: uuid.UUID,
    memory_id: uuid.UUID,
    body: service.MemoryChange,
    ctx: WorkspaceContext = Depends(require_membership("memory.correct")),
    db: Session = Depends(get_db),
    clock: Clock = Depends(get_clock),
) -> ChangedOut:
    identity(db, ctx, account_id, customer_id)
    service.change(db, clock, ctx, account_id, customer_id, memory_id, body)
    db.commit()
    return ChangedOut()


@router.post("/memory/{memory_id}/forget", response_model=ChangedOut)
def forget_memory(
    account_id: uuid.UUID,
    customer_id: uuid.UUID,
    memory_id: uuid.UUID,
    ctx: WorkspaceContext = Depends(require_membership("memory.forget")),
    db: Session = Depends(get_db),
    clock: Clock = Depends(get_clock),
) -> ChangedOut:
    identity(db, ctx, account_id, customer_id)
    service.change(db, clock, ctx, account_id, customer_id, memory_id, None)
    db.commit()
    return ChangedOut()
