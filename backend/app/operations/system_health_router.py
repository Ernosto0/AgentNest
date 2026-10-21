"""``GET /workspaces/{ws}/system-health`` (api-design.md section 2.8). Owner and manager only."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_app_settings, get_clock, require_membership
from app.core.clock import Clock
from app.core.config import Settings
from app.core.context import WorkspaceContext
from app.core.db import get_db
from app.operations import system_health
from app.operations.system_health import SystemHealthOut

router = APIRouter(prefix="/workspaces/{workspace_id}/system-health", tags=["operations"])


@router.get("", response_model=SystemHealthOut)
def get_system_health(
    ctx: WorkspaceContext = Depends(require_membership("system_health.view")),
    db: Session = Depends(get_db),
    clock: Clock = Depends(get_clock),
    settings: Settings = Depends(get_app_settings),
) -> SystemHealthOut:
    return system_health.build(db, clock, settings, ctx)
