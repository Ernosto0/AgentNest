"""DB-only price-card draft staging; caller owns the transaction."""

import uuid

from sqlalchemy.orm import Session

from app.audit import service as audit
from app.content import service
from app.content.models import ContentItem
from app.content.payload import RenderTemplateImagePayload
from app.content.schemas import empty_validation
from app.content.templates.spec import CardFormat, Language, PriceCard
from app.core.clock import Clock
from app.core.context import WorkspaceContext
from app.jobs.queue import enqueue


def stage_price_card(
    db: Session,
    clock: Clock,
    ctx: WorkspaceContext,
    *,
    command_id: uuid.UUID,
    label: str,
    fact_key: str,
    format: CardFormat,
    language: Language,
) -> ContentItem:
    user_id = service.author_id(ctx)
    request_id = f"command:{command_id}"
    existing = service.existing_for_request(db, ctx, user_id, request_id)
    if existing:
        return existing
    title = ("Fiyat kartı: " if language == "tr" else "Price card: ") + label
    item = ContentItem(
        workspace_id=ctx.workspace_id,
        content_type="story_image" if format == "story" else "feed_image",
        status="draft",
        version=1,
        title=title[:200],
        overlay_text_suggestions=[],
        validation=empty_validation(),
        created_by_user_id=user_id,
        client_request_id=request_id,
        is_simulated=False,
        created_at=clock.now(),
        updated_at=clock.now(),
    )
    db.add(item)
    db.flush()
    audit.record(
        db,
        ctx,
        "content.created",
        "content_item",
        item.id,
        {"content_type": item.content_type, "version": 1, "source": "command"},
        is_simulated=False,
        clock=clock,
    )
    enqueue(
        db,
        "render_template_image",
        RenderTemplateImagePayload(
            content_id=item.id,
            version=1,
            template_input=PriceCard(
                template="price_card", fact_key=fact_key, format=format, language=language
            ),
        ),
        workspace_id=ctx.workspace_id,
        correlation_id=None,
        dedup_key=f"render_template_image:{item.id}",
        clock=clock,
    )
    return item
