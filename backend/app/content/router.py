"""Content and media routes (api-design.md §2.7). Thin: validate, call the service, map.

Every route is workspace-scoped (INV-01): a foreign ID is simply not found.
"""

import uuid
from collections.abc import Iterator
from typing import BinaryIO

from fastapi import APIRouter, Depends, File, Query, Response, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api.deps import get_app_settings, get_clock, require_membership
from app.content import generation, media, service
from app.content.schemas import (
    ContentCreate,
    ContentGenerate,
    ContentItemOut,
    ContentPatch,
    ContentStatus,
    ContentTab,
    ContentValidationOut,
    MediaAssetOut,
    ReapproveIn,
    ScheduleIn,
    SubmitIn,
    ValidateIn,
)
from app.content.service import ScheduleRequest
from app.content.views import check_out, item_out
from app.core.clock import Clock
from app.core.config import Settings
from app.core.context import WorkspaceContext
from app.core.db import get_db
from app.core.errors import AppError
from app.core.pagination import Page
from app.integrations.storage.base import MediaStorage, StorageObjectNotFound
from app.integrations.storage.registry import get_media_storage

router = APIRouter(prefix="/workspaces/{workspace_id}", tags=["content"])

CHUNK_BYTES = 64 * 1024


def get_storage(
    settings: Settings = Depends(get_app_settings), clock: Clock = Depends(get_clock)
) -> MediaStorage:
    return get_media_storage(settings, clock)


def _chunks(stream: BinaryIO) -> Iterator[bytes]:
    try:
        while chunk := stream.read(CHUNK_BYTES):
            yield chunk
    finally:
        stream.close()


@router.post("/media", response_model=MediaAssetOut, status_code=201)
def upload_media(
    file: UploadFile = File(...),
    ctx: WorkspaceContext = Depends(require_membership("content.edit")),
    db: Session = Depends(get_db),
    clock: Clock = Depends(get_clock),
    settings: Settings = Depends(get_app_settings),
    storage: MediaStorage = Depends(get_storage),
) -> MediaAssetOut:
    asset = media.ingest(
        db, clock, settings, storage, ctx, file.file, file.filename, file.content_type
    )
    return MediaAssetOut.model_validate(asset)


@router.get("/media/{media_id}/content")
def media_content(
    media_id: uuid.UUID,
    ctx: WorkspaceContext = Depends(require_membership()),
    db: Session = Depends(get_db),
    storage: MediaStorage = Depends(get_storage),
) -> StreamingResponse:
    """The stored JPEG, for authenticated members only. Never a bucket URL (ADR-015)."""
    asset = media.get_asset(db, ctx, media_id)
    try:
        stream = storage.open(asset.storage_key)
    except StorageObjectNotFound as exc:
        raise AppError("NOT_FOUND") from exc
    return StreamingResponse(
        _chunks(stream),
        media_type=asset.mime_type,
        headers={
            "Content-Length": str(asset.byte_size),
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, max-age=3600",
            "Content-Disposition": "inline",
            "ETag": f'"{asset.sha256}"',
        },
    )


# --- content items (api-design.md section 2.7) -------------------------------------------------


@router.get("/content-items", response_model=Page[ContentItemOut])
def list_content_items(
    tab: ContentTab | None = None,
    status: ContentStatus | None = None,
    limit: int = Query(50, ge=1, le=service.MAX_LIMIT),
    ctx: WorkspaceContext = Depends(require_membership()),
    db: Session = Depends(get_db),
) -> Page[ContentItemOut]:
    items = service.list_items(db, ctx, tab=tab, status=status, limit=limit)
    return Page(items=[item_out(db, ctx, item) for item in items])


@router.post("/content-items", response_model=ContentItemOut, status_code=201)
def create_content_item(
    body: ContentCreate,
    response: Response,
    ctx: WorkspaceContext = Depends(require_membership("content.edit")),
    db: Session = Depends(get_db),
    clock: Clock = Depends(get_clock),
) -> ContentItemOut:
    item, created = service.create_draft(
        db,
        clock,
        ctx,
        content_type=body.content_type,
        title=body.title,
        caption=body.caption,
        overlay_text_suggestions=body.overlay_text_suggestions,
        media_asset_id=body.media_asset_id,
        client_request_id=body.client_request_id,
    )
    if not created:
        response.status_code = 200  # the same request again: the item it made
    return item_out(db, ctx, item)


@router.post("/content-items/generate", response_model=ContentItemOut, status_code=202)
def generate_content_item(
    body: ContentGenerate,
    response: Response,
    ctx: WorkspaceContext = Depends(require_membership("content.edit")),
    db: Session = Depends(get_db),
    clock: Clock = Depends(get_clock),
) -> ContentItemOut:
    """Ask the AI for a draft: the draft exists at once (202) and fills in when the job has
    run. The same ``client_request_id`` again returns the first draft (200)."""
    item, created = generation.request(
        db,
        clock,
        ctx,
        content_type=body.content_type,
        objective=body.objective,
        notes=body.notes,
        client_request_id=body.client_request_id,
    )
    if not created:
        response.status_code = 200
    return item_out(db, ctx, item)


@router.get("/content-items/{content_id}", response_model=ContentItemOut)
def get_content_item(
    content_id: uuid.UUID,
    ctx: WorkspaceContext = Depends(require_membership()),
    db: Session = Depends(get_db),
) -> ContentItemOut:
    return item_out(db, ctx, service.get_item(db, ctx, content_id))


@router.patch("/content-items/{content_id}", response_model=ContentItemOut)
def patch_content_item(
    content_id: uuid.UUID,
    body: ContentPatch,
    ctx: WorkspaceContext = Depends(require_membership("content.edit")),
    db: Session = Depends(get_db),
    clock: Clock = Depends(get_clock),
) -> ContentItemOut:
    sent = body.model_fields_set - {"expected_version"}
    if ("title" in sent and body.title is None) or (
        "overlay_text_suggestions" in sent and body.overlay_text_suggestions is None
    ):
        field = "title" if "title" in sent and body.title is None else "overlay_text_suggestions"
        raise AppError(
            "VALIDATION_FAILED", errors=[{"field": field, "code": "required", "params": {}}]
        )
    fields = {name: getattr(body, name) for name in sent}
    item = service.update(
        db, clock, ctx, content_id, expected_version=body.expected_version, fields=fields
    )
    return item_out(db, ctx, item)


def _schedule(schedule: ScheduleIn) -> ScheduleRequest:
    if schedule == "now":
        return ScheduleRequest(publish_now=True)
    return ScheduleRequest(local_date=schedule.local_date, local_time=schedule.local_time)


@router.post("/content-items/{content_id}/validate", response_model=ContentValidationOut)
def validate_content_item(
    content_id: uuid.UUID,
    body: ValidateIn | None = None,
    ctx: WorkspaceContext = Depends(require_membership("content.edit")),
    db: Session = Depends(get_db),
    clock: Clock = Depends(get_clock),
    settings: Settings = Depends(get_app_settings),
) -> ContentValidationOut:
    """A dry run of the claim validation and every submit rule. Changes nothing."""
    body = body or ValidateIn()
    checked = service.validate(
        db,
        clock,
        settings,
        ctx,
        content_id,
        schedule=None if body.schedule is None else _schedule(body.schedule),
        self_approve=body.self_approve,
    )
    return check_out(checked, ctx.locale)


@router.post("/content-items/{content_id}/submit", response_model=ContentItemOut)
def submit_content_item(
    content_id: uuid.UUID,
    body: SubmitIn,
    ctx: WorkspaceContext = Depends(require_membership("content.edit")),
    db: Session = Depends(get_db),
    clock: Clock = Depends(get_clock),
    settings: Settings = Depends(get_app_settings),
) -> ContentItemOut:
    item = service.submit(
        db,
        clock,
        settings,
        ctx,
        content_id,
        schedule=_schedule(body.schedule),
        self_approve=body.self_approve,
        expected_version=body.expected_version,
    )
    return item_out(db, ctx, item)


@router.post("/content-items/{content_id}/cancel", response_model=ContentItemOut)
def cancel_content_item(
    content_id: uuid.UUID,
    ctx: WorkspaceContext = Depends(require_membership()),  # the service decides (may_cancel)
    db: Session = Depends(get_db),
    clock: Clock = Depends(get_clock),
) -> ContentItemOut:
    return item_out(db, ctx, service.cancel(db, clock, ctx, content_id))


@router.post("/content-items/{content_id}/reapprove", response_model=ContentItemOut)
def reapprove_content_item(
    content_id: uuid.UUID,
    body: ReapproveIn,
    ctx: WorkspaceContext = Depends(require_membership("content.approve")),
    db: Session = Depends(get_db),
    clock: Clock = Depends(get_clock),
    settings: Settings = Depends(get_app_settings),
) -> ContentItemOut:
    item = service.reapprove(
        db,
        clock,
        settings,
        ctx,
        content_id,
        schedule=_schedule(body.schedule),
        expected_version=body.expected_version,
    )
    return item_out(db, ctx, item)
