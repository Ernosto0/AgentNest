"""Automation policy routes (api-design.md §2.3)."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_clock, require_membership
from app.core.clock import Clock
from app.core.context import WorkspaceContext
from app.core.db import get_db
from app.policy import service
from app.policy.schemas import PoliciesIn, PoliciesOut, PolicyItem

router = APIRouter(prefix="/workspaces/{workspace_id}/automation-policies", tags=["automation"])


def _out(db: Session, clock: Clock, ctx: WorkspaceContext, modes: dict[str, str]) -> PoliciesOut:
    allowed, level = service.auto_allowed(db, clock, ctx)
    return PoliciesOut(
        items=[PolicyItem(action_class=a, mode=m) for a, m in modes.items()],
        readiness_level=level,
        auto_allowed=allowed,
        reviewed_at=service.reviewed_at(db, ctx),
    )


@router.get("", response_model=PoliciesOut)
def get_policies(
    ctx: WorkspaceContext = Depends(require_membership("approvals.view")),
    db: Session = Depends(get_db),
    clock: Clock = Depends(get_clock),
) -> PoliciesOut:
    return _out(db, clock, ctx, service.get_policies(db, ctx.workspace_id))


@router.put("", response_model=PoliciesOut)
def put_policies(
    body: PoliciesIn,
    ctx: WorkspaceContext = Depends(require_membership("automation.manage")),
    db: Session = Depends(get_db),
    clock: Clock = Depends(get_clock),
) -> PoliciesOut:
    return _out(db, clock, ctx, service.set_policies(db, clock, ctx, body))


@router.post("/review", response_model=PoliciesOut)
def review_policies(
    ctx: WorkspaceContext = Depends(require_membership("automation.manage")),
    db: Session = Depends(get_db),
    clock: Clock = Depends(get_clock),
) -> PoliciesOut:
    """The owner confirms the automation settings were looked at. Idempotent."""
    service.mark_reviewed(db, clock, ctx)
    return _out(db, clock, ctx, service.get_policies(db, ctx.workspace_id))
