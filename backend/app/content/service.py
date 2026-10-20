"""Content items: create, read and edit (workflows.md section E steps 2-3, api-design.md 2.7).

Submission (``submit``), cancellation (``cancel``) and re-approval (``reapprove``) are below the
edit path; the publish executor is a later task. Every status change goes through
``content.transitions.apply``; nothing here assigns ``status``.

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
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.approvals import service as approvals
from app.approvals.grants import record_policy_grant
from app.audit import service as audit
from app.content import grounding, hooks, media, scheduling, transitions, validation
from app.content.models import ContentItem, MediaAsset
from app.content.payload import (
    APPROVAL_ACTION,
    APPROVAL_PERMISSION,
    PublishContentPayload,
    approval_payload,
    approval_summary,
    publish_job_key,
)
from app.core.clock import Clock
from app.core.config import Settings
from app.core.context import WorkspaceContext
from app.core.errors import AppError
from app.identity import repository as identity_repo
from app.identity.permissions import has_permission
from app.identity.schemas import WorkspaceSettings
from app.integrations.instagram import queries as accounts
from app.integrations.instagram.models import SocialAccount
from app.jobs.queue import cancel_queued, enqueue
from app.knowledge import impact

SUBJECT_TYPE = transitions.SUBJECT_TYPE
SUBJECT_EDITED = "SUBJECT_EDITED"
SUBJECT_CANCELLED = "SUBJECT_CANCELLED"

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


def existing_for_request(
    session: Session, ctx: WorkspaceContext, user_id: uuid.UUID, client_request_id: str
) -> ContentItem | None:
    return session.scalars(
        select(ContentItem).where(
            ContentItem.workspace_id == ctx.workspace_id,
            ContentItem.created_by_user_id == user_id,
            ContentItem.client_request_id == client_request_id,
        )
    ).one_or_none()


def author_id(ctx: WorkspaceContext) -> uuid.UUID:
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
    user_id = author_id(ctx)
    if client_request_id is not None:
        existing = existing_for_request(session, ctx, user_id, client_request_id)
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
            existing_for_request(session, ctx, user_id, client_request_id)
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


def _post_times(
    session: Session,
    ctx: WorkspaceContext,
    account_id: uuid.UUID,
    item_id: uuid.UUID,
    around: datetime,
) -> list[datetime]:
    """When this account's other posts go out, or went out, within 24 h of ``around``: items that
    are scheduled, being published or waiting for a retry (their ``scheduled_at``) and items
    already published (their ``published_at``). A post waiting for approval is not counted: it is
    not committed to going out."""
    low, high = around - scheduling.QUOTA_WINDOW, around + scheduling.QUOTA_WINDOW
    base = (
        ContentItem.workspace_id == ctx.workspace_id,
        ContentItem.social_account_id == account_id,
        ContentItem.id != item_id,
    )
    planned = session.scalars(
        select(ContentItem.scheduled_at).where(
            *base,
            ContentItem.status.in_(("scheduled", "publishing", "retry_scheduled")),
            ContentItem.scheduled_at > low,
            ContentItem.scheduled_at < high,
        )
    ).all()
    published = session.scalars(
        select(ContentItem.published_at).where(
            *base,
            ContentItem.status == "published",
            ContentItem.published_at > low,
            ContentItem.published_at < high,
        )
    ).all()
    return [t for t in (*planned, *published) if t is not None]


# --- submitting ------------------------------------------------------------------------------


@dataclass(frozen=True)
class ScheduleRequest:
    """When the owner wants the post out: ``publish_now``, or a local date and ``HH:MM``."""

    publish_now: bool = False
    local_date: date | None = None
    local_time: str | None = None


@dataclass(frozen=True)
class Checked:
    """Everything one submit-time check found out."""

    claims: grounding.Grounding
    result: validation.SubmitValidation
    resolved: scheduling.ResolvedSchedule | None
    account: SocialAccount | None
    media: MediaAsset | None


@dataclass(frozen=True)
class Ready:
    """A check that passed, with the schedule, account and media a submission needs."""

    claims: grounding.Grounding
    result: validation.SubmitValidation
    resolved: scheduling.ResolvedSchedule
    account: SocialAccount
    media: MediaAsset


def may_approve(ctx: WorkspaceContext) -> bool:
    return ctx.role is not None and has_permission(ctx.role, APPROVAL_PERMISSION)


def _check(
    session: Session,
    clock: Clock,
    settings: Settings,
    ctx: WorkspaceContext,
    item: ContentItem,
    schedule: ScheduleRequest | None,
    *,
    needs_approval: bool,
) -> Checked:
    """Gather the facts of a submission and run the G17 rules. Changes nothing."""
    asset = (
        session.scalar(
            select(MediaAsset).where(
                MediaAsset.workspace_id == ctx.workspace_id, MediaAsset.id == item.media_asset_id
            )
        )
        if item.media_asset_id is not None
        else None
    )
    overlay = list(item.overlay_text_suggestions or [])
    claims = grounding.check(session, clock, ctx, grounding.texts_of(item.caption, overlay))

    resolved: scheduling.ResolvedSchedule | None = None
    schedule_error: validation.Issue | None = None
    if schedule is not None:
        try:
            resolved = scheduling.resolve(
                now=clock.now(),
                timezone=ctx.timezone,
                local_date=schedule.local_date,
                local_time=schedule.local_time,
                publish_now=schedule.publish_now,
                needs_approval=needs_approval,
            )
        except scheduling.ScheduleError as exc:
            schedule_error = validation.Issue(exc.code, "schedule", exc.params)

    # The workspace's one active account (one per workspace, mock in Phase 5). A content item
    # has no account until it is submitted; submit sets it (api-design.md 2.7).
    account = accounts.get_active_for_workspace(session, ctx.workspace_id)
    connected = account is not None and account.status == "connected"
    quota_exceeded = False
    if resolved is not None and account is not None and connected:
        quota_exceeded = scheduling.quota_forecast_exceeded(
            _post_times(session, ctx, account.id, item.id, resolved.scheduled_at),
            resolved.scheduled_at,
            settings.publish_daily_limit,
        )

    result = validation.validate_submission(
        validation.SubmitFacts(
            content_type=item.content_type,
            caption=item.caption,
            overlay_text_suggestions=overlay,
            media=(
                validation.MediaFacts(asset.status, asset.width, asset.height)
                if asset is not None
                else None
            ),
            claim_issues=claims.blocking,
            schedule_error=schedule_error,
            account=(
                validation.AccountFacts(connected, account.capabilities)
                if account is not None
                else None
            ),
            quota_exceeded=quota_exceeded,
        )
    )
    return Checked(claims, result, resolved, account, asset)


def validate(
    session: Session,
    clock: Clock,
    settings: Settings,
    ctx: WorkspaceContext,
    content_id: uuid.UUID,
    *,
    schedule: ScheduleRequest | None = None,
    self_approve: bool = False,
) -> Checked:
    """A dry run of everything a submit checks, on the item as it is now. Changes nothing.

    Without a ``schedule`` the schedule and quota rules are skipped.
    """
    item = get_item(session, ctx, content_id)
    needs_approval = not (self_approve and may_approve(ctx))
    return _check(session, clock, settings, ctx, item, schedule, needs_approval=needs_approval)


def stored_report(checked: Checked | Ready) -> dict[str, Any]:
    """What ``content_items.validation`` keeps after a successful check: the claim report and
    the warnings (errors cannot be there: they stop the submission)."""
    return {
        **checked.claims.report,
        "warnings": [validation.as_dict(w) for w in checked.result.warnings],
    }


def _require_valid(checked: Checked, locale: str) -> Ready:
    """``checked`` as a ``Ready`` or ``CONTENT_VALIDATION_FAILED`` listing every blocking item."""
    if (
        not checked.result.ok
        or checked.resolved is None
        or checked.account is None
        or checked.media is None
    ):
        raise AppError(
            "CONTENT_VALIDATION_FAILED",
            errors=[validation.as_dict(i, locale) for i in checked.result.errors],
            warnings=[validation.as_dict(i, locale) for i in checked.result.warnings],
        )
    return Ready(checked.claims, checked.result, checked.resolved, checked.account, checked.media)


def _max_delay(session: Session, ctx: WorkspaceContext) -> timedelta:
    """``publish_max_delay_minutes`` of the workspace (plan.md G16)."""
    workspace = identity_repo.get_workspace(session, ctx)
    minutes = WorkspaceSettings.model_validate(
        workspace.settings if workspace is not None else {}
    ).publish_max_delay_minutes
    return timedelta(minutes=minutes)


def _approval_arguments(
    session: Session, ctx: WorkspaceContext, item: ContentItem, ready: Ready, version: int
) -> dict[str, Any]:
    """The keyword arguments of the approval of ``item`` as ``version``: exactly the payload the
    approver sees (plan.md G5), valid until the instant it would go out."""
    scheduled_at = ready.resolved.scheduled_at
    return {
        "action": APPROVAL_ACTION,
        "subject_type": SUBJECT_TYPE,
        "subject_id": item.id,
        "subject_version": version,
        "payload": approval_payload(
            item,
            version=version,
            social_account_id=ready.account.id,
            media_sha256=ready.media.sha256,
            scheduled_at=scheduled_at,
        ),
        "summary": approval_summary(item, scheduled_at),
        "required_permission": APPROVAL_PERMISSION,
        "expires_at": scheduled_at,
        "execute_before": scheduled_at + _max_delay(session, ctx),
        "is_simulated": ready.account.is_simulated,
    }


def enqueue_publish(session: Session, clock: Clock, item: ContentItem) -> None:
    """Queue the ``publish_content`` job of the item's current version at ``scheduled_at``
    (dedup key per version). In the caller's transaction."""
    if item.scheduled_at is None:
        raise ValueError("a content item is queued for publishing with its instant")
    enqueue(
        session,
        "publish_content",
        PublishContentPayload(content_id=item.id, version=item.version),
        workspace_id=item.workspace_id,
        correlation_id=None,
        run_at=item.scheduled_at,
        dedup_key=publish_job_key(item.id, item.version),
        clock=clock,
    )


def _schedule_changes(ready: Ready) -> dict[str, Any]:
    return {
        "social_account_id": ready.account.id,
        "is_simulated": ready.account.is_simulated,
        "scheduled_at": ready.resolved.scheduled_at,
        "schedule_input": ready.resolved.input,
        "validation": stored_report(ready),
    }


def _expect_version(item: ContentItem, expected_version: int | None) -> None:
    if expected_version is not None and item.version != expected_version:
        raise AppError("VERSION_CONFLICT", expected=expected_version, current=item.version)


def submit(
    session: Session,
    clock: Clock,
    settings: Settings,
    ctx: WorkspaceContext,
    content_id: uuid.UUID,
    *,
    schedule: ScheduleRequest,
    self_approve: bool,
    expected_version: int,
) -> ContentItem:
    """Validate everything and submit a ``draft``. Commits (workflows.md section E step 4).

    - ``self_approve`` by someone who holds ``content.approve``: the approval is recorded as
      decided in this transaction and the item is ``scheduled`` with its job queued.
    - Otherwise a pending ``content.publish`` approval is requested (it expires at
      ``scheduled_at``) and the item is ``pending_approval``. The instant must be at least 15
      minutes ahead, so nobody without the permission can publish "now".
    - ``self_approve`` without the permission is ``FORBIDDEN``.

    ``CONTENT_VALIDATION_FAILED`` (422) lists every blocking item; the item stays a draft.
    """
    item = get_item(session, ctx, content_id, lock=True)
    _expect_version(item, expected_version)
    if item.status != "draft":
        raise AppError("CONFLICT_STATE", entity="content_item", status=item.status)
    if self_approve and not may_approve(ctx):
        raise AppError("FORBIDDEN", permission=APPROVAL_PERMISSION)

    checked = _check(session, clock, settings, ctx, item, schedule, needs_approval=not self_approve)
    ready = _require_valid(checked, ctx.locale)

    arguments = _approval_arguments(session, ctx, item, ready, item.version)
    changes = _schedule_changes(ready)
    if self_approve:
        approval = record_policy_grant(session, clock, ctx, self_approved=True, **arguments)
        transitions.apply(session, clock, ctx, item, "schedule", approval_id=approval.id, **changes)
        enqueue_publish(session, clock, item)
    else:
        approval = approvals.request(session, clock, ctx, kind="authorization", **arguments)
        transitions.apply(session, clock, ctx, item, "submit", approval_id=approval.id, **changes)
    # The facts the text states *now*: a value typed before its fact was verified is grounded
    # only at this check, and a later change of that fact must reach the scheduled item.
    impact.replace_references(session, ctx, SUBJECT_TYPE, item.id, ready.claims.references)
    session.commit()
    return item


def reapprove(
    session: Session,
    clock: Clock,
    settings: Settings,
    ctx: WorkspaceContext,
    content_id: uuid.UUID,
    *,
    schedule: ScheduleRequest,
    expected_version: int,
) -> ContentItem:
    """Re-approve an ``on_hold`` item for a new instant (plan.md G2). Commits.

    The content is unchanged, but **the version increases**: the schedule is part of the
    approval payload, so the new approval, job and operation get fresh ``publish:{id}:v{n}``
    keys and the old ones can never fire. Everything is validated again, so a caption that
    still shows an old price fails and has to be edited. Needs ``content.approve``; the
    approval is recorded as decided in this transaction.
    """
    item = get_item(session, ctx, content_id, lock=True)
    _expect_version(item, expected_version)
    if item.status != "on_hold":
        raise AppError("CONFLICT_STATE", entity="content_item", status=item.status)
    if not may_approve(ctx):
        raise AppError("FORBIDDEN", permission=APPROVAL_PERMISSION)

    checked = _check(session, clock, settings, ctx, item, schedule, needs_approval=False)
    ready = _require_valid(checked, ctx.locale)

    new_version = item.version + 1
    approval = record_policy_grant(
        session,
        clock,
        ctx,
        self_approved=True,
        **_approval_arguments(session, ctx, item, ready, new_version),
    )
    transitions.apply(
        session,
        clock,
        ctx,
        item,
        "reapprove",
        approval_id=approval.id,
        **_schedule_changes(ready),
    )
    impact.replace_references(session, ctx, SUBJECT_TYPE, item.id, ready.claims.references)
    enqueue_publish(session, clock, item)
    session.commit()
    return item


# --- cancelling ------------------------------------------------------------------------------


def apply_cancel(
    session: Session,
    clock: Clock,
    ctx: WorkspaceContext,
    content_id: uuid.UUID,
    *,
    expected_version: int | None = None,
) -> ContentItem:
    """Cancel a draft, an item waiting for approval, a scheduled one, one on hold or one waiting
    for a retry (workflows.md section E step 7). **No commit**: the caller owns the transaction
    (the route commits; the command executor runs inside an approval's decision).

    A pending approval is cancelled (``SUBJECT_CANCELLED``), the queued publish job is
    cancelled, and a waiting operation is cancelled through the ledger hook. An item that is
    ``publishing`` is a ``CONFLICT_STATE``: the outcome must be known first. An approval that
    was already ``approved`` stays so; it can authorise nothing once the item is cancelled.
    """
    item = get_item(session, ctx, content_id, lock=True)
    _expect_version(item, expected_version)
    transitions.next_status(item.status, "cancel")  # CONFLICT_STATE before anything is touched
    approvals.cancel_for_subject(session, clock, ctx, SUBJECT_TYPE, item.id, SUBJECT_CANCELLED)
    cancel_queued(session, publish_job_key(item.id, item.version), clock)
    hooks.get().cancel_operation(session, clock, ctx, item, SUBJECT_CANCELLED)
    transitions.apply(session, clock, ctx, item, "cancel")
    return item


def cancel(
    session: Session,
    clock: Clock,
    ctx: WorkspaceContext,
    content_id: uuid.UUID,
    *,
    expected_version: int | None = None,
) -> ContentItem:
    """``apply_cancel`` and commit (the cancel route)."""
    item = apply_cancel(session, clock, ctx, content_id, expected_version=expected_version)
    session.commit()
    return item
