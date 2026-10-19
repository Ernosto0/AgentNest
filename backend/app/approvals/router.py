"""Approval routes (api-design.md §2.5). Thin: validate, call the service, map to a model.

The decision endpoint takes only an explicit approval id and the payload hash the client
displayed: nothing else can approve anything (INV-04, INV-16).
"""

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_clock, require_membership
from app.approvals import repository as repo
from app.approvals import service
from app.approvals.schemas import ApprovalAction, ApprovalOut, ApprovalStatus, DecisionIn
from app.approvals.views import approval_out
from app.core.clock import Clock
from app.core.context import WorkspaceContext
from app.core.db import get_db
from app.core.errors import AppError
from app.core.pagination import Page

router = APIRouter(prefix="/workspaces/{workspace_id}/approvals", tags=["approvals"])


@router.get("", response_model=Page[ApprovalOut])
def list_approvals(
    status: ApprovalStatus | None = None,
    action: ApprovalAction | None = None,
    limit: int = 50,
    ctx: WorkspaceContext = Depends(require_membership("approvals.view")),
    db: Session = Depends(get_db),
    clock: Clock = Depends(get_clock),
) -> Page[ApprovalOut]:
    service.expire_due_in_workspace(db, clock, ctx)  # lazy expiry: never show a stale "pending"
    items = repo.list_approvals(db, ctx, status=status, action=action, limit=limit)
    return Page(items=[approval_out(db, clock, ctx, a) for a in items])


@router.get("/{approval_id}", response_model=ApprovalOut)
def get_approval(
    approval_id: uuid.UUID,
    ctx: WorkspaceContext = Depends(require_membership("approvals.view")),
    db: Session = Depends(get_db),
    clock: Clock = Depends(get_clock),
) -> ApprovalOut:
    service.expire_due_in_workspace(db, clock, ctx)
    approval = repo.get_approval(db, ctx, approval_id)
    if approval is None:
        raise AppError("NOT_FOUND")
    return approval_out(db, clock, ctx, approval)


@router.post("/{approval_id}/decision", response_model=ApprovalOut)
def decide(
    approval_id: uuid.UUID,
    body: DecisionIn,
    ctx: WorkspaceContext = Depends(require_membership()),
    db: Session = Depends(get_db),
    clock: Clock = Depends(get_clock),
) -> ApprovalOut:
    """Permission is checked per approval (``required_permission``, or the requester of a
    confirmation), so any member reaches this route and unauthorised ones get 403."""
    approval = service.decide(
        db,
        clock,
        ctx,
        approval_id,
        decision=body.decision,
        payload_hash=body.payload_hash,
        note=body.note,
    )
    return approval_out(db, clock, ctx, approval)
