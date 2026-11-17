"""Effective workspace palette and audited, permission checked updates."""

import uuid
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit import service as audit
from app.content import media
from app.content.models import WorkspaceBrandSettings
from app.core.clock import Clock
from app.core.context import WorkspaceContext
from app.core.errors import AppError
from app.identity.models import Workspace
from app.identity.permissions import has_permission

DEFAULT_PRIMARY = "#f4f4f5"
DEFAULT_ACCENT = "#3f3f46"
Color = Annotated[str, Field(pattern=r"^#[0-9a-fA-F]{6}$", strict=True)]


class BrandInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    primary_color: Color
    accent_color: Color
    logo_media_asset_id: Annotated[uuid.UUID, Field(strict=False)] | None

    @field_validator("primary_color", "accent_color")
    @classmethod
    def lowercase(cls, value: str) -> str:
        return value.lower()


class BrandOut(BrandInput):
    is_default: bool
    logo_width: int | None = None
    logo_height: int | None = None


def get_brand(db: Session, ctx: WorkspaceContext) -> BrandOut:
    row = db.scalar(
        select(WorkspaceBrandSettings).where(
            WorkspaceBrandSettings.workspace_id == ctx.workspace_id
        )
    )
    if row is None:
        return BrandOut(
            primary_color=DEFAULT_PRIMARY,
            accent_color=DEFAULT_ACCENT,
            logo_media_asset_id=None,
            is_default=True,
        )
    logo = media.get_asset(db, ctx, row.logo_media_asset_id) if row.logo_media_asset_id else None
    return BrandOut(
        primary_color=row.primary_color,
        accent_color=row.accent_color,
        logo_media_asset_id=row.logo_media_asset_id,
        is_default=False,
        logo_width=logo.width if logo else None,
        logo_height=logo.height if logo else None,
    )


def set_brand(db: Session, clock: Clock, ctx: WorkspaceContext, body: BrandInput) -> BrandOut:
    if not has_permission(ctx.role, "brand.manage"):
        raise AppError("FORBIDDEN", permission="brand.manage")
    # Serialize first creation too: locking an absent brand row alone cannot do that.
    workspace = db.scalar(
        select(Workspace.id).where(Workspace.id == ctx.workspace_id).with_for_update()
    )
    if workspace is None:
        raise AppError("NOT_FOUND")
    if body.logo_media_asset_id:
        media.get_asset(db, ctx, body.logo_media_asset_id)
    row = db.scalar(
        select(WorkspaceBrandSettings)
        .where(WorkspaceBrandSettings.workspace_id == ctx.workspace_id)
        .with_for_update()
    )
    if row is None:
        row = WorkspaceBrandSettings(workspace_id=ctx.workspace_id, created_at=clock.now())
        db.add(row)
    row.primary_color = body.primary_color
    row.accent_color = body.accent_color
    row.logo_media_asset_id = body.logo_media_asset_id
    row.updated_at = clock.now()
    db.flush()
    audit.record(
        db,
        ctx,
        "brand.updated",
        "workspace_brand_settings",
        row.id,
        body.model_dump(mode="json"),
        clock=clock,
    )
    db.commit()
    return get_brand(db, ctx)
