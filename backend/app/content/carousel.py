"""Workspace-scoped ordered media access and atomic replacement."""

import uuid
from collections.abc import Sequence

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.content import media
from app.content.models import ContentItem, ContentItemMedia, MediaAsset
from app.content.validation import CAROUSEL_MAX_ITEMS
from app.core.clock import Clock
from app.core.context import WorkspaceContext
from app.core.errors import AppError


def ordered_asset_ids(
    session: Session, ctx: WorkspaceContext, item: ContentItem
) -> list[uuid.UUID]:
    if item.content_type != "feed_carousel":
        return [item.media_asset_id] if item.media_asset_id else []
    return list(
        session.scalars(
            select(ContentItemMedia.media_asset_id)
            .where(
                ContentItemMedia.workspace_id == ctx.workspace_id,
                ContentItemMedia.content_item_id == item.id,
            )
            .order_by(ContentItemMedia.position)
        )
    )


def ordered_assets(
    session: Session, ctx: WorkspaceContext, item: ContentItem
) -> tuple[MediaAsset, ...]:
    ids = ordered_asset_ids(session, ctx, item)
    assets = (
        {
            a.id: a
            for a in session.scalars(
                select(MediaAsset).where(
                    MediaAsset.workspace_id == ctx.workspace_id,
                    MediaAsset.id.in_(ids),
                    MediaAsset.kind == "image",
                )
            )
        }
        if ids
        else {}
    )
    return tuple(assets[id] for id in ids if id in assets)


def check_shape(
    session: Session,
    ctx: WorkspaceContext,
    content_type: str,
    asset_id: uuid.UUID | None,
    ids: Sequence[uuid.UUID] | None,
    *,
    single_sent: bool = False,
) -> None:
    if (content_type == "feed_carousel" and (asset_id is not None or single_sent)) or (
        content_type != "feed_carousel" and ids is not None
    ):
        raise AppError("CONTENT_MEDIA_SHAPE_INVALID")
    if ids is None:
        return
    if len(ids) > CAROUSEL_MAX_ITEMS:
        raise AppError("CAROUSEL_TOO_MANY_ITEMS", count=len(ids), max=CAROUSEL_MAX_ITEMS)
    if len(set(ids)) != len(ids):
        raise AppError("CAROUSEL_DUPLICATE_MEDIA")
    for id in ids:
        media.get_asset(session, ctx, id)


def replace(
    session: Session,
    clock: Clock,
    ctx: WorkspaceContext,
    item: ContentItem,
    ids: Sequence[uuid.UUID],
) -> None:
    session.execute(
        delete(ContentItemMedia).where(
            ContentItemMedia.workspace_id == ctx.workspace_id,
            ContentItemMedia.content_item_id == item.id,
        )
    )
    session.add_all(
        [
            ContentItemMedia(
                workspace_id=ctx.workspace_id,
                content_item_id=item.id,
                media_asset_id=id,
                position=position,
                created_at=clock.now(),
            )
            for position, id in enumerate(ids)
        ]
    )
    session.flush()
