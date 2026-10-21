"""``media_cleanup``: delete the image files nobody needs any more (plan H18, ADR-015).

An asset is deleted when it is not ``deleted`` yet and either

- no content item references it and it is older than ``RETENTION_MEDIA_ORPHAN_DAYS`` (7), or
- content items reference it and **all** of them were published more than
  ``RETENTION_PUBLISHED_MEDIA_DAYS`` (90) ago.

An item in any other state (draft, scheduled, retrying, on hold, failed, cancelled, rejected, or
published more recently) keeps its image: the media of a scheduled item is never removed.

For each asset the file is removed through ``MediaStorage`` **between** transactions (no external
call inside a DB transaction), then the row is set to ``status = deleted`` (the row stays for its
foreign keys) if it is still eligible. A crash in between leaves a ``ready`` row whose file is
gone; the next run removes the (missing) file again, which is not an error, and marks the row.
An asset that was attached to a new item in that window is left ``ready``; the content detail
then shows the generic preview error instead of the deleted-image text (a window of
milliseconds, on an image that had been unused for a week).
"""

import uuid
from datetime import datetime, timedelta

from pydantic import BaseModel
from sqlalchemy import ColumnElement, and_, exists, or_, select, update
from sqlalchemy.orm import Session, sessionmaker

from app.content.models import ContentItem, MediaAsset
from app.core.clock import Clock
from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.integrations.storage.base import InvalidStorageKey, MediaStorage
from app.integrations.storage.registry import get_media_storage
from app.jobs.models import Job
from app.jobs.queue import enqueue
from app.jobs.registry import JobContext, job_handler
from app.jobs.scheduler import register_periodic

MEDIA_CLEANUP_HOUR_UTC = 2
MEDIA_CLEANUP_MINUTE_UTC = 30
PAGE = 200
_log = get_logger("app.content.media_cleanup")


class MediaCleanupPayload(BaseModel):
    pass


def eligible(settings: Settings, now: datetime) -> ColumnElement[bool]:
    """The SQL condition under which a stored asset is no longer needed."""
    references = (
        select(ContentItem.id)
        .where(
            ContentItem.workspace_id == MediaAsset.workspace_id,
            ContentItem.media_asset_id == MediaAsset.id,
        )
        .exists()
    )
    still_needed = (
        select(ContentItem.id)
        .where(
            ContentItem.workspace_id == MediaAsset.workspace_id,
            ContentItem.media_asset_id == MediaAsset.id,
            or_(
                ContentItem.status != "published",
                ContentItem.published_at.is_(None),
                ContentItem.published_at
                >= now - timedelta(days=settings.retention_published_media_days),
            ),
        )
        .exists()
    )
    orphan = and_(
        ~references,
        MediaAsset.created_at < now - timedelta(days=settings.retention_media_orphan_days),
    )
    only_old_published = and_(references, ~still_needed)
    return and_(MediaAsset.status.in_(("uploaded", "ready")), or_(orphan, only_old_published))


def run_media_cleanup(
    session_factory: sessionmaker[Session],
    storage: MediaStorage,
    settings: Settings,
    now: datetime,
) -> int:
    """Delete every eligible asset's file and mark its row; returns how many rows were marked."""
    condition = eligible(settings, now)
    deleted = 0
    last_id: uuid.UUID | None = None
    while True:
        with session_factory() as session:
            statement = (
                select(MediaAsset.id, MediaAsset.storage_backend, MediaAsset.storage_key)
                .where(condition)
                .order_by(MediaAsset.id)
                .limit(PAGE)
            )
            if last_id is not None:
                statement = statement.where(MediaAsset.id > last_id)
            page = session.execute(statement).all()
        if not page:
            return deleted
        last_id = page[-1].id
        for asset_id, backend, key in page:
            if backend != storage.backend:
                _log.warning("media_cleanup_skipped", asset_id=str(asset_id), reason="backend")
                continue
            try:
                storage.delete(key)  # no transaction is open here
            except (InvalidStorageKey, OSError):
                _log.exception("media_cleanup_delete_failed", asset_id=str(asset_id))
                continue
            with session_factory() as session:
                result = session.execute(
                    update(MediaAsset)
                    .where(MediaAsset.id == asset_id, condition)
                    .values(status="deleted", deleted_at=now)
                    .execution_options(synchronize_session=False)
                )
                session.commit()
            if result.rowcount == 1:  # type: ignore[attr-defined]
                deleted += 1
            else:
                _log.warning("media_cleanup_raced", asset_id=str(asset_id))


@job_handler("media_cleanup", MediaCleanupPayload, max_attempts=1)
def media_cleanup(job: JobContext) -> None:
    settings = get_settings()
    storage = get_media_storage(settings, job.clock)
    deleted = run_media_cleanup(job.session_factory, storage, settings, job.clock.now())
    _log.info("media_cleanup_done", deleted=deleted)


@register_periodic
def enqueue_media_cleanup(session: Session, clock: Clock) -> int:
    now = clock.now()
    if (now.hour, now.minute) < (MEDIA_CLEANUP_HOUR_UTC, MEDIA_CLEANUP_MINUTE_UTC):
        return 0
    key = f"media_cleanup:{now:%Y-%m-%d}"
    if session.scalar(select(exists().where(Job.dedup_key == key))):
        return 0  # queued, running, done or dead: today has had its job
    enqueue(
        session,
        "media_cleanup",
        MediaCleanupPayload(),
        workspace_id=None,
        correlation_id=None,
        dedup_key=key,
        clock=clock,
    )
    return 1
