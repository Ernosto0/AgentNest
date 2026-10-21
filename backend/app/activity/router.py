"""Activity route (api-design.md section 2.8): the audit log of the workspace, newest first.

Owners and managers only (``activity.view``). A foreign workspace id is a 404 (INV-01). Texts and
labels are rendered in the reader's UI language; the day filter uses the workspace timezone.
"""

from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.activity import feed, labels
from app.activity.groups import Group, group_of
from app.activity.schemas import (
    ActivityActorOut,
    ActivityEntryOut,
    ActivityResourceOut,
)
from app.api.deps import current_auth, require_membership
from app.core.context import WorkspaceContext
from app.core.db import get_db
from app.core.i18n import catalog_keys, normalize_locale, t
from app.core.pagination import Page
from app.identity.service import AuthenticatedSession

router = APIRouter(prefix="/workspaces/{workspace_id}/activity", tags=["activity"])


@router.get("", response_model=Page[ActivityEntryOut])
def list_activity(
    group: Group | None = Query(default=None, alias="type"),
    local_date: date | None = Query(default=None, alias="date"),
    cursor: str | None = None,
    limit: int = Query(default=feed.DEFAULT_LIMIT, ge=1, le=feed.MAX_LIMIT),
    ctx: WorkspaceContext = Depends(require_membership("activity.view")),
    auth: AuthenticatedSession = Depends(current_auth),
    db: Session = Depends(get_db),
) -> Page[ActivityEntryOut]:
    locale = normalize_locale(auth.user.ui_locale)
    page = feed.list_feed(db, ctx, group=group, local_date=local_date, cursor=cursor, limit=limit)
    actors = labels.resolve_actors(db, ctx, page.rows, locale)
    resources = labels.resolve_resources(db, ctx, page.rows, locale)
    known = catalog_keys(locale)
    items = []
    for row in page.rows:
        actor = actors[row.id]
        resource = resources.get(row.id)
        key = f"activity.{row.action}"
        items.append(
            ActivityEntryOut(
                id=row.id,
                action=row.action,
                group=group_of(row.action),
                occurred_at=row.occurred_at,
                actor=ActivityActorOut(type=actor.type, label=actor.label),
                text=t(key if key in known else "activity.unknown", locale),
                resource=None
                if resource is None
                else ActivityResourceOut(
                    type=resource.type, id=resource.id, label=resource.label, link=resource.link
                ),
                is_simulated=row.is_simulated,
            )
        )
    return Page[ActivityEntryOut](items=items, next_cursor=page.next_cursor)
