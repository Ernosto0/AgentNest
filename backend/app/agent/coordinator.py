"""Durable, bounded coordinator. Domain bodies never enter generic evidence."""

import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import cast

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent import transitions
from app.agent.delegation import current_delegation
from app.agent.models import (
    ACTIVE_RUN_STATES,
    AccountAgent,
    AgentAction,
    AgentSession,
    AgentStep,
    AgentThread,
)
from app.agent.repository import scoped_account, scoped_thread
from app.agent.tools.broker import BrokerContext, Surface, ToolBroker
from app.ai.models import AgentRun
from app.ai.runner import RunnerDeps
from app.ai.step_runner import run_step
from app.core.context import ActorRef, WorkspaceContext
from app.core.errors import RetryableError
from app.identity.models import Workspace
from app.integrations.llm.steps import LLMStepRequest, LLMStepResult, LLMToolObservation

LEASE = timedelta(seconds=90)
TOKEN_RESERVATION = 40000  # includes bounded context and one repair
GOAL_TOKEN_LIMIT = 960000
PUBLIC_ACTIONS = ("comment.reply", "comment.hide", "comment.unhide", "comment.delete")


def effect_result(db: Session, action: "AgentAction") -> dict[str, object]:
    if action.action_type in PUBLIC_ACTIONS:
        from app.comments.actions import result

        return result(db, action)
    from app.agent.dm import action_result

    return action_result(db, action)


@dataclass(frozen=True)
class Claim:
    step_id: uuid.UUID
    token: uuid.UUID
    context: BrokerContext


def set_state(
    db: Session,
    deps: RunnerDeps,
    goal: AgentSession,
    thread: AgentThread,
    state: str,
    *,
    reason: str | None = None,
    wake_kind: str | None = None,
    wake_ref: str | None = None,
) -> None:
    db.flush()
    if state in {"completed", "failed", "cancelled"}:
        thread.current_goal_key = f"event:{thread.event_cursor}"
    if goal.status != state:
        transitions.transition_session(
            db,
            workspace_id=goal.workspace_id,
            session_id=goal.id,
            expected_status=goal.status,
            expected_version=goal.version,
            next_status=state,
            clock=deps.clock,
            wake_kind=wake_kind,
            wake_ref=wake_ref,
        )
        db.refresh(goal)
    if thread.state != state:
        # A terminal thread becomes queued only with a new durable goal.
        if thread.state in {"completed", "failed", "cancelled"}:
            thread.state = "queued"
            thread.thread_version += 1
            db.flush()
        transitions.transition_thread(
            db,
            workspace_id=thread.workspace_id,
            thread_id=thread.id,
            expected_version=thread.thread_version,
            expected_status=thread.state,
            next_status=state,
            clock=deps.clock,
        )
        db.refresh(thread)
    goal.outcome_code = reason


def step_state(db: Session, deps: RunnerDeps, step: AgentStep, state: str) -> None:
    db.flush()
    transitions.transition_step(
        db,
        workspace_id=step.workspace_id,
        step_id=step.id,
        claim_token=step.claim_token,
        expected_status=step.status,
        next_status=state,
        clock=deps.clock,
    )
    db.refresh(step)


def claim(deps: RunnerDeps, workspace_id: uuid.UUID, thread_id: uuid.UUID) -> Claim | None:
    with deps.session_factory() as db:
        ref = db.get(AgentThread, thread_id)
        if ref is None or ref.workspace_id != workspace_id:
            return None
        account = scoped_account(db, workspace_id, ref.social_account_id, lock=True)
        thread = scoped_thread(db, workspace_id, ref.social_account_id, thread_id, lock=True)
        if not enabled(account, thread):
            return None
        goal = db.scalar(
            select(AgentSession)
            .where(
                AgentSession.workspace_id == workspace_id,
                AgentSession.thread_id == thread_id,
                AgentSession.status.in_(ACTIVE_RUN_STATES),
            )
            .with_for_update()
        )
        if goal is None:
            if thread.current_goal_key == f"event:{thread.event_cursor}":
                return None
            goal = AgentSession(
                workspace_id=workspace_id,
                thread_id=thread_id,
                goal_key=f"event:{thread.event_cursor}",
                initiating_event_cursor=thread.event_cursor,
            )
            db.add(goal)
            db.flush()
            thread.current_goal_key = goal.goal_key
        sync_usage(db, goal)
        latest = db.scalar(
            select(AgentStep)
            .where(AgentStep.session_id == goal.id)
            .order_by(AgentStep.sequence.desc())
            .limit(1)
        )
        if latest is not None and latest.status in {
            "claimed",
            "model_pending",
            "model_done",
            "dispatched",
        }:
            if latest.lease_expires_at is not None and latest.lease_expires_at > deps.clock.now():
                return None
            step_state(
                db,
                deps,
                latest,
                "abandoned" if latest.status in {"claimed", "model_pending"} else "stale",
            )
        if goal.status.startswith("waiting_") or goal.status == "sleeping":
            if not wait_resolved(db, deps, goal, thread):
                db.commit()
                return None
            if goal.wake_at is not None and goal.wake_at <= deps.clock.now():
                goal.activation_started_at = None
                goal.wake_at = None
            goal.activation_started_at = None
            set_state(db, deps, goal, thread, "queued")
        if goal.activation_started_at is None or thread.event_cursor > goal.activation_cursor:
            goal.activation_cursor = thread.event_cursor
            goal.activation_started_at = deps.clock.now()
            goal.activation_steps = 0
            goal.activation_tools = 0
            goal.validation_failures = 0
        if (
            goal.model_steps >= 24
            or goal.activation_steps >= 8
            or goal.reserved_tokens + TOKEN_RESERVATION > GOAL_TOKEN_LIMIT
            or deps.clock.now() - goal.activation_started_at >= timedelta(seconds=120)
        ):
            set_state(db, deps, goal, thread, "failed", reason="AGENT_BUDGET_EXCEEDED")
            db.commit()
            return None
        if goal.status != "running":
            set_state(db, deps, goal, thread, "running")
        policy = current_delegation(db, workspace_id, thread.social_account_id)
        from app.comments.service import media_version

        step = AgentStep(
            workspace_id=workspace_id,
            session_id=goal.id,
            sequence=1 if latest is None else latest.sequence + 1,
            claim_token=uuid.uuid4(),
            lease_expires_at=deps.clock.now() + LEASE,
            captured_cursor=thread.event_cursor,
            captured_public_version=media_version(db, thread),
            captured_epoch=account.controller_epoch,
            captured_ownership_generation=thread.ownership_generation,
            captured_policy_version=policy.version if policy else None,
            captured_persona_version=account.persona_version,
            captured_deletion_generation=thread.deletion_generation,
            status="model_pending",
            reserved_tokens=TOKEN_RESERVATION,
            prompt_version="v1",
            tool_version="v1",
        )
        db.add(step)
        goal.model_steps += 1
        goal.activation_steps += 1
        goal.reserved_tokens += TOKEN_RESERVATION
        workspace = db.get(Workspace, workspace_id)
        if workspace is None:
            raise ValueError("workspace missing")
        from app.memory.service import resolve_identity

        identity = resolve_identity(db, deps.clock, thread)
        context = BrokerContext(
            WorkspaceContext(
                workspace_id,
                ActorRef.system("account_agent"),
                None,
                workspace.timezone,
                workspace.default_locale,
                False,
            ),
            thread.social_account_id,
            thread_id,
            cast(Surface, thread.surface),
            "owner_task" if thread.surface == "owner_task" else "customer",
            identity.generation if identity else None,
        )
        db.commit()
        return Claim(step.id, step.claim_token, context)


def enabled(account: AccountAgent, thread: AgentThread) -> bool:
    return (
        account.state == "active"
        and account.controller_mode == "agent"
        and thread.handling_mode == "agent"
        and thread.controller_epoch == account.controller_epoch
    )


def fresh(
    db: Session, deps: RunnerDeps, claimed: Claim
) -> tuple[AgentStep, AgentSession, AgentThread] | None:
    context = claimed.context
    account = scoped_account(db, context.workspace.workspace_id, context.account_id, lock=True)
    thread = scoped_thread(
        db, context.workspace.workspace_id, context.account_id, context.thread_id, lock=True
    )
    step = db.get(AgentStep, claimed.step_id)
    if step is None:
        return None
    goal = db.get(AgentSession, step.session_id)
    if goal is None:
        return None
    policy = current_delegation(db, thread.workspace_id, thread.social_account_id)
    from app.comments.service import media_version

    if (
        step.claim_token != claimed.token
        or step.status != "model_pending"
        or step.lease_expires_at is None
        or step.lease_expires_at <= deps.clock.now()
        or not enabled(account, thread)
        or step.captured_cursor != thread.event_cursor
        or step.captured_public_version != media_version(db, thread)
        or step.captured_epoch != account.controller_epoch
        or step.captured_ownership_generation != thread.ownership_generation
        or (
            goal.activation_started_at is not None
            and deps.clock.now() - goal.activation_started_at >= timedelta(seconds=120)
        )
        or step.captured_deletion_generation != thread.deletion_generation
        or step.captured_policy_version != (policy.version if policy else None)
        or step.captured_persona_version != account.persona_version
    ):
        if step.status == "model_pending":
            step_state(db, deps, step, "stale")
        return None
    return step, goal, thread


def run_activation(
    deps: RunnerDeps,
    workspace_id: uuid.UUID,
    thread_id: uuid.UUID,
    broker: ToolBroker,
    *,
    job_id: uuid.UUID | None = None,
) -> None:
    observations: tuple[LLMToolObservation, ...] = ()
    observation_generation: tuple[int | None, int, int | None] | None = None
    while (claimed := claim(deps, workspace_id, thread_id)) is not None:
        with deps.session_factory() as db:
            observation_step = db.get(AgentStep, claimed.step_id)
            if observation_step is None:
                return
            current_generation = (
                claimed.context.memory_generation,
                observation_step.captured_cursor,
                observation_step.captured_public_version,
            )
        if observation_generation != current_generation:
            observations = ()
        observation_generation = current_generation
        with deps.session_factory() as db:
            from app.agent.models import AgentAction

            latest_action = db.scalar(
                select(AgentAction)
                .where(
                    AgentAction.thread_id == claimed.context.thread_id,
                    AgentAction.action_type.in_(("dm.send", *PUBLIC_ACTIONS)),
                )
                .order_by(AgentAction.created_at.desc())
                .limit(1)
            )
            if latest_action is not None:
                observations = (
                    LLMToolObservation(
                        str(latest_action.id),
                        latest_action.action_type,
                        {},
                        effect_result(db, latest_action),
                    ),
                )
                db.commit()
            current = db.get(AgentStep, claimed.step_id)
            previous = (
                db.scalar(
                    select(AgentStep)
                    .where(
                        AgentStep.session_id == current.session_id,
                        AgentStep.sequence < current.sequence,
                        AgentStep.status == "consumed",
                    )
                    .order_by(AgentStep.sequence.desc())
                    .limit(1)
                )
                if current
                else None
            )
            if previous is not None and previous.read_checkpoint and latest_action is None:
                checkpoint = previous.read_checkpoint
                tool = broker.dispatch(
                    db,
                    deps.clock,
                    claimed.context,
                    name=checkpoint["name"],
                    version="v1",
                    arguments=checkpoint["arguments"],
                )
                observations = (
                    LLMToolObservation(
                        str(previous.id),
                        checkpoint["name"],
                        checkpoint["arguments"],
                        tool.observation(),
                    ),
                )
            from app.agent.context import assemble

            model_context = assemble(db, deps.clock, claimed.context)
            db.commit()
        if model_context.language is None:
            with deps.session_factory() as db:
                state = fresh(db, deps, claimed)
                if state is not None:
                    step, goal, thread = state
                    step_state(db, deps, step, "failed")
                    set_state(db, deps, goal, thread, "failed", reason="AGENT_UNSUPPORTED_LANGUAGE")
                db.commit()
            return
        request = LLMStepRequest(
            task="account_agent_step",
            model="fake",
            system=model_context.system,
            messages=model_context.messages,
            tools=broker.available(claimed.context),
            observations=observations,
        )
        encoded_request = json.dumps(
            {
                "system": request.system,
                "messages": [m.content for m in request.messages],
                "tools": [
                    {
                        "name": t.name,
                        "description": t.description,
                        "schema": t.arguments_schema.model_json_schema(),
                        "version": t.version,
                    }
                    for t in request.tools
                ],
                "observations": [
                    {
                        "call_id": o.call_id,
                        "name": o.name,
                        "arguments": o.arguments,
                        "result": o.result,
                    }
                    for o in request.observations
                ],
            },
            ensure_ascii=False,
        )
        if len(encoded_request.encode("utf-8")) > 16000:
            with deps.session_factory() as db:
                state = fresh(db, deps, claimed)
                if state is not None:
                    step, goal, thread = state
                    step_state(db, deps, step, "failed")
                    set_state(db, deps, goal, thread, "failed", reason="AGENT_CONTEXT_LIMIT")
                db.commit()
            return
        try:
            outcome = run_step(
                deps, claimed.context.workspace, claimed.step_id, request, job_id=job_id
            )
        except RetryableError:
            with deps.session_factory() as db:
                state = fresh(db, deps, claimed)
                if state is not None:
                    step, goal, thread = state
                    sync_usage(db, goal)
                    step_state(db, deps, step, "failed")
                    set_state(db, deps, goal, thread, "queued", reason="LLM_RETRY_PENDING")
                db.commit()
            raise
        except Exception:
            # Recovery waits for the durable claim to expire.
            raise
        with deps.session_factory() as db:
            scoped_account(db, workspace_id, claimed.context.account_id, lock=True)
            recorded_step = db.get(AgentStep, claimed.step_id)
            run = db.get(AgentRun, outcome.agent_run_id)
            if recorded_step is not None and run is not None:
                recorded_goal = db.get(AgentSession, recorded_step.session_id)
                if recorded_goal is not None:
                    recorded_goal.input_tokens += (
                        run.input_tokens or 0
                    ) - recorded_step.input_tokens
                    recorded_goal.output_tokens += (
                        run.output_tokens or 0
                    ) - recorded_step.output_tokens
                    recorded_step.input_tokens = run.input_tokens or 0
                    recorded_step.output_tokens = run.output_tokens or 0
                    db.flush()
            state = fresh(db, deps, claimed)
            if state is None:
                db.commit()
                return
            step, goal, thread = state
            if outcome.result is None:
                step_state(db, deps, step, "failed")
                set_state(db, deps, goal, thread, "failed", reason=outcome.error_code)
                db.commit()
                return
            result = outcome.result
            step_state(db, deps, step, "model_done")
            if result.kind == "tool":
                signature = hashlib.sha256(
                    json.dumps([result.tool_name, result.tool_arguments], sort_keys=True).encode()
                ).hexdigest()
                repeats = len(
                    db.scalars(
                        select(AgentStep.id).where(
                            AgentStep.session_id == goal.id, AgentStep.output_ref == signature
                        )
                    ).all()
                )
                if goal.activation_tools >= 12 or repeats >= 3:
                    step_state(db, deps, step, "failed")
                    set_state(db, deps, goal, thread, "failed", reason="AGENT_LOOP_LIMIT")
                    db.commit()
                    return
                step.output_ref = signature
                goal.tool_calls += 1
                goal.activation_tools += 1
                # Domain intents commit here; operations jobs own network effects.
                tool = broker.dispatch(
                    db,
                    deps.clock,
                    claimed.context,
                    name=result.tool_name or "",
                    version="v1",
                    arguments=result.tool_arguments,
                )
                if result.tool_name == "reply.validate" and (
                    not tool.ok or tool.data.get("valid") is False
                ):
                    goal.validation_failures += 1
                    if goal.validation_failures > 1:
                        step_state(db, deps, step, "failed")
                        set_state(
                            db, deps, goal, thread, "failed", reason="AGENT_GROUNDING_REJECTED"
                        )
                        db.commit()
                        return
                if tool.ok and result.tool_name in {
                    "knowledge.read",
                    "thread.read",
                    "public.thread",
                }:
                    # Store only validated routing metadata. A non-null fact cursor must
                    # be an existing scoped fact key, never arbitrary model text.
                    args = result.tool_arguments
                    cursor = args.get("cursor")
                    safe_cursor = cursor is None
                    if result.tool_name == "knowledge.read" and cursor is not None:
                        from app.knowledge.models import BusinessFact

                        safe_cursor = (
                            db.scalar(
                                select(BusinessFact.id)
                                .where(
                                    BusinessFact.workspace_id == workspace_id,
                                    BusinessFact.key == cursor,
                                )
                                .limit(1)
                            )
                            is not None
                        )
                    if result.tool_name == "public.thread" and cursor is not None:
                        from app.comments.models import PublicComment

                        try:
                            public_cursor = uuid.UUID(str(cursor))
                        except ValueError:
                            public_cursor = None
                        safe_cursor = (
                            db.scalar(
                                select(PublicComment.id)
                                .where(
                                    PublicComment.workspace_id == workspace_id,
                                    PublicComment.social_account_id == claimed.context.account_id,
                                    PublicComment.thread_id == thread.public_thread_id,
                                    PublicComment.id == public_cursor,
                                )
                                .limit(1)
                            )
                            is not None
                        )
                    if safe_cursor:
                        step.read_checkpoint = {"name": result.tool_name, "arguments": args}
                step_state(db, deps, step, "dispatched")
                step_state(db, deps, step, "consumed")
                if (
                    result.tool_name == "owner.ask"
                    and tool.ok
                    and tool.data.get("question_id")
                    and tool.data.get("state") == "pending"
                ):
                    set_state(
                        db,
                        deps,
                        goal,
                        thread,
                        "waiting_owner",
                        wake_kind="owner",
                        wake_ref=str(tool.data["question_id"]),
                    )
                    db.commit()
                    return
                if (
                    result.tool_name
                    in {"dm.send", "approval.request", "comment.reply", "comment.moderate"}
                    and tool.ok
                    and tool.data.get("status") == "waiting_customer"
                ):
                    set_state(
                        db,
                        deps,
                        goal,
                        thread,
                        "waiting_customer",
                        wake_kind="customer",
                        wake_ref=str(thread.id),
                    )
                    db.commit()
                    return
                if (
                    result.tool_name
                    in {"dm.send", "approval.request", "comment.reply", "comment.moderate"}
                    and tool.ok
                    and tool.data.get("action_id")
                ):
                    status = tool.data.get("status")
                    if status in {
                        "waiting_approval",
                        "authorized",
                        "queued",
                        "in_progress",
                        "outcome_unknown",
                    }:
                        set_state(
                            db,
                            deps,
                            goal,
                            thread,
                            "waiting_approval"
                            if status == "waiting_approval"
                            else "waiting_operation",
                            wake_kind="approval" if status == "waiting_approval" else "operation",
                            wake_ref=str(
                                tool.data.get("approval_id")
                                if status == "waiting_approval"
                                else tool.data["action_id"]
                            ),
                        )
                        db.commit()
                        return
                observations = (
                    LLMToolObservation(
                        result.call_id or str(step.id),
                        result.tool_name or "",
                        result.tool_arguments,
                        tool.observation(),
                    ),
                )
                db.commit()
                continue
            step_state(db, deps, step, "dispatched")
            step_state(db, deps, step, "consumed")
            if result.kind == "complete":
                outstanding = db.scalar(
                    select(AgentAction)
                    .where(
                        AgentAction.thread_id == thread.id,
                        AgentAction.action_type.in_(("dm.send", *PUBLIC_ACTIONS)),
                        AgentAction.status.in_(
                            (
                                "waiting_approval",
                                "authorized",
                                "queued",
                                "in_progress",
                                "outcome_unknown",
                            )
                        ),
                    )
                    .order_by(AgentAction.created_at.desc())
                    .limit(1)
                )
                if outstanding is not None:
                    effect_result(db, outstanding)
                if outstanding is not None and outstanding.status not in {
                    "succeeded",
                    "failed",
                    "cancelled",
                }:
                    awaiting_approval = outstanding.status == "waiting_approval"
                    set_state(
                        db,
                        deps,
                        goal,
                        thread,
                        "waiting_approval" if awaiting_approval else "waiting_operation",
                        wake_kind="approval" if awaiting_approval else "operation",
                        wake_ref=str(
                            outstanding.approval_id if awaiting_approval else outstanding.id
                        ),
                    )
                else:
                    set_state(db, deps, goal, thread, "completed")
            elif result.kind == "wait" and result.wait_for == "customer":
                set_state(
                    db,
                    deps,
                    goal,
                    thread,
                    "waiting_customer",
                    wake_kind="customer",
                    wake_ref=str(thread.id),
                )
            elif result.kind == "wait" and valid_wait(db, goal, thread, result):
                set_state(
                    db,
                    deps,
                    goal,
                    thread,
                    f"waiting_{result.wait_for}",
                    wake_kind=result.wait_for,
                    wake_ref=str(result.metadata["reference_id"]),
                )
            else:
                set_state(
                    db,
                    deps,
                    goal,
                    thread,
                    "failed",
                    reason="AGENT_HANDOFF" if result.kind == "handoff" else "AGENT_WAIT_INVALID",
                )
            db.commit()
            return


def valid_wait(db: Session, goal: AgentSession, thread: AgentThread, result: LLMStepResult) -> bool:
    from app.agent.models import AgentAction

    try:
        ref = uuid.UUID(str(result.metadata.get("reference_id")))
    except ValueError:
        return False
    if result.wait_for == "owner":
        from app.owner_requests.models import OwnerQuestion

        return (
            db.scalar(
                select(OwnerQuestion.id).where(
                    OwnerQuestion.id == ref,
                    OwnerQuestion.workspace_id == goal.workspace_id,
                    OwnerQuestion.thread_id == thread.id,
                    OwnerQuestion.session_id == goal.id,
                    OwnerQuestion.state == "pending",
                    OwnerQuestion.body.is_not(None),
                )
            )
            is not None
        )
    if result.wait_for == "operation":
        action = db.scalar(
            select(AgentAction).where(
                AgentAction.id == ref,
                AgentAction.workspace_id == goal.workspace_id,
                AgentAction.thread_id == thread.id,
                AgentAction.action_type.in_(("dm.send", *PUBLIC_ACTIONS)),
                AgentAction.status.in_(("authorized", "queued", "in_progress", "outcome_unknown")),
            )
        )
        if action is not None:
            return True
    if result.wait_for in {"approval", "operation"}:
        return (
            db.scalar(
                select(AgentAction.id).where(
                    AgentAction.workspace_id == goal.workspace_id,
                    AgentAction.session_id == goal.id,
                    AgentAction.thread_id == thread.id,
                    AgentAction.approval_id == ref
                    if result.wait_for == "approval"
                    else AgentAction.operation_id == ref,
                    AgentAction.status == "waiting_approval"
                    if result.wait_for == "approval"
                    else AgentAction.status.in_(("in_progress", "outcome_unknown")),
                )
            )
            is not None
        )
    return False


def wait_resolved(db: Session, deps: RunnerDeps, goal: AgentSession, thread: AgentThread) -> bool:
    from app.agent.models import AgentAction, AgentEvent
    from app.approvals.models import Approval
    from app.operations.models import Operation

    if goal.status == "sleeping":
        return goal.wake_at is not None and goal.wake_at <= deps.clock.now()
    if goal.status == "waiting_customer":
        return (
            db.scalar(
                select(AgentEvent.id)
                .where(
                    AgentEvent.thread_id == thread.id,
                    AgentEvent.cursor > goal.activation_cursor,
                    AgentEvent.source_kind.in_(("message", "customer_message", "inbound_message")),
                    AgentEvent.kind.not_in(("echo", "own_message", "outbound_message")),
                )
                .limit(1)
            )
            is not None
        )
    try:
        ref = uuid.UUID(goal.wake_ref or "")
    except ValueError:
        return False
    if goal.status == "waiting_owner":
        from app.owner_requests.models import OwnerQuestion

        question = db.scalar(
            select(OwnerQuestion).where(
                OwnerQuestion.id == ref,
                OwnerQuestion.workspace_id == goal.workspace_id,
                OwnerQuestion.thread_id == thread.id,
                OwnerQuestion.session_id == goal.id,
            )
        )
        return question is not None and (
            question.state != "pending"
            or question.expires_at <= deps.clock.now()
            or thread.event_cursor > goal.activation_cursor
        )
    if goal.status == "waiting_approval":
        approval = db.scalar(
            select(Approval)
            .join(AgentAction, AgentAction.approval_id == Approval.id)
            .where(
                Approval.id == ref,
                Approval.workspace_id == goal.workspace_id,
                AgentAction.session_id == goal.id,
            )
        )
        if approval is not None and approval.status == "approved":
            action = db.scalar(select(AgentAction).where(AgentAction.approval_id == approval.id))
            if action is not None and action.action_type in ("dm.send", *PUBLIC_ACTIONS):
                effect_result(db, action)
                if action.status not in {"succeeded", "failed", "cancelled"}:
                    set_state(
                        db,
                        deps,
                        goal,
                        thread,
                        "waiting_operation",
                        wake_kind="operation",
                        wake_ref=str(action.id),
                    )
                    return False
        return approval is not None and approval.status != "pending"
    if goal.status == "waiting_operation":
        action = db.scalar(
            select(AgentAction).where(
                AgentAction.id == ref,
                AgentAction.workspace_id == goal.workspace_id,
                AgentAction.thread_id == thread.id,
                AgentAction.action_type.in_(("dm.send", *PUBLIC_ACTIONS)),
            )
        )
        if action is not None:
            effect_result(db, action)
            return (
                action.status in {"succeeded", "failed", "cancelled"}
                or thread.event_cursor > goal.activation_cursor
            )
        operation = db.scalar(
            select(Operation)
            .join(AgentAction, AgentAction.operation_id == Operation.id)
            .where(
                Operation.id == ref,
                Operation.workspace_id == goal.workspace_id,
                AgentAction.session_id == goal.id,
            )
        )
        return operation is not None and operation.status in {"succeeded", "failed"}
    return False


def sleep_until(
    db: Session, deps: RunnerDeps, goal: AgentSession, thread: AgentThread, wake_at: datetime
) -> None:
    """Schedule a server-validated task; never trust a model timestamp as eligibility."""
    from app.agent.jobs import AgentSessionPayload
    from app.jobs.queue import enqueue

    if wake_at <= deps.clock.now():
        raise ValueError("wake must be in the future")
    set_state(db, deps, goal, thread, "sleeping", wake_kind="scheduled", wake_ref=str(goal.id))
    goal.wake_at = wake_at
    enqueue(
        db,
        "agent_wake_due",
        AgentSessionPayload(session_id=goal.id),
        workspace_id=goal.workspace_id,
        correlation_id=None,
        run_at=wake_at,
        dedup_key=f"agent_due:{goal.id}:{goal.version}",
        clock=deps.clock,
    )


def sync_usage(db: Session, goal: AgentSession) -> None:
    """Reconcile recorded usage after a worker dies before result bookkeeping."""
    rows = db.execute(
        select(AgentStep, AgentRun)
        .join(AgentRun, AgentRun.agent_step_id == AgentStep.id)
        .where(AgentStep.session_id == goal.id)
    ).all()
    for step, run in rows:
        goal.input_tokens += (run.input_tokens or 0) - step.input_tokens
        goal.output_tokens += (run.output_tokens or 0) - step.output_tokens
        step.input_tokens = run.input_tokens or 0
        step.output_tokens = run.output_tokens or 0
