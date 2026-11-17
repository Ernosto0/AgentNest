"""Owner endpoints for approval-ladder suggestions (D-02).

Reading and dismissing live here. Confirming is deliberately **not** here: it goes through the
existing ``POST /agent/delegation/preview`` and ``/apply`` endpoints with the suggestion's own
change (``DelegationChange.suggestion_id``), so one code path decides every delegation change.
"""

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.agent import suggestions
from app.api.deps import get_clock, require_membership
from app.core.clock import Clock
from app.core.context import WorkspaceContext
from app.core.db import get_db

router = APIRouter(prefix="/workspaces/{workspace_id}/delegation-suggestions", tags=["agent"])


class SuggestionList(BaseModel):
    items: list[suggestions.SuggestionOut]


class SuggestionDismissed(BaseModel):
    id: uuid.UUID
    status: str
    cooldown_until: datetime | None


@router.get("", response_model=SuggestionList)
def list_suggestions(
    ctx: WorkspaceContext = Depends(require_membership("agent.delegation.manage")),
    db: Session = Depends(get_db),
    clock: Clock = Depends(get_clock),
) -> SuggestionList:
    """Open suggestions, each with the exact change to preview and apply."""
    return SuggestionList(items=suggestions.list_pending(db, clock, ctx))


@router.post("/{suggestion_id}/dismiss", response_model=SuggestionDismissed)
def dismiss_suggestion(
    suggestion_id: uuid.UUID,
    ctx: WorkspaceContext = Depends(require_membership("agent.delegation.manage")),
    db: Session = Depends(get_db),
    clock: Clock = Depends(get_clock),
) -> SuggestionDismissed:
    row = suggestions.dismiss(db, clock, ctx, suggestion_id)
    db.commit()
    return SuggestionDismissed(id=row.id, status=row.status, cooldown_until=row.cooldown_until)
