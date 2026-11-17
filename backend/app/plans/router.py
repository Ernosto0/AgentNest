"""``GET /workspaces/{id}/usage``: the plan and this period's AI reply usage (owner, manager)."""

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_clock, require_membership
from app.core.clock import Clock
from app.core.context import WorkspaceContext
from app.core.db import get_db
from app.plans import service
from app.plans.models import WorkspacePlan

router = APIRouter(prefix="/workspaces/{workspace_id}/usage", tags=["plans"])


class UsageOut(BaseModel):
    plan: Literal["starter", "growth", "pro"]
    status: Literal["trial", "active", "past_due", "cancelled"]
    monthly_quota: int  # the plan's own quota
    quota_override: int | None  # an operator's per-workspace quota, when set
    quota: int  # what applies: the override, else the plan's
    used: int
    grace_limit: int  # drafting pauses at this many (the quota plus 10%)
    period_start: datetime
    period_end: datetime
    # normal < warning (80%) < grace (100%, drafting continues) < paused (the grace is used up)
    state: Literal["normal", "warning", "grace", "paused"]


def view(row: WorkspacePlan) -> UsageOut:
    return UsageOut(
        plan=row.plan,
        status=row.status,
        monthly_quota=row.monthly_quota,
        quota_override=row.quota_override,
        quota=service.quota(row),
        used=row.used,
        grace_limit=service.limit(row),
        period_start=row.period_start,
        period_end=row.period_end,
        state=service.state(row),
    )


@router.get("", response_model=UsageOut)
def get_usage(
    ctx: WorkspaceContext = Depends(require_membership("system_health.view")),
    db: Session = Depends(get_db),
    clock: Clock = Depends(get_clock),
) -> UsageOut:
    result = view(service.get_plan(db, clock, ctx.workspace_id))
    db.commit()
    return result
