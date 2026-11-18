"""Re-render outside the item transaction; attach through the normal versioned edit."""

import uuid

from sqlalchemy.orm import Session

from app.content import service as content
from app.content import transitions
from app.content.models import ContentItem
from app.content.templates import link, service
from app.core.clock import Clock
from app.core.config import Settings
from app.core.context import WorkspaceContext
from app.core.errors import AppError
from app.integrations.storage.base import MediaStorage


def rerender(
    db: Session,
    clock: Clock,
    settings: Settings,
    storage: MediaStorage,
    ctx: WorkspaceContext,
    content_id: uuid.UUID,
    expected_version: int,
) -> ContentItem:
    item = content.get_item(db, ctx, content_id)
    if item.version != expected_version:
        raise AppError("VERSION_CONFLICT", expected=expected_version, current=item.version)
    old_id = item.cover_media_asset_id if item.content_type == "reel" else item.media_asset_id
    target_field = "cover_media_asset_id" if item.content_type == "reel" else "media_asset_id"
    record = link.records(db, ctx, [old_id]).get(old_id) if old_id else None
    if item.status not in transitions.EDITABLE_STATUSES or record is None:
        raise AppError("CONFLICT_STATE", entity="content_item", status=item.status)
    asset = service.create(db, clock, settings, storage, ctx, record.to_input())
    new_id, raw = asset.id, asset.render_record
    if raw is None:
        raise AppError("CONFLICT_STATE")
    db.commit()  # release any refreshed asset snapshot before locking the item
    # Expire the snapshot read before the render; update locks and checks the current version.
    db.expire_all()
    return content.update(
        db,
        clock,
        ctx,
        content_id,
        expected_version=expected_version,
        fields={target_field: new_id},
        rerender_details={
            "old_asset_id": old_id,
            "new_asset_id": new_id,
            "template": raw["template"],
            "facts": raw["facts"],
        },
    )
