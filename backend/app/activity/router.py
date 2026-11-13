"""Activity routes (api-design.md section 2.8): the audit log of the workspace, newest first, and
a summary of recent days.

Owners and managers only (``activity.view``). A foreign workspace id is a 404 (INV-01). Texts and
labels are rendered in the reader's UI language; days use the workspace timezone.
"""

import uuid
from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.activity import describe, feed, labels, summary
from app.activity.classify import Level, classify
from app.activity.groups import Group, group_of
from app.activity.schemas import (
    ActivityActorOut,
    ActivityDetailOut,
    ActivityEntryOut,
    ActivityResourceOut,
    ActivitySummaryOut,
)
from app.api.deps import current_auth, get_clock, require_membership
from app.core.clock import Clock
from app.core.context import WorkspaceContext
from app.core.db import get_db
from app.core.i18n import normalize_locale
from app.core.pagination import Page
from app.identity.service import AuthenticatedSession

router = APIRouter(prefix="/workspaces/{workspace_id}/activity", tags=["activity"])


@router.get("", response_model=Page[ActivityEntryOut])
def list_activity(
    group: Group | None = Query(default=None, alias="type"),
    local_date: date | None = Query(default=None, alias="date"),
    level: list[Level] | None = Query(default=None),
    include_routine: bool = True,
    correlation: uuid.UUID | None = None,
    cursor: str | None = None,
    limit: int = Query(default=feed.DEFAULT_LIMIT, ge=1, le=feed.MAX_LIMIT),
    ctx: WorkspaceContext = Depends(require_membership("activity.view")),
    auth: AuthenticatedSession = Depends(current_auth),
    db: Session = Depends(get_db),
) -> Page[ActivityEntryOut]:
    locale = normalize_locale(auth.user.ui_locale)
    page = feed.list_feed(
        db,
        ctx,
        group=group,
        local_date=local_date,
        cursor=cursor,
        limit=limit,
        levels=set(level) if level else None,
        include_routine=include_routine,
        correlation_id=correlation,
    )
    actors = labels.resolve_actors(db, ctx, page.rows, locale)
    resources = labels.resolve_resources(db, ctx, page.rows, locale)
    texts = describe.texts_for(locale)
    items = []
    for row in page.rows:
        actor = actors[row.id]
        resource = resources.get(row.id)
        found = classify(row.action, row.actor_type, row.metadata_)
        items.append(
            ActivityEntryOut(
                id=row.id,
                action=row.action,
                group=group_of(row.action),
                occurred_at=row.occurred_at,
                actor=ActivityActorOut(type=actor.type, label=actor.label),
                text=describe.entry_text(row, texts),
                resource=None
                if resource is None
                else ActivityResourceOut(
                    type=resource.type, id=resource.id, label=resource.label, link=resource.link
                ),
                is_simulated=row.is_simulated,
                level=found.level,
                routine=found.routine,
                collapse_key=describe.collapse_key(row, found),
                correlation_id=row.correlation_id,
                details=[
                    ActivityDetailOut(key=d.key, label=d.label, value=d.value)
                    for d in describe.entry_details(row, texts, ctx.timezone)
                ],
            )
        )
    return Page[ActivityEntryOut](items=items, next_cursor=page.next_cursor)


@router.get("/summary", response_model=ActivitySummaryOut)
def activity_summary(
    days: int = Query(default=summary.DEFAULT_DAYS, ge=1, le=summary.MAX_DAYS),
    ctx: WorkspaceContext = Depends(require_membership("activity.view")),
    clock: Clock = Depends(get_clock),
    db: Session = Depends(get_db),
) -> ActivitySummaryOut:
    found = summary.summarize(db, ctx, clock, days)
    return ActivitySummaryOut(
        days=found.days,
        period_start=found.period_start,
        period_end=found.period_end,
        total=found.total,
        routine=found.routine,
        failure=found.failure,
        warning=found.warning,
        success=found.success,
    )
