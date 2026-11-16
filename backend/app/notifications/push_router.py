"""Web Push subscription routes (api-design.md §2.8a, F-01 part 1).

Any member manages their own devices and their own per-category opt-in; nobody sees another
member's. Responses carry a device label, an id and timestamps only: never the endpoint URL or
the message keys. Nothing here sends a push (the owner channel does, from the job worker).
"""

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.api.deps import current_auth, get_app_settings, get_clock, require_membership
from app.core.clock import Clock
from app.core.config import Settings
from app.core.context import WorkspaceContext
from app.core.db import get_db
from app.identity.service import AuthenticatedSession
from app.notifications import push_preferences
from app.notifications import push_subscriptions as service
from app.notifications.models import PushSubscription

router = APIRouter(prefix="/workspaces/{workspace_id}/push-subscriptions", tags=["push"])


class PushConfigOut(BaseModel):
    enabled: bool  # false when VAPID is not configured: the app then hides push controls
    public_key: str | None  # the VAPID application server key (public by design)


class PushKeysIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    p256dh: str = Field(min_length=1, max_length=200)
    auth: str = Field(min_length=1, max_length=100)


class PushSubscribeIn(BaseModel):
    """The shape of the browser's ``PushSubscription.toJSON()``."""

    model_config = ConfigDict(extra="forbid")

    endpoint: str = Field(min_length=1, max_length=service.MAX_ENDPOINT_CHARS)
    expirationTime: float | None = None  # noqa: N815  # browsers send it; it is not stored
    keys: PushKeysIn
    label: str | None = Field(default=None, max_length=service.MAX_LABEL_CHARS)


class PushDeviceOut(BaseModel):
    id: uuid.UUID
    label: str
    created_at: datetime
    last_success_at: datetime | None


class PushDeviceList(BaseModel):
    items: list[PushDeviceOut]


class PushPreferencesOut(BaseModel):
    """Opt-in per category; ``false`` until the user switches it on."""

    approvals: bool
    questions: bool
    failures: bool


class PushPreferencesIn(BaseModel):
    """Only the categories sent are changed."""

    model_config = ConfigDict(extra="forbid")

    approvals: bool | None = None
    questions: bool | None = None
    failures: bool | None = None


def _out(row: PushSubscription) -> PushDeviceOut:
    return PushDeviceOut(
        id=row.id,
        label=row.device_label,
        created_at=row.created_at,
        last_success_at=row.last_success_at,
    )


@router.get("/config", response_model=PushConfigOut)
def push_config(
    _ctx: WorkspaceContext = Depends(require_membership()),
    settings: Settings = Depends(get_app_settings),
) -> PushConfigOut:
    """Whether push is available and the public key to subscribe with. Safe when unconfigured."""
    if not settings.web_push_enabled:
        return PushConfigOut(enabled=False, public_key=None)
    return PushConfigOut(enabled=True, public_key=settings.web_push_vapid_public_key.strip())


@router.get("/preferences", response_model=PushPreferencesOut)
def get_preferences(
    ctx: WorkspaceContext = Depends(require_membership()),
    auth: AuthenticatedSession = Depends(current_auth),
    db: Session = Depends(get_db),
) -> PushPreferencesOut:
    """The signed-in user's own opt-in per category."""
    return PushPreferencesOut(
        **push_preferences.get_preferences(db, ctx.workspace_id, auth.user.id)
    )


@router.put("/preferences", response_model=PushPreferencesOut)
def put_preferences(
    body: PushPreferencesIn,
    ctx: WorkspaceContext = Depends(require_membership()),
    auth: AuthenticatedSession = Depends(current_auth),
    db: Session = Depends(get_db),
    clock: Clock = Depends(get_clock),
) -> PushPreferencesOut:
    """Change the signed-in user's own opt-in (only the categories sent)."""
    changes = {k: v for k, v in body.model_dump().items() if v is not None}
    return PushPreferencesOut(
        **push_preferences.set_preferences(db, clock, ctx, auth.user.id, changes)
    )


@router.get("", response_model=PushDeviceList)
def list_devices(
    ctx: WorkspaceContext = Depends(require_membership()),
    auth: AuthenticatedSession = Depends(current_auth),
    db: Session = Depends(get_db),
) -> PushDeviceList:
    """The signed-in user's own devices."""
    return PushDeviceList(items=[_out(r) for r in service.list_devices(db, ctx, auth.user.id)])


@router.post("", response_model=PushDeviceOut, status_code=201)
def subscribe(
    body: PushSubscribeIn,
    request: Request,
    response: Response,
    ctx: WorkspaceContext = Depends(require_membership()),
    auth: AuthenticatedSession = Depends(current_auth),
    db: Session = Depends(get_db),
    clock: Clock = Depends(get_clock),
    settings: Settings = Depends(get_app_settings),
) -> PushDeviceOut:
    """Register this device (201), or refresh it when the same endpoint is already registered
    for this user (200). 409 ``WEB_PUSH_NOT_CONFIGURED`` when the server has no VAPID keys."""
    row, created = service.subscribe(
        db,
        clock,
        settings,
        ctx,
        auth.user.id,
        endpoint=body.endpoint,
        p256dh=body.keys.p256dh,
        auth=body.keys.auth,
        user_agent=request.headers.get("user-agent"),
        label=body.label,
    )
    if not created:
        response.status_code = 200
    return _out(row)


@router.delete("/{subscription_id}", status_code=204)
def unsubscribe(
    subscription_id: uuid.UUID,
    ctx: WorkspaceContext = Depends(require_membership()),
    auth: AuthenticatedSession = Depends(current_auth),
    db: Session = Depends(get_db),
    clock: Clock = Depends(get_clock),
) -> Response:
    service.unsubscribe(db, clock, ctx, auth.user.id, subscription_id)
    return Response(status_code=204)
