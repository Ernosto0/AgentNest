"""Notification routes (api-design.md §2.8, basic in Phase 3).

A user only ever sees their own notifications; someone else's id is a 404 (INV-01).
"""

import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import current_auth, get_clock, require_membership
from app.core.clock import Clock
from app.core.context import WorkspaceContext
from app.core.db import get_db
from app.identity.service import AuthenticatedSession
from app.notifications import service
from app.notifications.models import Notification

router = APIRouter(prefix="/workspaces/{workspace_id}/notifications", tags=["notifications"])


class NotificationOut(BaseModel):
    id: uuid.UUID
    type: str
    severity: str
    params: dict[str, Any]
    subject_type: str | None
    subject_id: uuid.UUID | None
    is_simulated: bool
    read_at: datetime | None
    created_at: datetime


class NotificationList(BaseModel):
    items: list[NotificationOut]
    unread_count: int
    next_cursor: str | None = None


def _out(n: Notification) -> NotificationOut:
    return NotificationOut(
        id=n.id,
        type=n.type,
        severity=n.severity,
        params=n.params,
        subject_type=n.subject_type,
        subject_id=n.subject_id,
        is_simulated=n.is_simulated,
        read_at=n.read_at,
        created_at=n.created_at,
    )


@router.get("", response_model=NotificationList)
def list_notifications(
    unread: bool = False,
    limit: int = 50,
    ctx: WorkspaceContext = Depends(require_membership()),
    auth: AuthenticatedSession = Depends(current_auth),
    db: Session = Depends(get_db),
) -> NotificationList:
    items = service.list_notifications(db, ctx, auth.user.id, unread_only=unread, limit=limit)
    return NotificationList(
        items=[_out(n) for n in items], unread_count=service.unread_count(db, ctx, auth.user.id)
    )


@router.post("/read-all", status_code=204)
def read_all(
    ctx: WorkspaceContext = Depends(require_membership()),
    auth: AuthenticatedSession = Depends(current_auth),
    db: Session = Depends(get_db),
    clock: Clock = Depends(get_clock),
) -> Response:
    service.mark_all_read(db, clock, ctx, auth.user.id)
    return Response(status_code=204)


@router.post("/{notification_id}/read", response_model=NotificationOut)
def read_one(
    notification_id: uuid.UUID,
    ctx: WorkspaceContext = Depends(require_membership()),
    auth: AuthenticatedSession = Depends(current_auth),
    db: Session = Depends(get_db),
    clock: Clock = Depends(get_clock),
) -> NotificationOut:
    return _out(service.mark_read(db, clock, ctx, auth.user.id, notification_id))
