"""What the command system knows about content (agent-runtime.md §3, workflows.md §B step 2.1).

Two things come out of one read of the workspace's content:

* the **catalog** the interpreter is shown: items due in the next 14 days plus recent failures,
  as short aliases ``C1``..``Cn`` (never ids), and
* the **context** the resolver turns a reference into one item with: the candidates, the
  alias -> id map of that catalog and the workspace timezone.

The aliases are built when the model is called and handed to the resolution step in memory (the
job holds them between the two transactions), so an alias always means the item the model was
shown, even if new content arrives meanwhile. Everything is scoped by ``workspace_id`` (INV-01).
"""

import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.ai.schemas import MAX_CATALOG_CONTENT, ContentCatalogEntry
from app.commands.resolver import FAILURE_STATUSES, ContentContext, ContentSnapshot
from app.content.models import ContentItem
from app.core.clock import Clock
from app.core.context import WorkspaceContext

UPCOMING_DAYS = 14
FAILURE_DAYS = 14
LOOKAHEAD_DAYS = 60  # the farthest a post can be scheduled (workflows.md §E step 4.1)
POOL_LIMIT = 300
UPCOMING_STATUSES = ("pending_approval", "scheduled", "publishing", "retry_scheduled", "on_hold")


@dataclass(frozen=True)
class ContentView:
    context: ContentContext
    catalog: list[ContentCatalogEntry]


def _snapshot(item: ContentItem) -> ContentSnapshot:
    return ContentSnapshot(
        id=item.id,
        title=item.title,
        content_type=item.content_type,
        status=item.status,
        version=item.version,
        scheduled_at=item.scheduled_at,
        updated_at=item.updated_at,
        last_error_code=item.last_error_code,
        hold_reason=item.hold_reason,
        is_simulated=item.is_simulated,
    )


def load(
    session: Session,
    clock: Clock,
    ctx: WorkspaceContext,
    timezone: str,
    *,
    aliases: Mapping[str, uuid.UUID] | None = None,
) -> ContentView:
    """The candidates and the catalog. With ``aliases`` (the map the model was shown) the
    catalog is not rebuilt: only the resolution context is."""
    now = clock.now()
    recent = now - timedelta(days=FAILURE_DAYS)
    items = session.scalars(
        select(ContentItem)
        .where(
            ContentItem.workspace_id == ctx.workspace_id,
            ContentItem.status != "cancelled",
            or_(
                ContentItem.updated_at >= recent,
                and_(
                    ContentItem.scheduled_at >= recent,
                    ContentItem.scheduled_at <= now + timedelta(days=LOOKAHEAD_DAYS),
                ),
            ),
        )
        .order_by(ContentItem.updated_at.desc(), ContentItem.id)
        .limit(POOL_LIMIT)
    ).all()
    pool = [_snapshot(i) for i in items]

    horizon = now + timedelta(days=UPCOMING_DAYS)
    shown = [
        s
        for s in pool
        if (
            s.status in UPCOMING_STATUSES
            and s.scheduled_at is not None
            and now <= s.scheduled_at <= horizon
        )
        or (s.status in FAILURE_STATUSES and s.updated_at >= recent)
    ]
    shown.sort(key=lambda s: (s.scheduled_at is None, s.scheduled_at or s.updated_at, str(s.id)))
    shown = shown[:MAX_CATALOG_CONTENT]
    tz = ZoneInfo(timezone)
    catalog = [
        ContentCatalogEntry(
            ref_id=f"C{n}",
            title=s.title,
            content_type=s.content_type,
            status=s.status,
            local_schedule=(
                s.scheduled_at.astimezone(tz).isoformat(timespec="minutes")
                if s.scheduled_at
                else None
            ),
        )
        for n, s in enumerate(shown, start=1)
    ]
    built = {f"C{n}": s.id for n, s in enumerate(shown, start=1)}
    context = ContentContext(
        items=pool, aliases=aliases if aliases is not None else built, timezone=timezone
    )
    return ContentView(context, catalog)
