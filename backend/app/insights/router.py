"""Instagram Insights router (P5-Insights).

Accessible to all workspace members (owners and staff).
"""

import uuid
from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_clock, require_membership
from app.core.clock import Clock
from app.core.context import WorkspaceContext
from app.core.db import get_db
from app.insights import service
from app.insights.schemas import (
    AudienceOut,
    InsightsContentListOut,
    InsightsSummaryOut,
)

router = APIRouter(
    prefix="/workspaces/{workspace_id}/accounts/{account_id}/insights", tags=["insights"]
)


@router.get("/summary", response_model=InsightsSummaryOut)
def get_insights_summary(
    account_id: uuid.UUID,
    range: Literal["7d", "28d"] = Query(default="7d"),
    ctx: WorkspaceContext = Depends(require_membership()),
    db: Session = Depends(get_db),
    clock: Clock = Depends(get_clock),
) -> InsightsSummaryOut:
    range_days = 28 if range == "28d" else 7
    return service.get_summary(db, ctx.workspace_id, account_id, range_days=range_days, clock=clock)


@router.get("/content", response_model=InsightsContentListOut)
def get_insights_content(
    account_id: uuid.UUID,
    kind: Literal["story", "feed"] | None = Query(default=None),
    limit: int = Query(default=10, ge=1, le=50),
    ctx: WorkspaceContext = Depends(require_membership()),
    db: Session = Depends(get_db),
) -> InsightsContentListOut:
    return service.get_content_insights(db, ctx.workspace_id, account_id, kind=kind, limit=limit)


@router.get("/audience", response_model=AudienceOut)
def get_insights_audience(
    account_id: uuid.UUID,
    ctx: WorkspaceContext = Depends(require_membership()),
    db: Session = Depends(get_db),
) -> AudienceOut:
    return service.get_audience_data(db, ctx.workspace_id, account_id)
