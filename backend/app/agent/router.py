"""Owner account-agent delegation controls."""

import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.agent import delegation
from app.agent.models import AgentDelegation
from app.agent.repository import AgentScopeError, scoped_account
from app.api.deps import get_clock, require_membership
from app.audit import service as audit
from app.core.clock import Clock
from app.core.context import WorkspaceContext
from app.core.db import get_db
from app.core.errors import AppError

router = APIRouter(prefix="/workspaces/{workspace_id}/accounts/{account_id}/agent", tags=["agent"])


class DelegationPreview(BaseModel):
    next_version: int
    changed_actions: list[str]


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
