"""Owner account-agent delegation controls."""

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.agent import delegation
from app.agent.grounding import FactEvidence
from app.agent.models import AgentAction, AgentDelegation, AgentSession, AgentThread
from app.agent.personality import (
    PersonalityChange,
    PersonalityOut,
    change_personality,
    read_personality,
)
from app.agent.repository import AgentScopeError, scoped_account
from app.api.deps import get_clock, require_membership
from app.audit import service as audit
from app.core.clock import Clock
from app.core.context import WorkspaceContext
from app.core.db import get_db
from app.core.errors import AppError

router = APIRouter(prefix="/workspaces/{workspace_id}/accounts/{account_id}/agent", tags=["agent"])

from app.agent.control import ControllerChange, change_controller  # noqa: E402


class ControllerOut(BaseModel):
    state: str
    controller_mode: str
    config_version: int
    controller_epoch: int


@router.post("/activate", response_model=ControllerOut)
def activate_agent(
    account_id: uuid.UUID,
    body: ControllerChange,
    ctx: WorkspaceContext = Depends(require_membership("agent.control")),
    db: Session = Depends(get_db),
    clock: Clock = Depends(get_clock),
) -> ControllerOut:
    try:
        account = change_controller(db, clock, ctx, account_id, body)
    except AgentScopeError as exc:
        raise AppError("NOT_FOUND") from exc
    db.commit()
    return ControllerOut(
        state=account.state,
        controller_mode=account.controller_mode,
        config_version=account.config_version,
        controller_epoch=account.controller_epoch,
    )


@router.get("/personality", response_model=PersonalityOut)
def get_personality(
    account_id: uuid.UUID,
    ctx: WorkspaceContext = Depends(require_membership()),
    db: Session = Depends(get_db),
) -> PersonalityOut:
    try:
        account = scoped_account(db, ctx.workspace_id, account_id)
    except AgentScopeError as exc:
        raise AppError("NOT_FOUND") from exc
    return read_personality(account)


@router.patch("/personality", response_model=PersonalityOut)
def patch_personality(
    account_id: uuid.UUID,
    body: PersonalityChange,
    ctx: WorkspaceContext = Depends(require_membership("agent.settings.edit")),
    db: Session = Depends(get_db),
    clock: Clock = Depends(get_clock),
) -> PersonalityOut:
    result = change_personality(db, clock, ctx, account_id, body)
    db.commit()
    return result


class DelegationPreview(BaseModel):
    next_version: int
    changed_actions: list[str]


class ContentPreview(BaseModel):
    account_id: uuid.UUID
    content_id: uuid.UUID | None = None
    version: int
    content_type: str | None = None
    caption: str | None = None
    media_asset_id: uuid.UUID | None = None
    media_sha256: str | None = None
    scheduled_at: datetime | None = None
    execute_before: datetime | None = None
    overlay_text: list[str] = Field(default_factory=list)
    fact_versions: list[FactEvidence] = Field(default_factory=list)


class ActionOut(BaseModel):
    id: uuid.UUID
    action_type: str
    status: str
    operation_id: uuid.UUID | None
    approval_id: uuid.UUID | None
    outcome_code: str | None
    content: ContentPreview | None = None


@router.get("/actions/{action_id}", response_model=ActionOut)
def action_detail(
    account_id: uuid.UUID,
    action_id: uuid.UUID,
    ctx: WorkspaceContext = Depends(require_membership("approvals.view")),
    db: Session = Depends(get_db),
) -> ActionOut:
    try:
        scoped_account(db, ctx.workspace_id, account_id)
    except AgentScopeError as exc:
        raise AppError("NOT_FOUND") from exc
    action = db.scalar(
        select(AgentAction).where(
            AgentAction.id == action_id,
            AgentAction.workspace_id == ctx.workspace_id,
            AgentAction.social_account_id == account_id,
        )
    )
    if action is None:
        raise AppError("NOT_FOUND")
    preview = None
    if action.content_intent is not None:
        from app.agent.content import result

        result(db, action)
        intent = action.content_intent
        payload = intent.get("payload", {})
        request = intent.get("request", {})
        preview = ContentPreview(
            account_id=account_id,
            content_id=action.payload_ref,
            version=action.version,
            content_type=payload.get("content_type", request.get("content_type")),
            caption=payload.get("caption", intent.get("rendered_caption")),
            media_asset_id=payload.get("media_asset_id", request.get("media_asset_id")),
            media_sha256=payload.get("media_sha256", intent.get("media_sha256")),
            scheduled_at=payload.get("scheduled_at"),
            execute_before=action.execute_before,
            overlay_text=payload.get("overlay_text", []),
            fact_versions=[
                FactEvidence(id=fid, version=version)
                for fid, version in payload.get("fact_versions", [])
            ]
            if payload
            else [
                FactEvidence.model_validate(source)
                for source in (request.get("caption") or {}).get("fact_sources", [])
            ],
        )
    if action.action_type.startswith("comment."):
        from app.comments.actions import result

        result(db, action)
    return ActionOut(
        id=action.id,
        action_type=action.action_type,
        status=action.status,
        operation_id=action.operation_id,
        approval_id=action.approval_id,
        outcome_code=action.outcome_code,
        content=preview,
    )


class DelegationOut(BaseModel):
    id: uuid.UUID
    version: int
    policy: delegation.DelegationPolicy
    config_version: int
    controller_epoch: int


class StateChange(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_config_version: int = Field(ge=1)


class StateOut(BaseModel):
    state: str
    controller_mode: str
    config_version: int
    controller_epoch: int


@router.post("/delegation/preview", response_model=DelegationPreview)
def preview_delegation(
    account_id: uuid.UUID,
    body: delegation.DelegationChange,
    ctx: WorkspaceContext = Depends(require_membership("agent.delegation.manage")),
    db: Session = Depends(get_db),
) -> DelegationPreview:
    return DelegationPreview.model_validate(delegation.preview(db, ctx, account_id, body))


@router.post("/delegation/apply", response_model=DelegationOut)
def apply_delegation(
    account_id: uuid.UUID,
    body: delegation.DelegationChange,
    ctx: WorkspaceContext = Depends(require_membership("agent.delegation.manage")),
    db: Session = Depends(get_db),
    clock: Clock = Depends(get_clock),
) -> DelegationOut:
    row = delegation.apply(db, clock, ctx, account_id, body)
    db.commit()
    account = scoped_account(db, ctx.workspace_id, account_id)
    return _delegation_out(row, account.config_version, account.controller_epoch)


@router.get("/delegation", response_model=DelegationOut | None)
def get_delegation(
    account_id: uuid.UUID,
    ctx: WorkspaceContext = Depends(require_membership("approvals.view")),
    db: Session = Depends(get_db),
) -> DelegationOut | None:
    try:
        account = scoped_account(db, ctx.workspace_id, account_id)
    except AgentScopeError as exc:
        raise AppError("NOT_FOUND") from exc
    row = delegation.current_delegation(db, ctx.workspace_id, account_id)
    return _delegation_out(row, account.config_version, account.controller_epoch) if row else None


def _delegation_out(row: AgentDelegation, config_version: int, epoch: int) -> DelegationOut:
    return DelegationOut(
        id=row.id,
        version=row.version,
        policy=delegation.DelegationPolicy.model_validate(row.policy),
        config_version=config_version,
        controller_epoch=epoch,
    )


@router.post("/pause", response_model=StateOut)
def pause(
    account_id: uuid.UUID,
    body: StateChange,
    ctx: WorkspaceContext = Depends(require_membership("agent.control")),
    db: Session = Depends(get_db),
    clock: Clock = Depends(get_clock),
) -> StateOut:
    return _state_change(db, clock, ctx, account_id, body, "paused")


@router.post("/resume", response_model=StateOut)
def resume(
    account_id: uuid.UUID,
    body: StateChange,
    ctx: WorkspaceContext = Depends(require_membership("agent.control")),
    db: Session = Depends(get_db),
    clock: Clock = Depends(get_clock),
) -> StateOut:
    return _state_change(db, clock, ctx, account_id, body, "active")


def _state_change(
    db: Session,
    clock: Clock,
    ctx: WorkspaceContext,
    account_id: uuid.UUID,
    body: StateChange,
    target: str,
) -> StateOut:
    if ctx.actor.type != "user" or ctx.role != "owner":
        raise AppError("FORBIDDEN", permission="agent.control")
    try:
        account = scoped_account(db, ctx.workspace_id, account_id, lock=True)
    except AgentScopeError as exc:
        raise AppError("NOT_FOUND") from exc
    if account.config_version != body.expected_config_version:
        raise AppError("VERSION_CONFLICT")
    if account.controller_mode != "agent" or account.state not in (
        "active" if target == "paused" else "paused",
    ):
        raise AppError("CONFLICT_STATE", entity="account_agent", status=account.state)
    account.state = target
    account.controller_epoch += 1
    from app.agent.control import adopt_threads

    adopt_threads(db, clock, account)
    from app.agent.jobs import enqueue_cleanup

    enqueue_cleanup(db, clock, ctx.workspace_id, account_id, account.controller_epoch)
    account.config_version += 1
    account.updated_at = clock.now()
    audit.record(
        db,
        ctx,
        "agent.state_changed",
        "account_agent",
        account.id,
        {"state": target, "controller_epoch": account.controller_epoch},
        clock=clock,
    )
    db.commit()
    return StateOut(
        state=account.state,
        controller_mode=account.controller_mode,
        config_version=account.config_version,
        controller_epoch=account.controller_epoch,
    )


class OverviewAction(BaseModel):
    id: uuid.UUID
    action_type: str
    status: str
    operation_id: uuid.UUID | None
    created_at: datetime


class AgentOverview(BaseModel):
    state: str
    controller_mode: str
    config_version: int
    controller_epoch: int
    is_simulated: bool
    session_counts: dict[str, int]
    pending_questions: int
    pending_approvals: int
    recent_actions: list[OverviewAction]


@router.get("", response_model=AgentOverview)
def get_overview(
    account_id: uuid.UUID,
    ctx: WorkspaceContext = Depends(require_membership()),
    db: Session = Depends(get_db),
) -> AgentOverview:
    """Bounded, body-free operational projection; detail domains retain their own access."""
    from app.integrations.instagram.queries import get_account
    from app.owner_requests.models import OwnerQuestion

    try:
        account = scoped_account(db, ctx.workspace_id, account_id)
    except AgentScopeError as exc:
        raise AppError("NOT_FOUND") from exc
    social = get_account(db, ctx, account_id)
    if social is None:
        raise AppError("NOT_FOUND")
    counts = db.execute(
        select(AgentSession.status, func.count(AgentSession.id))
        .join(
            AgentThread,
            (AgentThread.id == AgentSession.thread_id)
            & (AgentThread.workspace_id == AgentSession.workspace_id),
        )
        .where(
            AgentThread.workspace_id == ctx.workspace_id,
            AgentThread.social_account_id == account_id,
        )
        .group_by(AgentSession.status)
    ).all()
    scope = (
        AgentAction.workspace_id == ctx.workspace_id,
        AgentAction.social_account_id == account_id,
    )
    actions = db.scalars(
        select(AgentAction)
        .where(*scope)
        .order_by(AgentAction.created_at.desc(), AgentAction.id.desc())
        .limit(10)
    ).all()
    questions = (
        db.scalar(
            select(func.count(OwnerQuestion.id)).where(
                OwnerQuestion.workspace_id == ctx.workspace_id,
                OwnerQuestion.social_account_id == account_id,
                OwnerQuestion.state == "pending",
            )
        )
        or 0
    )
    approvals = (
        db.scalar(
            select(func.count(AgentAction.id)).where(
                *scope, AgentAction.status == "waiting_approval"
            )
        )
        or 0
    )
    return AgentOverview(
        state=account.state,
        controller_mode=account.controller_mode,
        config_version=account.config_version,
        controller_epoch=account.controller_epoch,
        is_simulated=social.provider_kind == "mock",
        session_counts=dict(counts),
        pending_questions=questions,
        pending_approvals=approvals,
        recent_actions=[
            OverviewAction(
                id=a.id,
                action_type=a.action_type,
                status=a.status,
                operation_id=a.operation_id,
                created_at=a.created_at,
            )
            for a in actions
        ],
    )
