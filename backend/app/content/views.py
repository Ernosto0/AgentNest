"""Read model of content items: the API shape (api-design.md section 2.7)."""

from typing import Any, cast
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.approvals import repository as approvals_repo
from app.content import hooks
from app.content.models import ContentItem
from app.content.schemas import (
    ContentApprovalStateOut,
    ContentIssueOut,
    ContentItemOut,
    ContentOperationOut,
    ContentValidationOut,
    ScheduleLocalOut,
)
from app.core.context import WorkspaceContext
from app.identity.models import User


def validation_out(raw: dict[str, Any]) -> ContentValidationOut:
    """The stored report (or ``{}`` for an item nobody has checked yet)."""
    issues = [
        ContentIssueOut(
            code=str(i.get("code", "")),
            field=str(i.get("field", "caption")),
            span=[int(x) for x in i["span"]] if isinstance(i.get("span"), list) else None,
            text=str(i.get("text", "")),
            matches_verified=bool(i.get("matches_verified")),
        )
        for i in raw.get("issues", [])
    ]
    return ContentValidationOut(
        passed=bool(raw.get("passed", not issues)), issues=issues, stale=bool(raw.get("stale"))
    )


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


def item_out(session: Session, ctx: WorkspaceContext, item: ContentItem) -> ContentItemOut:
    summary = hooks.get().operation_summary(session, ctx, item)
    return ContentItemOut(
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
            )
            if summary
            else None
        ),
        hold_reason=item.hold_reason,
        rejection_note=item.rejection_note,
        validation=validation_out(item.validation or {}),
        published_at=item.published_at,
        external_media_id=item.external_media_id,
        external_permalink=item.external_permalink,
        last_error_code=item.last_error_code,
        created_by_user_id=item.created_by_user_id,
        created_at=item.created_at,
        updated_at=item.updated_at,
        is_simulated=item.is_simulated,
    )
