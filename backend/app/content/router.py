"""Content and media routes (api-design.md §2.7). Thin: validate, call the service, map.

Every route is workspace-scoped (INV-01): a foreign ID is simply not found.
"""

import uuid
from collections.abc import Iterator
from typing import BinaryIO

from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api.deps import get_app_settings, get_clock, require_membership
from app.content import media
from app.content.schemas import MediaAssetOut
from app.core.clock import Clock
from app.core.config import Settings
from app.core.context import WorkspaceContext
from app.core.db import get_db
from app.core.errors import AppError
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
