"""Workspace-scoped render evidence; render versions override caption versions."""

import uuid
from collections.abc import Iterable, Sequence
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.content.carousel import ordered_asset_ids
from app.content.models import ContentItem, MediaAsset
from app.content.templates.spec import RenderRecord
from app.core.context import WorkspaceContext
from app.knowledge.models import BusinessFact


def records(
    session: Session, ctx: WorkspaceContext, asset_ids: Iterable[uuid.UUID]
) -> dict[uuid.UUID, RenderRecord]:
    ids = set(asset_ids)
    if not ids:
        return {}
    rows = session.execute(
        select(MediaAsset.id, MediaAsset.render_record).where(
            MediaAsset.workspace_id == ctx.workspace_id,
            MediaAsset.id.in_(ids),
            MediaAsset.kind == "image",
            MediaAsset.render_record.is_not(None),
        )
    )
    return {id: RenderRecord.model_validate(raw) for id, raw in rows if raw is not None}


def render_references(
    session: Session, ctx: WorkspaceContext, media_asset_id: uuid.UUID | None
) -> tuple[tuple[uuid.UUID, int], ...]:
    record = records(session, ctx, [media_asset_id]).get(media_asset_id) if media_asset_id else None
    return record.fact_references() if record else ()


def merge_references(
    grounding_refs: Sequence[tuple[uuid.UUID, int]], render_refs: Sequence[tuple[uuid.UUID, int]]
) -> tuple[tuple[uuid.UUID, int], ...]:
    return tuple(dict((*grounding_refs, *render_refs)).items())


def states(
    session: Session, ctx: WorkspaceContext, render_records: dict[uuid.UUID, RenderRecord]
) -> dict[uuid.UUID, dict[str, Any]]:
    if not render_records:
        return {}
    ids = {f.fact_id for r in render_records.values() for f in r.facts}
    facts = {
        f.id: f
        for f in session.scalars(
            select(BusinessFact).where(
                BusinessFact.workspace_id == ctx.workspace_id, BusinessFact.id.in_(ids)
            )
        )
    }
    result = {}
    for asset_id, record in render_records.items():
        uses = []
        for used in record.facts:
            fact = facts.get(used.fact_id)
            uses.append(
                {
                    "key": used.key,
                    "label": fact.label if fact else {},
                    "recorded_version": used.version,
                    "current_version": fact.current_version if fact else None,
                    "usable": fact is not None and fact.status == "verified",
                }
            )
        result[asset_id] = {
            "template": record.template,
            "format": record.format,
            "language": record.language,
            "rendered_at": record.rendered_at,
            "facts": uses,
            "stale": any(
                f["current_version"] != f["recorded_version"] or not f["usable"] for f in uses
            ),
        }
    return result


def item_media_asset_ids(
    session: Session, ctx: WorkspaceContext, item: ContentItem
) -> list[uuid.UUID]:
    """Image assets associated with ``item`` that may hold template render evidence."""
    if item.content_type == "reel":
        return [item.cover_media_asset_id] if item.cover_media_asset_id else []
    return ordered_asset_ids(session, ctx, item)


def item_render_references(
    session: Session, ctx: WorkspaceContext, item: ContentItem
) -> tuple[tuple[uuid.UUID, int], ...]:
    return tuple(
        dict.fromkeys(
            ref
            for record in records(session, ctx, item_media_asset_ids(session, ctx, item)).values()
            for ref in record.fact_references()
        )
    )
