"""Owner-managed follow-up templates, validated against workspace knowledge."""

from pydantic import Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit import service as audit
from app.core.clock import Clock
from app.core.context import WorkspaceContext
from app.core.errors import AppError
from app.identity.models import Workspace
from app.identity.schemas import FollowUpText, StrictModel, WorkspaceSettings
from app.inbox.follow_up import DEFAULT_TEXT_EN, DEFAULT_TEXT_TR
from app.knowledge import approved_answers


class FollowUpSettingsIn(StrictModel):
    enabled: bool
    hours: int = Field(ge=1, le=20)
    text: FollowUpText


class FollowUpSettingsOut(FollowUpSettingsIn):
    default_text: FollowUpText
    min_hours: int = 1
    max_hours: int = 20


def get(session: Session, ctx: WorkspaceContext) -> FollowUpSettingsOut:
    workspace = session.get(Workspace, ctx.workspace_id)
    if workspace is None:
        raise AppError("NOT_FOUND")
    settings = WorkspaceSettings.model_validate(workspace.settings)
    return FollowUpSettingsOut(
        enabled=settings.follow_up_enabled,
        hours=settings.follow_up_hours,
        text=settings.follow_up_text,
        default_text=FollowUpText(tr=DEFAULT_TEXT_TR, en=DEFAULT_TEXT_EN),
    )


def put(
    session: Session,
    clock: Clock,
    ctx: WorkspaceContext,
    body: FollowUpSettingsIn,
) -> FollowUpSettingsOut:
    approved_answers.require(ctx, "workspace.manage")
    workspace = session.scalar(
        select(Workspace).where(Workspace.id == ctx.workspace_id).with_for_update()
    )
    if workspace is None:
        raise AppError("NOT_FOUND")
    for language, template in body.text.model_dump().items():
        if not template:
            continue
        if len(template.encode("utf-8")) > 1000:
            raise AppError(
                "VALIDATION_FAILED",
                errors=[
                    {"field": f"text.{language}", "code": "too_long", "params": {"max_bytes": 1000}}
                ],
            )
        try:
            approved_answers.check_template(template, language, max_bytes=1000)
            approved_answers._references(session, ctx, template)
        except AppError as exc:
            errors = exc.params.get("errors", [])
            for error in errors:
                error["field"] = f"text.{language}"
            raise
    changed = {
        "follow_up_enabled": body.enabled,
        "follow_up_hours": body.hours,
        "follow_up_text": body.text.model_dump(),
    }
    keys = [key for key, value in changed.items() if workspace.settings.get(key) != value]
    workspace.settings = WorkspaceSettings.model_validate(
        {**workspace.settings, **changed}
    ).model_dump(mode="json")
    audit.record(
        session,
        ctx,
        "follow_up.settings_changed",
        "workspace",
        workspace.id,
        {"changed_keys": keys},
        clock=clock,
    )
    session.commit()
    return get(session, ctx)
