"""Shared pause/resume transaction, used by HTTP and confirmed owner commands."""

import uuid

from sqlalchemy.orm import Session

from app.agent.models import AccountAgent
from app.agent.repository import AgentScopeError, scoped_account
from app.audit import service as audit
from app.core.clock import Clock
from app.core.context import WorkspaceContext
from app.core.errors import AppError


def change_state(
    db: Session,
    clock: Clock,
    ctx: WorkspaceContext,
    account_id: uuid.UUID,
    expected_config_version: int,
    target: str,
    *,
    repause: bool = False,
) -> AccountAgent:
    """``repause`` lets a confirmed "pause until" command replace the timer of a pause that is
    already in force; the HTTP endpoint keeps refusing a second pause."""
    if ctx.actor.type != "user" or ctx.role != "owner":
        raise AppError("FORBIDDEN", permission="agent.control")
    try:
        account = scoped_account(db, ctx.workspace_id, account_id, lock=True)
    except AgentScopeError as exc:
        raise AppError("NOT_FOUND") from exc
    if account.config_version != expected_config_version:
        raise AppError("VERSION_CONFLICT")
    allowed = (
        ("paused",) if target == "active" else ("active", "paused") if repause else ("active",)
    )
    if account.controller_mode != "agent" or account.state not in allowed:
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
    return account
