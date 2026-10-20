"""Content items: create, read and edit (workflows.md section E steps 2-3, api-design.md 2.7).

Submission, cancellation and the publish path come in later tasks. Every status change goes
through ``content.transitions.apply``; nothing here assigns ``status``.

An edit that changes the **payload** (caption, overlay suggestions, media) is a new version:
``version + 1``, the claim validation and the ``fact_references`` are recomputed, a pending
approval is cancelled (``SUBJECT_EDITED``) and the queued publish job of the old version is
cancelled. If the item was waiting for approval, scheduled, on hold, rejected or failed it
goes back to ``draft``. A version that was already approved is not "cancelled" (an approval
cannot leave ``approved``); it stays bound to the old version and ``assert_executable`` rejects
it (INV-16). ``published`` content is immutable (INV-17).
"""

import uuid
from collections.abc import Mapping, Sequence
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.approvals import service as approvals
from app.audit import service as audit
from app.content import grounding, media, transitions
from app.content.models import ContentItem
from app.content.payload import publish_job_key
from app.core.clock import Clock
from app.core.context import WorkspaceContext
from app.core.errors import AppError
from app.jobs.queue import cancel_queued
from app.knowledge import impact

SUBJECT_TYPE = transitions.SUBJECT_TYPE
SUBJECT_EDITED = "SUBJECT_EDITED"

# The fields an approval binds (INV-16): changing one is a new version.
PAYLOAD_FIELDS = ("caption", "overlay_text_suggestions", "media_asset_id")
# Internal fields: changing them touches nothing that was approved.
NOTE_FIELDS = ("title", "visual_notes")

# plan.md G15: the content tabs. ``cancelled`` items are in none of them.
TAB_STATUSES: dict[str, tuple[str, ...]] = {
    "drafts": ("draft", "pending_approval"),
    "scheduled": ("scheduled", "publishing", "retry_scheduled"),
    "published": ("published",),
    "problems": ("on_hold", "failed", "rejected"),
}
MAX_LIMIT = 100


# --- reading ---------------------------------------------------------------------------------


def get_item(
    session: Session, ctx: WorkspaceContext, content_id: uuid.UUID, *, lock: bool = False
) -> ContentItem:
    """An item of this workspace; a foreign or unknown id is a 404 (INV-01)."""
    statement = select(ContentItem).where(
        ContentItem.workspace_id == ctx.workspace_id, ContentItem.id == content_id
    )
    item = session.scalars(statement.with_for_update() if lock else statement).one_or_none()
    if item is None:
        raise AppError("NOT_FOUND")
    return item


def list_items(
    session: Session,
    ctx: WorkspaceContext,
    *,
    tab: str | None = None,
    status: str | None = None,
    limit: int = 50,
) -> Sequence[ContentItem]:
    statement = select(ContentItem).where(ContentItem.workspace_id == ctx.workspace_id)
    if tab is not None:
        statement = statement.where(ContentItem.status.in_(TAB_STATUSES[tab]))
    if status is not None:
        statement = statement.where(ContentItem.status == status)
    if tab == "scheduled":  # what goes out next first
        statement = statement.order_by(ContentItem.scheduled_at.asc().nulls_last(), ContentItem.id)
    elif tab == "published":
        statement = statement.order_by(ContentItem.published_at.desc().nulls_last(), ContentItem.id)
    else:
        statement = statement.order_by(ContentItem.updated_at.desc(), ContentItem.id)
    return session.scalars(statement.limit(min(max(limit, 1), MAX_LIMIT))).all()


# --- creating --------------------------------------------------------------------------------


def _clean_text(value: str | None) -> str | None:
    """A blank text is no text."""
    return value if value is not None and value.strip() else None


def _clean_overlay(values: Sequence[str] | None) -> list[str]:
    return [v.strip() for v in (values or []) if v and v.strip()]


def _existing_for_request(
    session: Session, ctx: WorkspaceContext, user_id: uuid.UUID, client_request_id: str
) -> ContentItem | None:
    return session.scalars(
        select(ContentItem).where(
            ContentItem.workspace_id == ctx.workspace_id,
            ContentItem.created_by_user_id == user_id,
            ContentItem.client_request_id == client_request_id,
        )
    ).one_or_none()


def _user_id(ctx: WorkspaceContext) -> uuid.UUID:
    if ctx.actor.type != "user" or ctx.actor.id is None:
        raise ValueError("content items are created by a user")
    return uuid.UUID(ctx.actor.id)


def create_draft(
    session: Session,
    clock: Clock,
    ctx: WorkspaceContext,
    *,
    content_type: str,
    title: str,
    caption: str | None = None,
    overlay_text_suggestions: Sequence[str] | None = None,
    media_asset_id: uuid.UUID | None = None,
    client_request_id: str | None = None,
) -> tuple[ContentItem, bool]:
    """A new ``draft``. Returns ``(item, created)``; with a ``client_request_id`` that this
    author already used, the earlier item and ``False``. Commits."""
    user_id = _user_id(ctx)
    if client_request_id is not None:
        existing = _existing_for_request(session, ctx, user_id, client_request_id)
        if existing is not None:
            return existing, False
    if media_asset_id is not None:
        media.get_asset(session, ctx, media_asset_id)  # 404 unless it is ours and ready

    caption = _clean_text(caption)
    overlay = _clean_overlay(overlay_text_suggestions)
    checked = grounding.check(session, clock, ctx, grounding.texts_of(caption, overlay))
    now = clock.now()
    item = ContentItem(
        workspace_id=ctx.workspace_id,
        content_type=content_type,
        status="draft",
        version=1,
        title=title,
        caption=caption,
        overlay_text_suggestions=overlay,
        media_asset_id=media_asset_id,
        validation=checked.report,
        created_by_user_id=user_id,
        client_request_id=client_request_id,
        is_simulated=False,  # set from the target account at submit
        created_at=now,
        updated_at=now,
    )
    try:
        with session.begin_nested():
            session.add(item)
    except IntegrityError:  # the same request arrived twice at once
        winner = (
            _existing_for_request(session, ctx, user_id, client_request_id)
            if client_request_id is not None
            else None
        )
        if winner is None:
            raise
        return winner, False
    impact.replace_references(session, ctx, SUBJECT_TYPE, item.id, checked.references)
    audit.record(
        session,
        ctx,
        "content.created",
        "content_item",
        item.id,
        {"content_type": content_type, "version": 1, "source": "manual"},
        is_simulated=False,
        clock=clock,
    )
    session.commit()
    return item, True


# --- editing ---------------------------------------------------------------------------------


def update(
    session: Session,
    clock: Clock,
    ctx: WorkspaceContext,
    content_id: uuid.UUID,
    *,
    expected_version: int,
    fields: Mapping[str, Any],
) -> ContentItem:
    """Apply the edits in ``fields`` (only the keys present are touched). Commits.

    ``VERSION_CONFLICT`` if the item moved on; ``CONFLICT_STATE`` if it cannot be edited in
    its status (``published`` and ``cancelled``, or while it is being published).
    """
    item = get_item(session, ctx, content_id, lock=True)
    if item.version != expected_version:
        raise AppError("VERSION_CONFLICT", expected=expected_version, current=item.version)
    if item.status not in transitions.EDITABLE_STATUSES:
        raise AppError("CONFLICT_STATE", entity="content_item", status=item.status)

    wanted: dict[str, Any] = {}
    if "caption" in fields:
        wanted["caption"] = _clean_text(fields["caption"])
    if "overlay_text_suggestions" in fields:
        wanted["overlay_text_suggestions"] = _clean_overlay(fields["overlay_text_suggestions"])
    if "media_asset_id" in fields:
        wanted["media_asset_id"] = fields["media_asset_id"]
    if "title" in fields:
        wanted["title"] = fields["title"]
    if "visual_notes" in fields:
        wanted["visual_notes"] = _clean_text(fields["visual_notes"])
    changed = {k: v for k, v in wanted.items() if getattr(item, k) != v}
    if not changed:
        session.commit()  # nothing to do; release the row lock
        return item

    payload_changed = any(k in changed for k in PAYLOAD_FIELDS)
    if changed.get("media_asset_id") is not None:
        media.get_asset(session, ctx, changed["media_asset_id"])

    if not payload_changed:  # a title or a note: nothing that was approved is touched
        for name, value in changed.items():
            setattr(item, name, value)
        item.updated_at = clock.now()
        audit.record(
            session,
            ctx,
            "content.updated",
            "content_item",
            item.id,
            {"fields": sorted(changed), "version": item.version, "content_type": item.content_type},
            is_simulated=item.is_simulated,
            clock=clock,
        )
        session.commit()
        return item

    previous_version = item.version
    approvals.cancel_for_subject(session, clock, ctx, SUBJECT_TYPE, item.id, SUBJECT_EDITED)
    cancel_queued(session, publish_job_key(item.id, previous_version), clock)
    caption = changed.get("caption", item.caption)
    overlay = (
        changed["overlay_text_suggestions"]
        if "overlay_text_suggestions" in changed
        else list(item.overlay_text_suggestions or [])
    )
    checked = grounding.check(session, clock, ctx, grounding.texts_of(caption, overlay))
    transitions.apply(
        session,
        clock,
        ctx,
        item,
        "edit",
        scheduled_at=None,  # the instant belongs to the version that was approved
        validation=checked.report,
        **changed,
    )
    impact.replace_references(session, ctx, SUBJECT_TYPE, item.id, checked.references)
    session.commit()
    return item


def validate(
    session: Session, clock: Clock, ctx: WorkspaceContext, content_id: uuid.UUID
) -> dict[str, Any]:
    """A dry run of the claim validation on the item as it is now. Changes nothing.

    The submit rules (media, caption length, schedule, capability, quota) join this report
    with the submission task (P5-04).
    """
    item = get_item(session, ctx, content_id)
    texts = grounding.texts_of(item.caption, list(item.overlay_text_suggestions or []))
    return grounding.check(session, clock, ctx, texts).report
