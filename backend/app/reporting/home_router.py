"""Workspace-scoped Today attention summary."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import require_membership
from app.core.context import WorkspaceContext
from app.core.db import get_db
from app.reporting.home import attention_counts

router = APIRouter(prefix="/workspaces/{workspace_id}/home", tags=["reports"])


class HomeAttentionOut(BaseModel):
    drafts: int | None
    unanswered_comments: int


@router.get("/attention", response_model=HomeAttentionOut)
def get_home_attention(
    ctx: WorkspaceContext = Depends(require_membership()),
    db: Session = Depends(get_db),
) -> HomeAttentionOut:
    return HomeAttentionOut.model_validate(attention_counts(db, ctx))
