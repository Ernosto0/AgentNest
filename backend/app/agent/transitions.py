"""Compare-and-swap transitions for durable agent state.

These functions never commit. Callers own the short transaction and must commit before
running a model, tool or provider operation.
"""

import uuid

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.agent.models import AgentAction, AgentSession, AgentStep, AgentThread
from app.audit.service import record
from app.core.clock import Clock


class StaleAgentState(ValueError):
    """The expected version/state/claim is no longer current."""


_SESSION_NEXT = {
    "queued": {"running", "cancelled", "failed"},
    "running": {
        "queued",
        "waiting_customer",
        "waiting_owner",
        "waiting_approval",
        "waiting_operation",
        "sleeping",
        "completed",
        "cancelled",
        "failed",
    },
    "waiting_customer": {"queued", "cancelled", "failed"},
    "waiting_owner": {"queued", "cancelled", "failed"},
    "waiting_approval": {"queued", "waiting_operation", "cancelled", "failed"},
    "waiting_operation": {"queued", "cancelled", "failed"},
    "sleeping": {"queued", "cancelled", "failed"},
}
_STEP_NEXT = {
    "claimed": {"model_pending", "abandoned", "stale", "failed"},
    "model_pending": {"model_done", "stale", "abandoned", "failed"},
    "model_done": {"dispatched", "stale", "failed"},
    "dispatched": {"consumed", "stale", "failed"},
}
_ACTION_NEXT = {
    "proposed": {"waiting_approval", "authorized", "cancelled"},
    "waiting_approval": {"authorized", "cancelled"},
    "authorized": {"queued", "in_progress", "cancelled"},
    "queued": {"in_progress", "cancelled"},
    "in_progress": {"succeeded", "failed", "outcome_unknown"},
    "outcome_unknown": {"succeeded", "failed"},
}


def transition_session(
    session: Session,
    *,
    workspace_id: uuid.UUID,
    session_id: uuid.UUID,
    expected_status: str,
    expected_version: int,
    next_status: str,
    clock: Clock,
    wake_kind: str | None = None,
    wake_ref: str | None = None,
) -> int:
    if next_status not in _SESSION_NEXT.get(expected_status, set()):
        raise ValueError("invalid agent session transition")
    now = clock.now()
    result = session.execute(
        update(AgentSession)
        .where(
            AgentSession.id == session_id,
            AgentSession.workspace_id == workspace_id,
            AgentSession.status == expected_status,
            AgentSession.version == expected_version,
        )
        .values(
            status=next_status,
            version=expected_version + 1,
            updated_at=now,
            wake_kind=wake_kind,
            wake_ref=wake_ref,
            completed_at=now if next_status in {"completed", "cancelled", "failed"} else None,
        )
        .returning(AgentSession.version)
        .execution_options(synchronize_session=False)
    ).scalar_one_or_none()
    if result is None:
        raise StaleAgentState("agent session changed")
    record(
        session,
        None,
        "agent.session_transition",
        "agent_session",
        session_id,
        {"from": expected_status, "to": next_status, "version": result},
        workspace_id=workspace_id,
        clock=clock,
    )
    return result


def transition_thread(
    session: Session,
    *,
    workspace_id: uuid.UUID,
    thread_id: uuid.UUID,
    expected_version: int,
    expected_status: str,
    next_status: str,
    clock: Clock,
) -> int:
    if next_status not in _SESSION_NEXT.get(expected_status, set()):
        raise ValueError("invalid agent thread transition")
    now = clock.now()
    version = session.execute(
        update(AgentThread)
        .where(
            AgentThread.id == thread_id,
            AgentThread.workspace_id == workspace_id,
            AgentThread.thread_version == expected_version,
            AgentThread.state == expected_status,
        )
        .values(state=next_status, thread_version=expected_version + 1, updated_at=now)
        .returning(AgentThread.thread_version)
        .execution_options(synchronize_session=False)
    ).scalar_one_or_none()
    if version is None:
        raise StaleAgentState("agent thread changed")
    record(
        session,
        None,
        "agent.thread_transition",
        "agent_thread",
        thread_id,
        {"from": expected_status, "to": next_status, "version": version},
        workspace_id=workspace_id,
        clock=clock,
    )
    return version


def transition_step(
    session: Session,
    *,
    workspace_id: uuid.UUID,
    step_id: uuid.UUID,
    claim_token: uuid.UUID,
    expected_status: str,
    next_status: str,
    clock: Clock,
) -> None:
    if next_status not in _STEP_NEXT.get(expected_status, set()):
        raise ValueError("invalid agent step transition")
    changed = session.execute(
        update(AgentStep)
        .where(
            AgentStep.id == step_id,
            AgentStep.workspace_id == workspace_id,
            AgentStep.claim_token == claim_token,
            AgentStep.status == expected_status,
        )
        .values(status=next_status, updated_at=clock.now())
        .returning(AgentStep.id)
        .execution_options(synchronize_session=False)
    ).scalar_one_or_none()
    if changed is None:
        raise StaleAgentState("agent step changed or claim lost")
    record(
        session,
        None,
        "agent.step_transition",
        "agent_step",
        step_id,
        {"from": expected_status, "to": next_status},
        workspace_id=workspace_id,
        clock=clock,
    )


def transition_action(
    session: Session,
    *,
    workspace_id: uuid.UUID,
    action_id: uuid.UUID,
    expected_status: str,
    expected_version: int,
    next_status: str,
    clock: Clock,
) -> None:
    if next_status not in _ACTION_NEXT.get(expected_status, set()):
        raise ValueError("invalid agent action transition")
    changed = session.execute(
        update(AgentAction)
        .where(
            AgentAction.id == action_id,
            AgentAction.workspace_id == workspace_id,
            AgentAction.status == expected_status,
            AgentAction.version == expected_version,
        )
        .values(status=next_status, updated_at=clock.now())
        .returning(AgentAction.id)
        .execution_options(synchronize_session=False)
    ).scalar_one_or_none()
    if changed is None:
        raise StaleAgentState("agent action changed")
    record(
        session,
        None,
        "agent.action_transition",
        "agent_action",
        action_id,
        {"from": expected_status, "to": next_status},
        workspace_id=workspace_id,
        clock=clock,
    )
