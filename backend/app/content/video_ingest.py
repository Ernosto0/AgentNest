"""Private, streamed video ingest. Probe/storage I/O always happens between transactions."""

import hashlib
import io
import tempfile
import uuid
from dataclasses import asdict
from pathlib import Path
from typing import BinaryIO, NoReturn

from sqlalchemy import func, select
from sqlalchemy.orm import Session, aliased

from app.audit import service as audit
from app.content.media import MediaRejected, process_image, sanitize_filename
from app.content.models import MediaAsset
from app.content.video import Issue, VideoLimits, validate_video
from app.core.clock import Clock
from app.core.config import Settings
from app.core.context import WorkspaceContext
from app.core.errors import AppError
from app.core.ids import new_id
from app.identity.models import Workspace
from app.integrations.storage.base import MediaStorage, build_key
from app.integrations.video.base import VideoProbeFailed, VideoProber, VideoProbeUnavailable

COPY_CHUNK_BYTES = 1024 * 1024
MULTIPART_ALLOWANCE_BYTES = 64 * 1024
THUMBNAIL_MAX_WIDTH = 1080
THUMBNAIL_MAX_HEIGHT = 1920
THUMBNAIL_MAX_BYTES = 8_000_000


def stored_video_bytes(db: Session, ctx: WorkspaceContext) -> int:
    thumbnail = aliased(MediaAsset)
    return int(
        db.scalar(
            select(
                func.coalesce(
                    func.sum(MediaAsset.byte_size + func.coalesce(thumbnail.byte_size, 0)), 0
                )
            )
            .outerjoin(
                thumbnail,
                (thumbnail.workspace_id == MediaAsset.workspace_id)
                & (thumbnail.id == MediaAsset.thumbnail_media_asset_id)
                & (thumbnail.status != "deleted"),
            )
            .where(
                MediaAsset.workspace_id == ctx.workspace_id,
                MediaAsset.kind == "video",
                MediaAsset.status != "deleted",
            )
        )
        or 0
    )


def check_quota(db: Session, settings: Settings, ctx: WorkspaceContext, size: int) -> None:
    if stored_video_bytes(db, ctx) + size > settings.media_video_workspace_quota_bytes:
        raise AppError(
            "VIDEO_STORAGE_QUOTA_EXCEEDED", limit=settings.media_video_workspace_quota_bytes
        )


def reject(
    db: Session,
    clock: Clock,
    ctx: WorkspaceContext,
    filename: str | None,
    size: int,
    issues: tuple[Issue, ...],
    *,
    too_large: bool = False,
) -> NoReturn:
    reasons = [asdict(issue) for issue in issues]
    audit.record(
        db,
        ctx,
        "media.rejected",
        "media_asset",
        None,
        {
            "reason": issues[0].code,
            "reasons": reasons,
            "original_filename": filename,
            "byte_size": size,
        },
        clock=clock,
    )
    db.commit()
    if too_large:
        raise AppError("VIDEO_TOO_LARGE", limit_bytes=issues[0].limit)
    raise AppError("VIDEO_INVALID", reason=issues[0].code, reasons=reasons)


def ingest_video(
    db: Session,
    clock: Clock,
    settings: Settings,
    storage: MediaStorage,
    ctx: WorkspaceContext,
    file: BinaryIO,
    filename: str | None,
    prober: VideoProber,
) -> MediaAsset:
    db.commit()
    name = sanitize_filename(filename)
    size = 0
    digest = hashlib.sha256()
    with tempfile.TemporaryDirectory(
        prefix="agentnest-video-", dir=settings.media_scratch_dir or None
    ) as directory:
        path = Path(directory) / "upload"
        # The enclosing directory is private, and the input itself is explicitly 0600.
        with path.open("xb") as output:
            path.chmod(0o600)
            while chunk := file.read(
                min(COPY_CHUNK_BYTES, settings.media_max_video_bytes - size + 1)
            ):
                size += len(chunk)
                if size > settings.media_max_video_bytes:
                    reject(
                        db,
                        clock,
                        ctx,
                        name,
                        size,
                        (Issue("TOO_LARGE", settings.media_max_video_bytes, size),),
                        too_large=True,
                    )
                digest.update(chunk)
                output.write(chunk)
        if size == 0:
            reject(db, clock, ctx, name, size, (Issue("EMPTY_FILE"),))
        try:
            # The real adapter independently scans ISO boxes before invoking any binary.
            # Fake fixtures deliberately have a different, test-only header.
            facts = prober.probe(path)
            verdict = validate_video(facts, byte_size=size, limits=VideoLimits())
            if verdict.issues:
                reject(db, clock, ctx, name, size, verdict.issues)
            thumbnail = process_image(
                prober.extract_frame(
                    path,
                    min(1000, facts.duration_ms // 2),
                    min(
                        THUMBNAIL_MAX_WIDTH,
                        max(1, round(THUMBNAIL_MAX_HEIGHT * facts.width / facts.height)),
                    ),
                )
            )
            if len(thumbnail.data) > THUMBNAIL_MAX_BYTES:
                raise VideoProbeFailed("CORRUPT_VIDEO")
        except VideoProbeUnavailable as exc:
            raise AppError("VIDEO_PROBE_UNAVAILABLE") from exc
        except VideoProbeFailed as exc:
            reject(db, clock, ctx, name, size, (Issue(exc.reason),))
        except MediaRejected:
            reject(db, clock, ctx, name, size, (Issue("CORRUPT_VIDEO"),))

        now = clock.now()
        video_id, thumbnail_id = new_id(), new_id()
        video_key = build_key(ctx.workspace_id, video_id, now, facts.container)
        thumbnail_key = build_key(ctx.workspace_id, thumbnail_id, now, "jpg")
        user_id = uuid.UUID(ctx.actor.id) if ctx.actor.type == "user" and ctx.actor.id else None
        common = {
            "workspace_id": ctx.workspace_id,
            "storage_backend": storage.backend,
            "status": "ready",
            "created_by_user_id": user_id,
            "created_at": now,
            "updated_at": now,
        }
        try:
            with path.open("rb") as source:
                storage.put(
                    video_key,
                    source,
                    "video/quicktime" if facts.container == "mov" else "video/mp4",
                )
            storage.put(thumbnail_key, io.BytesIO(thumbnail.data), "image/jpeg")
            # Serialize concurrent quota decisions in this workspace, after storage I/O.
            db.execute(
                select(Workspace.id).where(Workspace.id == ctx.workspace_id).with_for_update()
            )
            check_quota(db, settings, ctx, size + len(thumbnail.data))
            thumb = MediaAsset(
                id=thumbnail_id,
                kind="video_thumbnail",
                storage_key=thumbnail_key,
                mime_type="image/jpeg",
                byte_size=len(thumbnail.data),
                width=thumbnail.width,
                height=thumbnail.height,
                sha256=thumbnail.sha256,
                **common,
            )
            db.add(thumb)
            db.flush()
            asset = MediaAsset(
                id=video_id,
                kind="video",
                storage_key=video_key,
                original_filename=name,
                mime_type="video/quicktime" if facts.container == "mov" else "video/mp4",
                byte_size=size,
                width=facts.width,
                height=facts.height,
                sha256=digest.hexdigest(),
                duration_ms=facts.duration_ms,
                video_codec=facts.video_codec,
                audio_codec=facts.audio_codecs[0] if facts.audio_codecs else None,
                frame_rate=facts.frame_rate,
                bitrate_bps=facts.video_bitrate_bps,
                container=facts.container,
                video_warnings=list(verdict.warnings),
                thumbnail_media_asset_id=thumbnail_id,
                **common,
            )
            db.add(asset)
            db.flush()
            audit.record(
                db,
                ctx,
                "media.uploaded",
                "media_asset",
                asset.id,
                {
                    "kind": "video",
                    "duration_ms": asset.duration_ms,
                    "width": asset.width,
                    "height": asset.height,
                    "video_codec": asset.video_codec,
                    "container": asset.container,
                    "byte_size": size,
                    "sha256": asset.sha256,
                    "warnings": list(verdict.warnings),
                },
                clock=clock,
            )
            db.commit()
        except BaseException:
            db.rollback()
            # Attempt both deletes even when one cleanup fails; missing keys are idempotent.
            try:
                storage.delete(video_key)
            finally:
                storage.delete(thumbnail_key)
            raise
        return asset
