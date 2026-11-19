"""Owner messaging channel routes (ADR-012, Phase 9 Session 02 / P9-01)."""

from __future__ import annotations

import uuid
from urllib.parse import quote

from fastapi import APIRouter, Body, Depends, Response
from sqlalchemy.orm import Session

from app.api.deps import get_app_settings, get_clock, require_membership
from app.core.clock import Clock
from app.core.config import Settings
from app.core.context import WorkspaceContext
from app.core.db import get_db
from app.core.errors import AppError
from app.identity.channels import ChannelLinkService
from app.identity.models import CHANNEL_TYPES
from app.identity.schemas import (
    ChannelAvailabilityOut,
    ChannelDeliveryStatusOut,
    ChannelLinkCodeOut,
    ChannelLinkCodeRequest,
    ChannelLinkOut,
    ChannelPreferencesIn,
    ChannelPreferencesOut,
)

router = APIRouter(prefix="/workspaces/{workspace_id}/channels", tags=["channels"])


@router.post("/link-code", response_model=ChannelLinkCodeOut)
def generate_channel_link_code(
    body: ChannelLinkCodeRequest = Body(default_factory=ChannelLinkCodeRequest),
    ctx: WorkspaceContext = Depends(require_membership("settings.view")),
    db: Session = Depends(get_db),
    clock: Clock = Depends(get_clock),
    settings: Settings = Depends(get_app_settings),
) -> ChannelLinkCodeOut:
    """Generate a one-time link code for owner channel linking."""
    if body.channel == "whatsapp" and not settings.whatsapp_configured:
        raise AppError("CONFLICT_STATE", reason="whatsapp_not_configured")
    code, expires_at = ChannelLinkService.generate_link_code(db, clock, ctx, channel=body.channel)
    if body.channel == "whatsapp":
        number = settings.whatsapp_display_phone_number
        return ChannelLinkCodeOut(
            channel="whatsapp",
            code=code,
            expires_at=expires_at,
            whatsapp_number=number,
            deep_link_url=f"https://wa.me/{number}?text={quote(code, safe='')}" if number else None,
        )
    bot_username = settings.telegram_bot_username
    deep_link_url = None
    if bot_username:
        clean_bot = bot_username.lstrip("@")
        deep_link_url = f"https://t.me/{clean_bot}?start={code}"

    return ChannelLinkCodeOut(
        code=code,
        expires_at=expires_at,
        bot_username=bot_username,
        deep_link_url=deep_link_url,
    )


@router.get("/availability", response_model=ChannelAvailabilityOut)
def get_channel_availability(
    ctx: WorkspaceContext = Depends(require_membership("settings.view")),
    settings: Settings = Depends(get_app_settings),
) -> ChannelAvailabilityOut:
    """Which optional owner channels this server has credentials for (no secrets, no numbers)."""
    return ChannelAvailabilityOut(
        whatsapp=settings.whatsapp_configured,
        telegram=settings.telegram_configured,
    )


@router.get("/preferences", response_model=ChannelPreferencesOut)
def get_channel_preferences(
    ctx: WorkspaceContext = Depends(require_membership("settings.view")),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
) -> ChannelPreferencesOut:
    """Get the current user's notification channel preferences and status in this workspace."""
    if ctx.actor.type != "user" or not ctx.actor.id:
        raise AppError("FORBIDDEN")
    user_id = uuid.UUID(ctx.actor.id)
    prefs = ChannelLinkService.get_channel_preferences(db, ctx.workspace_id, user_id)
    channels_status = {
        ch: ChannelDeliveryStatusOut(
            **ChannelLinkService.get_channel_delivery_status(
                db, settings, ctx.workspace_id, user_id, ch
            )
        )
        for ch in CHANNEL_TYPES
    }
    app_only = not any(prefs.values())
    return ChannelPreferencesOut(
        telegram=prefs.get("telegram", False),
        whatsapp=prefs.get("whatsapp", False),
        app_only=app_only,
        channels=channels_status,
    )


@router.put("/preferences", response_model=ChannelPreferencesOut)
def update_channel_preferences(
    body: ChannelPreferencesIn,
    ctx: WorkspaceContext = Depends(require_membership("settings.view")),
    db: Session = Depends(get_db),
    clock: Clock = Depends(get_clock),
    settings: Settings = Depends(get_app_settings),
) -> ChannelPreferencesOut:
    """Update notification channel preferences for the current user."""
    if ctx.actor.type != "user" or not ctx.actor.id:
        raise AppError("FORBIDDEN")
    user_id = uuid.UUID(ctx.actor.id)

    if body.app_only is True:
        if body.telegram is True or body.whatsapp is True:
            raise AppError("VALIDATION_FAILED", reason="app_only_conflict")
        changes = {"telegram": False, "whatsapp": False}
    else:
        changes = {}
        if body.telegram is not None:
            changes["telegram"] = body.telegram
        if body.whatsapp is not None:
            changes["whatsapp"] = body.whatsapp
        if body.app_only is False and not changes:
            raise AppError("VALIDATION_FAILED", reason="specify_channel_or_app_only")

    ChannelLinkService.set_channel_preferences(db, clock, ctx, user_id, changes)
    db.commit()

    prefs = ChannelLinkService.get_channel_preferences(db, ctx.workspace_id, user_id)
    channels_status = {
        ch: ChannelDeliveryStatusOut(
            **ChannelLinkService.get_channel_delivery_status(
                db, settings, ctx.workspace_id, user_id, ch
            )
        )
        for ch in CHANNEL_TYPES
    }
    app_only = not any(prefs.values())
    return ChannelPreferencesOut(
        telegram=prefs.get("telegram", False),
        whatsapp=prefs.get("whatsapp", False),
        app_only=app_only,
        channels=channels_status,
    )


@router.get("/links", response_model=list[ChannelLinkOut])
def list_channel_links(
    ctx: WorkspaceContext = Depends(require_membership("settings.view")),
    db: Session = Depends(get_db),
) -> list[ChannelLinkOut]:
    """List active channel links for the current user in this workspace."""
    links = ChannelLinkService.list_links_for_user(db, ctx)
    return [
        ChannelLinkOut(
            id=link.id,
            channel=link.channel,
            channel_username=link.channel_username,
            linked_at=link.linked_at,
            status=link.status,
        )
        for link in links
    ]


@router.delete("/links/{link_id}", status_code=204)
def unlink_channel(
    link_id: uuid.UUID,
    ctx: WorkspaceContext = Depends(require_membership("settings.view")),
    db: Session = Depends(get_db),
    clock: Clock = Depends(get_clock),
) -> Response:
    """Unlink an active channel link."""
    ChannelLinkService.unlink_by_user(db, clock, ctx, link_id)
    return Response(status_code=204)
