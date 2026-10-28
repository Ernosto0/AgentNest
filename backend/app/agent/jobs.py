"""Durable routing, timers, recovery and stale approval cleanup."""

import uuid

from pydantic import BaseModel
from sqlalchemy import String, cast, or_, select
from sqlalchemy.orm import Session

from app.agent.models import ACTIVE_RUN_STATES, AgentSession, AgentStep, AgentThread
from app.ai.runner import RunnerDeps
from app.core.clock import Clock
from app.jobs.queue import enqueue
from app.jobs.registry import JobContext, job_handler
from app.jobs.scheduler import register_periodic


class AgentWakePayload(BaseModel):
    thread_id: uuid.UUID


class AgentSessionPayload(BaseModel):
    session_id: uuid.UUID


class AgentContinuePayload(AgentSessionPayload):
    step_id: uuid.UUID


class AgentRecoverPayload(BaseModel):
    pass


class AgentCleanupPayload(BaseModel):
    account_id: uuid.UUID


def deps_for(ctx: JobContext) -> "RunnerDeps":
    from app.ai.runner import RunnerDeps
    from app.core.config import get_settings
    from app.integrations.llm import build_provider

    settings = get_settings()
    return RunnerDeps(ctx.session_factory, ctx.clock, build_provider(settings), settings)


def dead_wake(ctx: JobContext, code: str) -> None:
    from app.agent.coordinator import set_state
    from app.agent.repository import scoped_account, scoped_thread

    payload = AgentWakePayload.model_validate(ctx.payload)
    deps = deps_for(ctx)
    with ctx.session_factory() as db:
        ref = db.get(AgentThread, payload.thread_id)
        if ref is None or ref.workspace_id != ctx.workspace_id:
            return
        scoped_account(db, ref.workspace_id, ref.social_account_id, lock=True)
        thread = scoped_thread(db, ref.workspace_id, ref.social_account_id, ref.id, lock=True)
        goal = db.scalar(
            select(AgentSession).where(
                AgentSession.thread_id == thread.id, AgentSession.status.in_(ACTIVE_RUN_STATES)
            )
        )
        if goal is not None:
            set_state(db, deps, goal, thread, "failed", reason=code)
        db.commit()


@job_handler("agent_wake", AgentWakePayload, timeout=150, on_dead=dead_wake)
def agent_wake(ctx: JobContext) -> None:
    from app.agent.coordinator import run_activation
    from app.agent.tools.broker import build_default_broker

    payload = AgentWakePayload.model_validate(ctx.payload)
    if ctx.workspace_id is not None:
        run_activation(
            deps_for(ctx),
            ctx.workspace_id,
            payload.thread_id,
            build_default_broker(),
            job_id=ctx.job_id,
        )


@job_handler("agent_continue", AgentContinuePayload)
def agent_continue(ctx: JobContext) -> None:
    payload = AgentContinuePayload.model_validate(ctx.payload)
    with ctx.session_factory() as db:
        goal = db.get(AgentSession, payload.session_id)
        step = db.get(AgentStep, payload.step_id)
        if (
            goal is None
            or step is None
            or goal.workspace_id != ctx.workspace_id
            or step.session_id != goal.id
        ):
            return
        wake(db, ctx.clock, goal.workspace_id, goal.thread_id, f"continue:{step.id}")
        db.commit()


def wake(
    db: Session, clock: Clock, workspace_id: uuid.UUID, thread_id: uuid.UUID, key: str
) -> None:
    enqueue(
        db,
        "agent_wake",
        AgentWakePayload(thread_id=thread_id),
        workspace_id=workspace_id,
        correlation_id=None,
        dedup_key=f"agent_wake:{thread_id}:{key}",
        clock=clock,
    )


@job_handler("agent_wake_due", AgentSessionPayload)
def agent_wake_due(ctx: JobContext) -> None:
    payload = AgentSessionPayload.model_validate(ctx.payload)
    with ctx.session_factory() as db:
        goal = db.get(AgentSession, payload.session_id)
        if (
            goal is None
            or goal.workspace_id != ctx.workspace_id
            or goal.status not in ACTIVE_RUN_STATES
        ):
            return
        if goal.wake_at is None or goal.wake_at > ctx.clock.now():
            return
        wake(db, ctx.clock, goal.workspace_id, goal.thread_id, f"due:{goal.version}")
        db.commit()


def enqueue_cleanup(
    db: Session, clock: Clock, workspace_id: uuid.UUID, account_id: uuid.UUID, epoch: int | str
) -> None:
    enqueue(
        db,
        "agent_cleanup_approvals",
        AgentCleanupPayload(account_id=account_id),
        workspace_id=workspace_id,
        correlation_id=None,
        dedup_key=f"agent_cleanup:{account_id}:{epoch}",
        clock=clock,
    )


@job_handler("agent_cleanup_approvals", AgentCleanupPayload)
def cleanup_approvals(ctx: JobContext) -> None:
    from app.agent.delegation import current_action_authority
    from app.agent.models import AgentAction
    from app.approvals.models import Approval
    from app.audit.service import record

    payload = AgentCleanupPayload.model_validate(ctx.payload)
    from app.agent.control import retire_stale_drafts

    if ctx.workspace_id is not None:
        retire_stale_drafts(ctx.session_factory, ctx.clock, ctx.workspace_id, payload.account_id)
    # First find IDs without locks. Then exactly the approval-service ordering:
    # approval -> account -> action -> thread. Never hold an account lock while
    # waiting for an approval; policy transactions only enqueue this job.
    with ctx.session_factory() as db:
        ids = db.scalars(
            select(Approval.id)
            .join(AgentAction, AgentAction.approval_id == Approval.id)
            .where(
                Approval.workspace_id == ctx.workspace_id,
                Approval.status == "pending",
                AgentAction.workspace_id == ctx.workspace_id,
                AgentAction.social_account_id == payload.account_id,
            )
        ).all()
    for approval_id in ids:
        with ctx.session_factory() as db:
            approval = db.scalar(
                select(Approval)
                .where(Approval.id == approval_id, Approval.workspace_id == ctx.workspace_id)
                .with_for_update()
            )
            if approval is None or approval.status != "pending":
                continue
            candidate = db.scalar(
                select(AgentAction).where(
                    AgentAction.approval_id == approval.id,
                    AgentAction.workspace_id == ctx.workspace_id,
                )
            )
            if candidate is None:
                continue
            from app.agent.repository import scoped_account

            scoped_account(db, candidate.workspace_id, candidate.social_account_id, lock=True)
            action = db.scalar(
                select(AgentAction)
                .where(
                    AgentAction.approval_id == approval.id,
                    AgentAction.workspace_id == ctx.workspace_id,
                )
                .with_for_update()
            )
            if action is None:
                continue
            from app.agent.repository import scoped_account

            scoped_account(db, action.workspace_id, action.social_account_id, lock=True)
            if not current_action_authority(db, action):
                approval.status = "cancelled"
                if action.status == "waiting_approval":
                    action.status = "cancelled"
                    action.outcome_code = "APPROVAL_STALE"
                record(
                    db,
                    None,
                    "agent.action_transition",
                    "agent_action",
                    action.id,
                    {"to": "cancelled", "reason": "APPROVAL_STALE"},
                    workspace_id=action.workspace_id,
                    clock=ctx.clock,
                )
            db.commit()


@job_handler("agent_recover", AgentRecoverPayload)
def agent_recover(ctx: JobContext) -> None:
    from app.agent.models import AgentAction
    from app.approvals.models import Approval
    from app.operations.models import Operation
    from app.owner_requests.models import OwnerQuestion
    from app.owner_requests.service import recover_questions

    recover_questions(ctx.session_factory, ctx.clock)
    resolved_owner = select(OwnerQuestion.session_id).where(
        OwnerQuestion.state != "pending",
        cast(OwnerQuestion.id, String) == AgentSession.wake_ref,
    )

    resolved_approvals = (
        select(AgentAction.session_id)
        .join(Approval, Approval.id == AgentAction.approval_id)
        .where(Approval.status != "pending")
    )
    resolved_operations = (
        select(AgentAction.session_id)
        .join(Operation, Operation.id == AgentAction.operation_id)
        .where(Operation.status.in_(("succeeded", "failed")))
    )
    with ctx.session_factory() as db:
        goals = db.scalars(
            select(AgentSession)
            .where(
                AgentSession.status.in_(ACTIVE_RUN_STATES),
                or_(
                    AgentSession.status.in_(("queued", "running")),
                    AgentSession.status == "waiting_operation",
                    (
                        (AgentSession.status == "waiting_owner")
                        & AgentSession.id.in_(resolved_owner)
                    ),
                    (
                        (AgentSession.status == "waiting_approval")
                        & AgentSession.id.in_(resolved_approvals)
                    ),
                    (
                        (AgentSession.status == "waiting_operation")
                        & AgentSession.id.in_(resolved_operations)
                    ),
                    (AgentSession.wake_at.is_not(None) & (AgentSession.wake_at <= ctx.clock.now())),
                ),
            )
            .order_by(AgentSession.updated_at)
            .limit(200)
        ).all()
        for goal in goals:
            goal.updated_at = ctx.clock.now()
            if goal.status in {
                "queued",
                "running",
                "waiting_owner",
                "waiting_approval",
                "waiting_operation",
            }:
                # Unique recovery tick keys cannot be swallowed by a running wake's finalization.
                wake(
                    db,
                    ctx.clock,
                    goal.workspace_id,
                    goal.thread_id,
                    f"recover:{ctx.clock.now():%Y%m%d%H%M}",
                )
            elif goal.wake_at is not None and goal.wake_at <= ctx.clock.now():
                enqueue(
                    db,
                    "agent_wake_due",
                    AgentSessionPayload(session_id=goal.id),
                    workspace_id=goal.workspace_id,
                    correlation_id=None,
                    dedup_key=f"agent_due:{goal.id}:{goal.version}",
                    clock=ctx.clock,
                )
        db.commit()


@register_periodic
def enqueue_recovery(db: Session, clock: Clock) -> int:
    enqueue(
        db,
        "agent_recover",
        AgentRecoverPayload(),
        workspace_id=None,
        correlation_id=None,
        dedup_key=f"agent_recover:{clock.now():%Y%m%d%H%M}",
        clock=clock,
    )
    return 1
