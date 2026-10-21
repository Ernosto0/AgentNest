"""Image upload: validate, normalise and store (ADR-015, plan.md G12).

The upload is untrusted input (INV-03). The order is fixed and every step is deterministic:

1. read at most ``limit + 1`` bytes (more than the limit: 413 ``MEDIA_TOO_LARGE``);
2. ``Image.open`` + ``verify`` (the format is sniffed from the bytes, never from the file name
   or the client's content type), then reopen, because ``verify`` leaves the image unusable;
3. pixel cap (a decompression-bomb warning is an error);
4. ``exif_transpose``, then convert to sRGB;
5. **always** re-encode as a baseline JPEG at quality 90 without EXIF (the simplest guaranteed
   removal of GPS and other metadata);
6. the sha256 is taken over the **output**, which is what is published.

A rejected upload stores no row: 422 ``MEDIA_INVALID`` plus a ``media.rejected`` audit entry.
The storage key is built from IDs only. Unused assets are removed later by the ``media_cleanup``
job (``content/media_cleanup.py``).
"""

import hashlib
import io
import re
import uuid
import warnings
from dataclasses import dataclass
from typing import BinaryIO

from PIL import Image, ImageCms, ImageOps, UnidentifiedImageError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit import service as audit
from app.content.models import MediaAsset
from app.core.clock import Clock
from app.core.config import Settings
from app.core.context import WorkspaceContext
from app.core.errors import AppError
from app.core.ids import new_id
from app.integrations.storage.base import MediaStorage, build_key

ACCEPTED_FORMATS = ("JPEG", "PNG")
# 6000 x 6000. Decoded RGB needs ~3 bytes per pixel, so this bounds the memory of one upload.
MAX_IMAGE_PIXELS = 36_000_000
JPEG_QUALITY = 90
OUTPUT_MIME = "image/jpeg"
OUTPUT_EXT = "jpg"
FILENAME_MAX = 120

# Why an upload was rejected (``media.rejected`` audit entries, ``MEDIA_INVALID`` params).
REASON_EMPTY = "EMPTY_FILE"
REASON_NOT_AN_IMAGE = "NOT_AN_IMAGE"
REASON_CORRUPT = "CORRUPT_IMAGE"
REASON_TOO_MANY_PIXELS = "TOO_MANY_PIXELS"
REASON_TOO_LARGE = "TOO_LARGE"

_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")


class MediaRejected(Exception):
    """The bytes are not an acceptable image. ``reason`` is one of the ``REASON_*`` codes."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class ProcessedImage:
    data: bytes
    width: int
    height: int
    sha256: str


def sanitize_filename(filename: str | None) -> str | None:
    """A display-only name: the last path segment, no control characters, bounded length."""
    if not filename:
        return None
    name = _CONTROL_CHARS.sub("", filename.replace("\\", "/").rsplit("/", 1)[-1]).strip()
    return name[:FILENAME_MAX] or None


def _open(raw: bytes) -> Image.Image:
    return Image.open(io.BytesIO(raw), formats=list(ACCEPTED_FORMATS))


def _check_pixels(image: Image.Image) -> None:
    width, height = image.size
    if width <= 0 or height <= 0 or width * height > MAX_IMAGE_PIXELS:
        raise MediaRejected(REASON_TOO_MANY_PIXELS)


def _is_srgb(profile: ImageCms.ImageCmsProfile) -> bool:
    return "srgb" in (ImageCms.getProfileDescription(profile) or "").lower()


def _to_srgb(image: Image.Image) -> Image.Image:
    """An RGB image in the sRGB colour space (transparency is flattened onto white)."""
    has_alpha = image.mode in ("RGBA", "LA", "PA") or (
        image.mode == "P" and "transparency" in image.info
    )
    if has_alpha:
        rgba = image.convert("RGBA")
        flat = Image.new("RGB", rgba.size, (255, 255, 255))
        flat.paste(rgba, mask=rgba.getchannel("A"))
        return flat
    icc = image.info.get("icc_profile")
    if icc and image.mode in ("RGB", "CMYK"):
        try:
            source = ImageCms.ImageCmsProfile(io.BytesIO(icc))
            if image.mode == "CMYK" or not _is_srgb(source):
                target = ImageCms.createProfile("sRGB")
                converted = ImageCms.profileToProfile(image, source, target, outputMode="RGB")
                if converted is not None:
                    return converted
        except (ImageCms.PyCMSError, OSError, ValueError):
            pass  # an unusable profile: fall back to the plain conversion below
    return image.convert("RGB")


def process_image(raw: bytes) -> ProcessedImage:
    """Validate ``raw`` and return it as a baseline sRGB JPEG without metadata."""
    if not raw:
        raise MediaRejected(REASON_EMPTY)
    try:
        with warnings.catch_warnings():
            # A decompression-bomb warning is an error, not a log line.
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            probe = _open(raw)
            _check_pixels(probe)
            probe.verify()
            image = _open(raw)  # verify() leaves the first object unusable
            _check_pixels(image)
            image.load()
            image = ImageOps.exif_transpose(image)
            image = _to_srgb(image)
    except MediaRejected:
        raise
    except (Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise MediaRejected(REASON_TOO_MANY_PIXELS) from exc
    except UnidentifiedImageError as exc:
        raise MediaRejected(REASON_NOT_AN_IMAGE) from exc
    except (OSError, SyntaxError, ValueError, EOFError) as exc:
        raise MediaRejected(REASON_CORRUPT) from exc
    image.info.clear()  # nothing from the source (EXIF, ICC, comments) may reach the output
    out = io.BytesIO()
    image.save(out, "JPEG", quality=JPEG_QUALITY, optimize=False, progressive=False)
    data = out.getvalue()
    width, height = image.size
    return ProcessedImage(data, width, height, hashlib.sha256(data).hexdigest())


def _reject(
    db: Session,
    clock: Clock,
    ctx: WorkspaceContext,
    *,
    reason: str,
    filename: str | None,
    byte_size: int | None,
) -> None:
    audit.record(
        db,
        ctx,
        "media.rejected",
        "media_asset",
        None,
        {"reason": reason, "original_filename": filename, "byte_size": byte_size},
        clock=clock,
    )
    db.commit()


def ingest(
    db: Session,
    clock: Clock,
    settings: Settings,
    storage: MediaStorage,
    ctx: WorkspaceContext,
    file: BinaryIO,
    filename: str | None,
    content_type: str | None,  # the client's claim: accepted, never trusted (INV-03)
) -> MediaAsset:
    """Validate, convert and store an upload and return its ``ready`` asset.

    Raises ``MEDIA_TOO_LARGE`` (413) or ``MEDIA_INVALID`` (422); both leave no asset and no
    stored object behind, only the audit entry.
    """
    limit = settings.media_max_image_bytes
    name = sanitize_filename(filename)
    raw = file.read(limit + 1)
    if len(raw) > limit:
        _reject(db, clock, ctx, reason=REASON_TOO_LARGE, filename=name, byte_size=None)
        raise AppError("MEDIA_TOO_LARGE", limit_bytes=limit)
    try:
        processed = process_image(raw)
    except MediaRejected as rejected:
        _reject(db, clock, ctx, reason=rejected.reason, filename=name, byte_size=len(raw))
        raise AppError("MEDIA_INVALID", reason=rejected.reason) from rejected

    now = clock.now()
    media_id = new_id()
    key = build_key(ctx.workspace_id, media_id, now, OUTPUT_EXT)
    user_id = uuid.UUID(ctx.actor.id) if ctx.actor.type == "user" and ctx.actor.id else None
    # The object is written before the row, so a committed asset always has its bytes. A
    # failure after this point removes the object again.
    storage.put(key, io.BytesIO(processed.data), OUTPUT_MIME)
    try:
        asset = MediaAsset(
            id=media_id,
            workspace_id=ctx.workspace_id,
            storage_backend=storage.backend,
            storage_key=key,
            original_filename=name,
            mime_type=OUTPUT_MIME,
            byte_size=len(processed.data),
            width=processed.width,
            height=processed.height,
            sha256=processed.sha256,
            status="ready",
            created_by_user_id=user_id,
            created_at=now,
            updated_at=now,
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
                "width": asset.width,
                "height": asset.height,
                "byte_size": asset.byte_size,
                "sha256": asset.sha256,
            },
            clock=clock,
        )
        db.commit()
    except BaseException:
        db.rollback()
        storage.delete(key)
        raise
    return asset


def get_asset(db: Session, ctx: WorkspaceContext, media_id: uuid.UUID) -> MediaAsset:
    """A ready asset of this workspace; anything else (foreign, deleted) is a 404 (INV-01)."""
    asset = db.scalar(
        select(MediaAsset).where(
            MediaAsset.workspace_id == ctx.workspace_id,
            MediaAsset.id == media_id,
            MediaAsset.status == "ready",
        )
    )
    if asset is None:
        raise AppError("NOT_FOUND")
    return asset
