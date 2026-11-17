"""Workspace brand and template image HTTP contracts."""

import uuid
from typing import Any

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.api.deps import get_app_settings, get_clock, require_membership
from app.content import brand
from app.content.router import get_storage
from app.content.schemas import ContentItemOut, MediaAssetOut, TemplateImageRerenderIn
from app.content.templates import service
from app.content.templates.rerender import rerender
from app.content.templates.spec import RenderRecord, TemplateInput, catalog
from app.content.views import item_out
from app.core.clock import Clock
from app.core.config import Settings
from app.core.context import WorkspaceContext
from app.core.db import get_db
from app.integrations.storage.base import MediaStorage

router = APIRouter(prefix="/workspaces/{workspace_id}", tags=["content"])


class TemplateImageOut(MediaAssetOut):
    render_record: RenderRecord


@router.get("/brand", response_model=brand.BrandOut)
def get_brand(
    ctx: WorkspaceContext = Depends(require_membership("settings.view")),
    db: Session = Depends(get_db),
) -> brand.BrandOut:
    return brand.get_brand(db, ctx)


@router.put("/brand", response_model=brand.BrandOut)
def put_brand(
    body: brand.BrandInput,
    ctx: WorkspaceContext = Depends(require_membership("brand.manage")),
    db: Session = Depends(get_db),
    clock: Clock = Depends(get_clock),
) -> brand.BrandOut:
    return brand.set_brand(db, clock, ctx, body)


@router.get("/content/templates")
def templates(
    ctx: WorkspaceContext = Depends(require_membership("content.edit")),
) -> list[dict[str, Any]]:
    return catalog()


@router.post(
    "/content/template-images/preview",
    response_class=Response,
    responses={200: {"content": {"image/jpeg": {}}}},
)
def preview(
    body: TemplateInput,
    ctx: WorkspaceContext = Depends(require_membership("content.edit")),
    db: Session = Depends(get_db),
    clock: Clock = Depends(get_clock),
    settings: Settings = Depends(get_app_settings),
    storage: MediaStorage = Depends(get_storage),
) -> Response:
    return Response(
        service.preview(db, clock, settings, storage, ctx, body), media_type="image/jpeg"
    )


@router.post("/content/template-images", response_model=TemplateImageOut, status_code=201)
def create(
    body: TemplateInput,
    ctx: WorkspaceContext = Depends(require_membership("content.edit")),
    db: Session = Depends(get_db),
    clock: Clock = Depends(get_clock),
    settings: Settings = Depends(get_app_settings),
    storage: MediaStorage = Depends(get_storage),
) -> TemplateImageOut:
    asset = service.create(db, clock, settings, storage, ctx, body)
    return TemplateImageOut.model_validate(asset)


@router.post("/content-items/{content_id}/template-image/rerender", response_model=ContentItemOut)
def rerender_image(
    content_id: uuid.UUID,
    body: TemplateImageRerenderIn,
    ctx: WorkspaceContext = Depends(require_membership("content.edit")),
    db: Session = Depends(get_db),
    clock: Clock = Depends(get_clock),
    settings: Settings = Depends(get_app_settings),
    storage: MediaStorage = Depends(get_storage),
) -> ContentItemOut:
    return item_out(
        db, ctx, rerender(db, clock, settings, storage, ctx, content_id, body.expected_version)
    )
