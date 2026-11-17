"""Render jobs separate read snapshots, Pillow/storage, and version-fenced attachment."""

from sqlalchemy import select

from app.audit import service as audit
from app.content import service as content
from app.content.models import ContentItem
from app.content.payload import RenderTemplateImagePayload
from app.content.templates import service
from app.core.config import get_settings
from app.core.context import ActorRef
from app.core.errors import AppError
from app.identity.models import Workspace
from app.identity.service import workspace_context
from app.integrations.storage.registry import get_media_storage
from app.jobs.registry import JobContext, job_handler


def failed(job: JobContext, code: str) -> None:
    payload = job.payload
    if not isinstance(payload, RenderTemplateImagePayload) or job.workspace_id is None:
        return
    with job.session_factory() as db:
        workspace = db.get(Workspace, job.workspace_id)
        item = db.scalar(
            select(ContentItem).where(
                ContentItem.workspace_id == job.workspace_id, ContentItem.id == payload.content_id
            )
        )
        if workspace is None or item is None:
            return
        ctx = workspace_context(workspace, ActorRef.system("render_template_image"), None)
        audit.record(
            db,
            ctx,
            "content.template_image_failed",
            "content_item",
            item.id,
            {"code": code},
            is_simulated=item.is_simulated,
            clock=job.clock,
        )
        db.commit()


@job_handler("render_template_image", RenderTemplateImagePayload, max_attempts=3, on_dead=failed)
def render_template_image(job: JobContext) -> None:
    payload = job.payload
    if not isinstance(payload, RenderTemplateImagePayload) or job.workspace_id is None:
        return
    settings = get_settings()
    storage = get_media_storage(settings, job.clock)
    try:
        with job.session_factory() as db:
            workspace = db.get(Workspace, job.workspace_id)
            item = db.scalar(
                select(ContentItem).where(
                    ContentItem.workspace_id == job.workspace_id,
                    ContentItem.id == payload.content_id,
                )
            )
            if (
                workspace is None
                or item is None
                or item.status != "draft"
                or item.version != payload.version
                or item.media_asset_id is not None
            ):
                return
            ctx = workspace_context(workspace, ActorRef.system("render_template_image"), None)
            # prepare commits its read snapshot before drawing or storage I/O.
            asset = service.create(db, job.clock, settings, storage, ctx, payload.template_input)
            asset_id = asset.id
            db.commit()
        with job.session_factory() as db:
            item = content.get_item(db, ctx, payload.content_id, lock=True)
            if (
                item.status != "draft"
                or item.version != payload.version
                or item.media_asset_id is not None
            ):
                raise AppError("VERSION_CONFLICT")
            content.update(
                db,
                job.clock,
                ctx,
                item.id,
                expected_version=payload.version,
                fields={"media_asset_id": asset_id},
            )
    except AppError as exc:
        if exc.code.startswith("TEMPLATE_") or exc.code in {
            "VERSION_CONFLICT",
            "CONFLICT_STATE",
            "NOT_FOUND",
        }:
            failed(job, exc.code)
            return
        raise
