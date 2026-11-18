"""Read model of content items: the API shape (api-design.md section 2.7)."""

import uuid
from typing import Any, cast
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.models import AgentRun
from app.approvals import repository as approvals_repo
from app.content import carousel, hooks, service, validation
from app.content.models import ContentItem, MediaAsset
from app.content.schemas import (
    ContentApprovalStateOut,
    ContentCheckItemOut,
    ContentIssueOut,
    ContentItemOut,
    ContentMediaItemOut,
    ContentOperationOut,
    ContentValidationOut,
    GenerationOut,
    ScheduleLocalOut,
    TemplateImageStateOut,
)
from app.content.service import Checked
from app.content.templates import link
from app.content.transitions import CANCELLABLE_STATUSES, EDITABLE_STATUSES
from app.core.context import WorkspaceContext
from app.core.i18n import t
from app.identity.models import User
from app.identity.permissions import has_permission


def check_item_out(raw: dict[str, Any], locale: str | None = None) -> ContentCheckItemOut:
    code = str(raw.get("code", ""))
    params = raw.get("params")
    params = params if isinstance(params, dict) else {}
    message = raw.get("message")
    if not isinstance(message, str) and locale is not None:
        message = t(f"content.issue.{code}", locale, **params)
    return ContentCheckItemOut(
        code=code,
        field=raw.get("field") if isinstance(raw.get("field"), str) else None,
        params=params,
        message=message if isinstance(message, str) else None,
    )


def validation_out(raw: dict[str, Any], locale: str | None = None) -> ContentValidationOut:
    """The stored report (or ``{}`` for an item nobody has checked yet)."""
    issues = [
        ContentIssueOut(
            code=str(i.get("code", "")),
            field=str(i.get("field", "caption")),
            span=[int(x) for x in i["span"]] if isinstance(i.get("span"), list) else None,
            text=str(i.get("text", "")),
            matches_verified=bool(i.get("matches_verified")),
            fact_key=i.get("fact_key") if isinstance(i.get("fact_key"), str) else None,
        )
        for i in raw.get("issues", [])
    ]
    return ContentValidationOut(
        passed=bool(raw.get("passed", not issues)),
        issues=issues,
        stale=bool(raw.get("stale")),
        errors=[check_item_out(e, locale) for e in raw.get("errors", [])],
        warnings=[check_item_out(w, locale) for w in raw.get("warnings", [])],
    )


def check_out(checked: Checked, locale: str) -> ContentValidationOut:
    """The result of a dry run: the claim report plus every submit rule found broken."""
    raw = {
        **checked.claims.report,
        "errors": [validation.as_dict(i, locale) for i in checked.result.errors],
        "warnings": [validation.as_dict(i, locale) for i in checked.result.warnings],
    }
    return validation_out(raw, locale)


def schedule_local(item: ContentItem, timezone: str) -> ScheduleLocalOut | None:
    """``scheduled_at`` shown in the workspace timezone, so the client never converts."""
    if item.scheduled_at is None:
        return None
    try:
        zone = ZoneInfo(timezone)
    except ZoneInfoNotFoundError:  # a workspace always has a valid zone; stay safe
        zone = ZoneInfo("UTC")
    local = item.scheduled_at.astimezone(zone)
    return ScheduleLocalOut(
        date=local.strftime("%Y-%m-%d"), time=local.strftime("%H:%M"), timezone=timezone
    )


def approval_state(
    session: Session, ctx: WorkspaceContext, item: ContentItem
) -> ContentApprovalStateOut | None:
    """The state of the item's current approval, or ``None``. Workspace-scoped; shows who
    decided and the note, never the payload or the hash."""
    if item.approval_id is None:
        return None
    approval = approvals_repo.get_approval(session, ctx, item.approval_id)
    if approval is None:
        return None
    name = (
        session.scalar(select(User.display_name).where(User.id == approval.decided_by_user_id))
        if approval.decided_by_user_id
        else None
    )
    return ContentApprovalStateOut(
        status=cast(Any, approval.status),
        subject_version=approval.subject_version,
        expires_at=approval.expires_at,
        decided_by_name=name,
        decided_at=approval.decided_at,
        decision_note=approval.decision_note,
        cancel_reason=approval.cancel_reason,
    )


def generation_out(
    session: Session, ctx: WorkspaceContext, item: ContentItem
) -> GenerationOut | None:
    """The status of the item's AI draft (``null`` for a manual draft). The runner marks a run
    succeeded when the model's output is valid; the text is saved on the draft a moment later,
    and until then the generation is still running for the user. A run whose snapshot has been
    purged is old and finished."""
    if item.agent_run_id is None:
        return None
    run = session.scalar(
        select(AgentRun).where(
            AgentRun.workspace_id == ctx.workspace_id, AgentRun.id == item.agent_run_id
        )
    )
    if run is None:
        return None
    status = run.status
    snapshot = run.input_snapshot
    if status == "succeeded" and snapshot is not None and "stored_at" not in snapshot:
        status = "running"
    return GenerationOut(
        status=cast(Any, status), error_code=run.error_code if status == "failed" else None
    )


def media_deleted(session: Session, ctx: WorkspaceContext, item: ContentItem) -> bool:
    """Whether the item's primary media was removed by the media cleanup (H18): the file is gone."""
    if item.content_type == "feed_carousel":
        return any(a.status == "deleted" for a in carousel.ordered_assets(session, ctx, item))
    if item.media_asset_id is None:
        return False
    expected_kind = "video" if item.content_type == "reel" else "image"
    status = session.scalar(
        select(MediaAsset.status).where(
            MediaAsset.workspace_id == ctx.workspace_id,
            MediaAsset.id == item.media_asset_id,
            MediaAsset.kind == expected_kind,
        )
    )
    return status == "deleted"


def cover_media_deleted(session: Session, ctx: WorkspaceContext, item: ContentItem) -> bool:
    """Whether a reel's uploaded cover image was removed by media cleanup."""
    if item.content_type != "reel" or item.cover_media_asset_id is None:
        return False
    status = session.scalar(
        select(MediaAsset.status).where(
            MediaAsset.workspace_id == ctx.workspace_id,
            MediaAsset.id == item.cover_media_asset_id,
            MediaAsset.kind == "image",
        )
    )
    return status == "deleted"


def _reel_video_duration_ms(
    session: Session, ctx: WorkspaceContext, item: ContentItem
) -> int | None:
    if item.content_type != "reel" or item.media_asset_id is None:
        return None
    return session.scalar(
        select(MediaAsset.duration_ms).where(
            MediaAsset.workspace_id == ctx.workspace_id,
            MediaAsset.id == item.media_asset_id,
            MediaAsset.kind == "video",
        )
    )


def item_out(
    session: Session,
    ctx: WorkspaceContext,
    item: ContentItem,
    *,
    template_states: dict[uuid.UUID, dict[str, Any]] | None = None,
) -> ContentItemOut:
    template_asset_id = (
        item.cover_media_asset_id if item.content_type == "reel" else item.media_asset_id
    )
    if template_states is None:
        template_states = link.states(
            session,
            ctx,
            link.records(session, ctx, [template_asset_id] if template_asset_id else []),
        )
    state = template_states.get(template_asset_id) if template_asset_id else None
    template_image = (
        TemplateImageStateOut(
            **state,
            can_rerender=item.status in EDITABLE_STATUSES
            and has_permission(ctx.role, "content.edit"),
        )
        if state
        else None
    )
    summary = hooks.get().operation_summary(session, ctx, item)
    return ContentItemOut(
        template_image=template_image,
        media_items=[
            ContentMediaItemOut(
                media_asset_id=a.id,
                position=i,
                width=a.width,
                height=a.height,
                media_deleted=a.status == "deleted",
            )
            for i, a in enumerate(carousel.ordered_assets(session, ctx, item))
        ]
        if item.content_type == "feed_carousel"
        else [],
        id=item.id,
        content_type=cast(Any, item.content_type),
        status=cast(Any, item.status),
        version=item.version,
        title=item.title,
        objective=item.objective,
        caption=item.caption,
        overlay_text_suggestions=list(item.overlay_text_suggestions or []),
        visual_notes=item.visual_notes,
        social_account_id=item.social_account_id,
        media_asset_id=item.media_asset_id,
        media_deleted=media_deleted(session, ctx, item),
        cover_media_asset_id=item.cover_media_asset_id,
        thumb_offset_ms=item.thumb_offset_ms,
        share_to_feed=item.share_to_feed,
        cover_media_deleted=cover_media_deleted(session, ctx, item),
        video_duration_ms=_reel_video_duration_ms(session, ctx, item),
        scheduled_at=item.scheduled_at,
        schedule_local=schedule_local(item, ctx.timezone),
        approval_id=item.approval_id,
        approval=approval_state(session, ctx, item),
        operation=(
            ContentOperationOut(
                status=summary.status,
                attempts=summary.attempts,
                next_attempt_at=summary.next_attempt_at,
                last_error_code=summary.last_error_code,
                processing=summary.processing,
            )
            if summary
            else None
        ),
        hold_reason=item.hold_reason,
        rejection_note=item.rejection_note,
        validation=validation_out(item.validation or {}, ctx.locale),
        generation=generation_out(session, ctx, item),
        published_at=item.published_at,
        external_media_id=item.external_media_id,
        external_permalink=item.external_permalink,
        last_error_code=item.last_error_code,
        created_by_user_id=item.created_by_user_id,
        created_at=item.created_at,
        updated_at=item.updated_at,
        is_simulated=item.is_simulated,
        can_cancel=service.may_cancel(session, ctx, item) and item.status in CANCELLABLE_STATUSES,
    )
