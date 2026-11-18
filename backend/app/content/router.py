"""Content and media routes (api-design.md §2.7). Thin: validate, call the service, map.

Every route is workspace-scoped (INV-01): a foreign ID is simply not found.
"""

import uuid
from collections.abc import Iterator
from typing import BinaryIO

from fastapi import APIRouter, Depends, File, Query, Request, Response, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import UploadFile as StarletteUploadFile

from app.api.deps import get_app_settings, get_clock, require_membership
from app.content import generation, media, service, video_ingest
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
from app.content.templates import link
from app.content.video import Issue
from app.content.views import check_out, item_out
from app.core.clock import Clock
from app.core.config import Settings
from app.core.context import WorkspaceContext
from app.core.db import get_db
from app.core.errors import AppError
from app.core.pagination import Page
from app.integrations.storage.base import MediaStorage, StorageObjectNotFound
from app.integrations.storage.registry import get_media_storage
from app.integrations.video.registry import get_video_prober

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


def _video_precheck(
    db: Session, clock: Clock, settings: Settings, ctx: WorkspaceContext, declared: int
) -> None:
    """Header guards before any body byte is read (sync: runs in the thread pool)."""
    if declared > settings.media_max_video_bytes + video_ingest.MULTIPART_ALLOWANCE_BYTES:
        video_ingest.reject(
            db,
            clock,
            ctx,
            None,
            declared,
            (Issue("TOO_LARGE", settings.media_max_video_bytes, declared),),
            too_large=True,
        )
    video_ingest.check_quota(db, settings, ctx, declared)
    db.commit()


@router.post(
    "/media/video",
    response_model=MediaAssetOut,
    status_code=201,
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {
                "multipart/form-data": {
                    "schema": {
                        "type": "object",
                        "required": ["file"],
                        "properties": {"file": {"type": "string", "format": "binary"}},
                    }
                }
            },
        }
    },
)
async def upload_video(
    request: Request,
    ctx: WorkspaceContext = Depends(require_membership("content.edit")),
    db: Session = Depends(get_db),
    clock: Clock = Depends(get_clock),
    settings: Settings = Depends(get_app_settings),
    storage: MediaStorage = Depends(get_storage),
) -> MediaAssetOut:
    # No File dependency: guards and auth run BEFORE Starlette consumes the body. A request
    # without a usable Content-Length (chunked) is untrusted: Starlette would spool it to disk
    # before our byte counter runs, so it is refused as too large (browsers always send one).
    try:
        declared = max(0, int(request.headers.get("content-length", "")))
    except ValueError:
        declared = settings.media_max_video_bytes + video_ingest.MULTIPART_ALLOWANCE_BYTES + 1
    await run_in_threadpool(_video_precheck, db, clock, settings, ctx, declared)
    async with request.form(max_files=1, max_fields=0) as form:
        file = form.get("file")
        if not isinstance(file, StarletteUploadFile):
            raise AppError(
                "VALIDATION_FAILED", errors=[{"field": "file", "code": "required", "params": {}}]
            )
        asset = await run_in_threadpool(
            video_ingest.ingest_video,
            db,
            clock,
            settings,
            storage,
            ctx,
            file.file,
            file.filename,
            get_video_prober(settings),
        )
    return MediaAssetOut.model_validate(asset)


@router.get("/media/{media_id}", response_model=MediaAssetOut)
def media_metadata(
    media_id: uuid.UUID,
    ctx: WorkspaceContext = Depends(require_membership()),
    db: Session = Depends(get_db),
) -> MediaAssetOut:
    return MediaAssetOut.model_validate(media.get_asset(db, ctx, media_id, kind=None))


@router.get("/media/{media_id}/content", response_model=None)
def media_content(
    media_id: uuid.UUID,
    request: Request,
    ctx: WorkspaceContext = Depends(require_membership()),
    db: Session = Depends(get_db),
    storage: MediaStorage = Depends(get_storage),
) -> Response:
    """Stored media for authenticated members only. Never a bucket URL (ADR-015)."""
    asset = media.get_asset(db, ctx, media_id, kind=None)
    key, mime_type, byte_size, sha256 = (
        asset.storage_key,
        asset.mime_type,
        asset.byte_size,
        asset.sha256,
    )
    db.commit()  # no transaction while storage is opened or streamed
    etag = f'"{sha256}"'
    base_headers = {
        "Accept-Ranges": "bytes",
        "X-Content-Type-Options": "nosniff",
        "Cache-Control": "private, max-age=3600",
        "Content-Disposition": "inline",
        "ETag": etag,
    }
    if_range = request.headers.get("if-range")
    parsed_range = (
        "full"
        if if_range is not None and if_range.strip() != etag
        else media.parse_byte_range(request.headers.get("range"), byte_size)
    )
    if parsed_range == "unsatisfiable":
        return Response(
            status_code=416,
            headers={**base_headers, "Content-Range": f"bytes */{byte_size}"},
        )
    try:
        if isinstance(parsed_range, tuple):
            start, end = parsed_range
            length = end - start + 1
            stream = storage.open_range(key, start, length)
            return StreamingResponse(
                _chunks(stream),
                status_code=206,
                media_type=mime_type,
                headers={
                    **base_headers,
                    "Content-Length": str(length),
                    "Content-Range": f"bytes {start}-{end}/{byte_size}",
                },
            )
        stream = storage.open(key)
    except StorageObjectNotFound as exc:
        raise AppError("NOT_FOUND") from exc
    return StreamingResponse(
        _chunks(stream),
        media_type=mime_type,
        headers={
            **base_headers,
            "Content-Length": str(byte_size),
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
    template_asset_ids = [
        aid
        for i in items
        if (aid := i.cover_media_asset_id if i.content_type == "reel" else i.media_asset_id)
        is not None
    ]
    states = link.states(db, ctx, link.records(db, ctx, template_asset_ids))
    return Page(items=[item_out(db, ctx, item, template_states=states) for item in items])


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
        media_asset_ids=body.media_asset_ids,
        cover_media_asset_id=body.cover_media_asset_id,
        thumb_offset_ms=body.thumb_offset_ms,
        share_to_feed=body.share_to_feed,
        fields_set=body.model_fields_set,
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
