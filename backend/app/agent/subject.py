"""Exact-action approval callback for account-agent effects."""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent import delegation
from app.agent.models import AgentAction
from app.approvals import callbacks
from app.approvals.models import Approval
from app.core.clock import Clock
from app.core.context import WorkspaceContext
from app.core.errors import AppError


def _action(session: Session, ctx: WorkspaceContext, action_id: uuid.UUID) -> AgentAction | None:
    return session.scalar(
        select(AgentAction)
        .where(
            AgentAction.workspace_id == ctx.workspace_id,
            AgentAction.id == action_id,
        )
        .with_for_update()
    )


def on_decided(session: Session, clock: Clock, ctx: WorkspaceContext, approval: Approval) -> None:
    action = _action(session, ctx, approval.subject_id)
    if action is None:
        raise AppError("NOT_FOUND")
    if action.status != "waiting_approval" or action.version != approval.subject_version:
        if approval.status == "expired":
            return
        raise AppError("APPROVAL_STALE")
    if (
        action.approval_id != approval.id
        or approval.summary.get("payload_hash") != action.payload_hash
        or approval.payload_hash != action.payload_hash
    ):
        raise AppError("APPROVAL_STALE")
    if approval.status == "approved":
        # This also verifies revocation, pause, takeover and grantor membership. Do not
        # dispatch here: the coordinator must project the exact domain subject first.
        delegation.fence_action(
            session, clock, ctx.workspace_id, action.id, allow_waiting_approval=True
        )
        action.status = "authorized"
        action.authorized_at = clock.now()
    elif approval.status in ("rejected", "expired"):
        action.status = "cancelled"
    else:
        return


def current_version(session: Session, ctx: WorkspaceContext, action_id: uuid.UUID) -> int | None:
    action = _action(session, ctx, action_id)
    return (
        action.version
        if action is not None
        and action.status == "waiting_approval"
        and delegation.current_action_authority(session, action)
        else None
    )


def status_of(session: Session, ctx: WorkspaceContext, action_id: uuid.UUID) -> str | None:
    action = _action(session, ctx, action_id)
    return action.status if action is not None else None


callbacks.register(
    "agent_action",
    on_decided,
    current_version=current_version,
    status_of=status_of,
)
