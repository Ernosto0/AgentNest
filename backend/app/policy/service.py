"""Automation policies: read with defaults, write with the review stamp (ADR-014).

Saving the policies is the owner's review of the automation (the readiness requirement
``automation_reviewed``): the server stamps ``automation_reviewed_at`` from the injected clock
(INV-19) and audits ``policy.reviewed``. ``auto`` is refused unless the workspace is ``ready``.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit import service as audit
from app.core.clock import Clock
from app.core.context import WorkspaceContext
from app.core.errors import AppError
from app.identity import repository as identity_repo
from app.identity.schemas import WorkspaceSettings
from app.knowledge import readiness as readiness_module
from app.policy.classes import ACTION_CLASSES, DEFAULT_MODE
from app.policy.models import AutomationPolicy
from app.policy.schemas import PoliciesIn


def get_policies(session: Session, workspace_id: uuid.UUID) -> dict[str, str]:
    """Every action class with its mode; classes without a row use the default."""
    rows = session.scalars(
        select(AutomationPolicy).where(AutomationPolicy.workspace_id == workspace_id)
    )
    modes = {row.action_class: row.mode for row in rows}
    return {action: modes.get(action, DEFAULT_MODE) for action in ACTION_CLASSES}


def auto_allowed(session: Session, clock: Clock, ctx: WorkspaceContext) -> tuple[bool, str]:
    """May any class be set to ``auto``? Only when everything for ``ready`` is in place; saving
    the policies is itself the review, so that one requirement does not hold it back."""
    report = readiness_module.readiness(session, clock, ctx)
    open_items = [r.code for r in report.requirements if not r.satisfied]
    return all(code == "automation_reviewed" for code in open_items), report.level


def mode_for(session: Session, workspace_id: uuid.UUID, action_class: str | None) -> str:
    if action_class is None:
        return DEFAULT_MODE
    return get_policies(session, workspace_id).get(action_class, DEFAULT_MODE)


def set_policies(
    session: Session, clock: Clock, ctx: WorkspaceContext, data: PoliciesIn
) -> dict[str, str]:
    """Save the given modes and mark the policy as reviewed. Commits."""
    workspace = identity_repo.get_workspace(session, ctx)
    if workspace is None:
        raise AppError("NOT_FOUND")
    allowed, level = auto_allowed(session, clock, ctx)
    wants_auto = [i.action_class for i in data.items if i.mode == "auto"]
    if wants_auto and not allowed:
        raise AppError(
            "VALIDATION_FAILED",
            errors=[
                {
                    "field": "items",
                    "code": "READINESS_NOT_READY",
                    "params": {"action_classes": wants_auto, "level": level},
                }
            ],
        )
    before = get_policies(session, ctx.workspace_id)
    now = clock.now()
    user_id = uuid.UUID(ctx.actor.id) if ctx.actor.type == "user" and ctx.actor.id else None
    seen: set[str] = set()
    for item in data.items:
        if item.action_class in seen:
            raise AppError(
                "VALIDATION_FAILED",
                errors=[{"field": "items", "code": "duplicate", "params": {}}],
            )
        seen.add(item.action_class)
        row = session.get(AutomationPolicy, (ctx.workspace_id, item.action_class))
        if row is None:
            session.add(
                AutomationPolicy(
                    workspace_id=ctx.workspace_id,
                    action_class=item.action_class,
                    mode=item.mode,
                    updated_by_user_id=user_id,
                    updated_at=now,
                )
            )
        else:
            row.mode, row.updated_by_user_id, row.updated_at = item.mode, user_id, now
    session.flush()
    after = get_policies(session, ctx.workspace_id)
    changed = sorted(a for a in ACTION_CLASSES if before[a] != after[a])
    if changed:
        audit.record(
            session,
            ctx,
            "policy.updated",
            "workspace",
            workspace.id,
            {"changed": {a: {"from": before[a], "to": after[a]} for a in changed}},
            clock=clock,
        )
    settings = WorkspaceSettings.model_validate(workspace.settings)
    if settings.automation_reviewed_at is None:
        merged = settings.model_dump(mode="json")
        merged["automation_reviewed_at"] = now.isoformat()  # server-stamped (INV-19)
        workspace.settings = merged  # a new dict: JSONB change detection
    audit.record(session, ctx, "policy.reviewed", "workspace", workspace.id, {}, clock=clock)
    session.commit()
    return after


def reviewed_at(session: Session, ctx: WorkspaceContext) -> str | None:
    workspace = identity_repo.get_workspace(session, ctx)
    if workspace is None:
        return None
    stamp = WorkspaceSettings.model_validate(workspace.settings).automation_reviewed_at
    return stamp.isoformat() if stamp else None
