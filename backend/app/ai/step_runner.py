"""Account-agent model-step evidence and provider call boundary.

The coordinator claims and reserves a durable AgentStep first. This runner commits the linked
AgentRun before calling a provider, then records bounded metadata and usage afterward.
"""

import uuid
from dataclasses import dataclass, replace

from sqlalchemy import func, or_, select

from app.agent.models import AgentSession, AgentStep
from app.ai.models import AgentRun
from app.ai.runner import BUDGET_EXCEEDED, BUDGET_WINDOW, RunnerDeps
from app.core.context import WorkspaceContext
from app.core.errors import RetryableError
from app.identity.models import Workspace
from app.integrations.llm.base import LLMMessage
from app.integrations.llm.errors import (
    LLMConfigError,
    LLMError,
    LLMInvalidOutput,
    LLMTransientError,
)
from app.integrations.llm.steps import LLMStepRequest, LLMStepResult


@dataclass(frozen=True)
class StepOutcome:
    agent_run_id: uuid.UUID
    result: LLMStepResult | None
    error_code: str | None
    repair_attempts: int


def _reserve_repair(deps: RunnerDeps, workspace_id: uuid.UUID, run_id: uuid.UUID) -> bool:
    """Account for the extra provider call before it happens, under the workspace lock."""
    with deps.session_factory() as session:
        workspace = session.scalar(
            select(Workspace).where(Workspace.id == workspace_id).with_for_update()
        )
        if workspace is None:
            return False
        run = session.scalar(
            select(AgentRun)
            .where(AgentRun.workspace_id == workspace_id, AgentRun.id == run_id)
            .with_for_update()
        )
        if run is None or run.status != "running":
            return False
        used = session.scalar(
            select(func.coalesce(func.sum(1 + AgentRun.repair_attempts), 0)).where(
                AgentRun.workspace_id == workspace_id,
                AgentRun.created_at >= deps.clock.now() - BUDGET_WINDOW,
                AgentRun.status != "queued",
                or_(
                    AgentRun.error_code.is_distinct_from(BUDGET_EXCEEDED),
                    AgentRun.output.is_not(None),
                ),
            )
        )
        if int(used or 0) >= deps.settings.llm_max_calls_per_workspace_per_day:
            return False
        if run.agent_step_id is not None:
            step = session.get(AgentStep, run.agent_step_id)
            goal = (
                session.scalar(
                    select(AgentSession).where(AgentSession.id == step.session_id).with_for_update()
                )
                if step
                else None
            )
            if goal is not None:
                if goal.model_steps >= 24 or goal.activation_steps >= 8:
                    return False
                goal.model_steps += 1
                goal.activation_steps += 1
        run.repair_attempts = 1
        session.commit()
        return True


def run_step(
    deps: RunnerDeps,
    ctx: WorkspaceContext,
    step_id: uuid.UUID,
    request: LLMStepRequest,
    *,
    job_id: uuid.UUID | None = None,
) -> StepOutcome:
    """Call a model once (one schema repair allowed), with no open DB transaction."""
    if request.task != "account_agent_step":
        raise ValueError("account-agent step runner requires account_agent_step")
    now = deps.clock.now()
    model = (
        deps.settings.llm_model_for("account_agent_step") if not deps.provider.is_fake else "fake"
    )
    request = replace(request, model=model)
    with deps.session_factory() as session:
        # Serialize this new agent path's daily reservation. Legacy task calls keep their
        # existing runner; Session 05 owns cumulative goal/token reservations.
        workspace = session.scalar(
            select(Workspace).where(Workspace.id == ctx.workspace_id).with_for_update()
        )
        if workspace is None:
            raise ValueError("workspace not found")
        step = session.scalar(
            select(AgentStep).where(
                AgentStep.workspace_id == ctx.workspace_id, AgentStep.id == step_id
            )
        )
        if step is None:
            raise ValueError("agent step not found in workspace")
        if step.status != "model_pending":
            raise ValueError("agent step is not waiting for a model result")
        if session.scalar(select(AgentRun.id).where(AgentRun.agent_step_id == step.id)) is not None:
            raise ValueError(
                "agent step already has model-call evidence; recovery must claim a new step"
            )
        used = session.scalar(
            select(func.coalesce(func.sum(1 + AgentRun.repair_attempts), 0)).where(
                AgentRun.workspace_id == ctx.workspace_id,
                AgentRun.created_at >= now - BUDGET_WINDOW,
                AgentRun.status != "queued",
                or_(
                    AgentRun.error_code.is_distinct_from(BUDGET_EXCEEDED),
                    AgentRun.output.is_not(None),
                ),
            )
        )
        run = AgentRun(
            workspace_id=ctx.workspace_id,
            agent_step_id=step.id,
            task="account_agent_step",
            status="running",
            provider=deps.provider.name,
            model=model,
            prompt_version="v1",
            input_snapshot={
                "message_count": len(request.messages),
                "tool_names": [item.name for item in request.tools],
                "observation_count": len(request.observations),
            },
            is_fake=deps.provider.is_fake,
            job_id=job_id,
            created_at=now,
            started_at=now,
        )
        session.add(run)
        if int(used or 0) >= deps.settings.llm_max_calls_per_workspace_per_day:
            run.status = "failed"
            run.error_code = BUDGET_EXCEEDED
            run.completed_at = now
        session.commit()
        run_id = run.id
        if run.status == "failed":
            return StepOutcome(run_id, None, BUDGET_EXCEEDED, 0)

    result: LLMStepResult | None = None
    error: LLMError | None = None
    repairs = 0
    budget_exhausted = False
    consumed_input: int | None = None
    consumed_output: int | None = None
    for attempt in range(2):
        try:
            result = deps.provider.generate_step(request)
            break
        except LLMInvalidOutput as exc:
            error = exc
            if exc.usage is not None:
                if exc.usage.input_tokens is not None:
                    consumed_input = (consumed_input or 0) + exc.usage.input_tokens
                if exc.usage.output_tokens is not None:
                    consumed_output = (consumed_output or 0) + exc.usage.output_tokens
            if attempt:
                break
            if not _reserve_repair(deps, ctx.workspace_id, run_id):
                budget_exhausted = True
                break
            repairs = 1
            request = replace(
                request,
                messages=(
                    *request.messages,
                    LLMMessage(
                        "user", "The previous step was invalid. Return one valid function call."
                    ),
                ),
            )
        except LLMError as exc:
            error = exc
            break
    with deps.session_factory() as session:
        recorded = session.scalar(
            select(AgentRun)
            .where(AgentRun.workspace_id == ctx.workspace_id, AgentRun.id == run_id)
            .with_for_update()
        )
        if recorded is not None:
            recorded.repair_attempts = repairs
            recorded.status = "succeeded" if result is not None else "failed"
            recorded.error_code = (
                None
                if result is not None
                else BUDGET_EXCEEDED
                if budget_exhausted
                else (error.code if error else "LLM_UNAVAILABLE")
            )
            recorded.output = {
                "provider_calls": 1 + repairs,
                "kind": result.kind if result is not None else None,
                "tool_name": (
                    result.tool_name
                    if result is not None
                    and result.tool_name in {tool.name for tool in request.tools}
                    else None
                ),
            }
            if result is not None:
                if result.usage.input_tokens is not None:
                    consumed_input = (consumed_input or 0) + result.usage.input_tokens
                if result.usage.output_tokens is not None:
                    consumed_output = (consumed_output or 0) + result.usage.output_tokens
            recorded.input_tokens = consumed_input
            recorded.output_tokens = consumed_output
            recorded.latency_ms = result.latency_ms if result is not None else None
            recorded.completed_at = deps.clock.now()
            session.commit()
    if isinstance(error, LLMTransientError) and result is None:
        raise RetryableError(
            error.code, error.detail, retry_after_seconds=error.retry_after_seconds
        ) from error
    if isinstance(error, LLMConfigError):
        return StepOutcome(run_id, None, error.code, repairs)
    error_code = (
        None
        if result is not None
        else BUDGET_EXCEEDED
        if budget_exhausted
        else error.code
        if error
        else None
    )
    return StepOutcome(run_id, result, error_code, repairs)
