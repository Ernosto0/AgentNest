"""Task runner (agent-runtime.md §2, ADR-009): the only place an LLM is called.

``run_task`` is called from job handlers. An LLM task is a pure proposal function: it gets a
validated input, returns a validated output, has no tools and no DB access. The runner owns
everything around the call: daily budget, versioned prompt, the ``agent_runs`` row (committed
**before** the call so a crash leaves a trace), validation with one repair call, usage capture,
and error classification for the job's retry policy. No DB transaction is open during the call.
"""

import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any, Literal

from pydantic import BaseModel, ValidationError
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, sessionmaker

from app.ai.models import AgentRun
from app.ai.prompt import render_system
from app.core.clock import Clock
from app.core.config import Settings
from app.core.context import WorkspaceContext
from app.core.errors import RetryableError
from app.core.logging import get_logger, redact_value
from app.identity.models import Workspace
from app.integrations.llm import LLMProvider
from app.integrations.llm.base import LLMMessage, LLMUsage
from app.integrations.llm.errors import (
    LLMConfigError,
    LLMError,
    LLMInvalidOutput,
    LLMRefusal,
    LLMTransientError,
)

BUDGET_WINDOW = timedelta(hours=24)
BUDGET_EXCEEDED = "LLM_BUDGET_EXCEEDED"
_log = get_logger("app.ai.runner")


@dataclass(frozen=True)
class TaskDefinition[InputT, OutputT: BaseModel]:
    """Everything task-specific. The runner knows nothing about commands or facts."""

    name: str
    output_schema: type[OutputT]
    max_output_tokens: int
    timeout_s: float
    build_messages: Callable[[InputT], list[LLMMessage]]
    prompt_version: str = "v1"
    # Trusted static text substituted into the system prompt (<<name>> markers).
    system_variables: Callable[[], dict[str, str]] = dict
    # Semantic checks after schema validation; returns human-readable problems (empty = ok).
    post_validate: Callable[[InputT, OutputT], list[str]] = field(default=lambda _i, _o: [])
    # The (to be redacted) input kept in ``agent_runs.input_snapshot``.
    snapshot: Callable[[InputT], dict[str, Any]] = field(default=lambda _i: {})


@dataclass(frozen=True)
class RunnerDeps:
    session_factory: sessionmaker[Session]
    clock: Clock
    provider: LLMProvider
    settings: Settings


@dataclass(frozen=True)
class TaskOutcome[OutputT: BaseModel]:
    status: Literal["succeeded", "failed"]
    agent_run_id: uuid.UUID
    output: OutputT | None = None
    error_code: str | None = None
    validation_errors: list[str] | None = None

    @property
    def ok(self) -> bool:
        return self.status == "succeeded"


def create_queued_run(
    session: Session,
    clock: Clock,
    provider: LLMProvider,
    ctx: WorkspaceContext,
    task: str,
    snapshot: dict[str, Any],
    correlation_id: uuid.UUID | None,
) -> AgentRun:
    """Insert a ``queued`` run (in the caller's transaction) that holds the redacted input.

    For work whose input must not travel in a job payload (pasted text): the job carries only
    the run id and ``run_task(..., agent_run_id=...)`` picks the snapshot up.
    """
    run = AgentRun(
        workspace_id=ctx.workspace_id,
        task=task,
        status="queued",
        input_snapshot=redact_value(snapshot),
        correlation_id=correlation_id,
        is_fake=provider.is_fake,
        created_at=clock.now(),
    )
    session.add(run)
    session.flush()
    return run


def _budget_used(session: Session, deps: RunnerDeps, ctx: WorkspaceContext) -> int:
    since = deps.clock.now() - BUDGET_WINDOW
    stmt = (
        select(func.coalesce(func.sum(1 + AgentRun.repair_attempts), 0))
        .select_from(AgentRun)
        .where(
            AgentRun.workspace_id == ctx.workspace_id,
            AgentRun.created_at >= since,
            AgentRun.status != "queued",
            or_(
                AgentRun.error_code.is_(None),
                AgentRun.error_code != BUDGET_EXCEEDED,
                AgentRun.output.is_not(None),
            ),
        )
    )
    return int(session.scalar(stmt) or 0)


def reserve_repair_call(deps: RunnerDeps, ctx: WorkspaceContext, run_id: uuid.UUID) -> bool:
    with deps.session_factory() as session:
        session.scalar(select(Workspace).where(Workspace.id == ctx.workspace_id).with_for_update())
        run = session.get(AgentRun, run_id)
        if run is None or run.status != "running":
            return False
        if _budget_used(session, deps, ctx) >= deps.settings.llm_max_calls_per_workspace_per_day:
            return False
        run.repair_attempts = 1
        session.commit()
        return True


def _validation_problems(exc: ValidationError) -> list[str]:
    # Location, type and message only: never echo the offending input back into logs/storage.
    return [f"{'.'.join(str(p) for p in e['loc']) or '<root>'}: {e['msg']}" for e in exc.errors()]


def _repair_message(problems: list[str]) -> LLMMessage:
    listing = "\n".join(f"- {p}" for p in problems[:20])
    return LLMMessage(
        "user",
        "Your previous output did not pass validation:\n"
        f"{listing}\n"
        "Return only the corrected JSON for the same schema. Do not change anything else.",
    )


def run_task[InputT, OutputT: BaseModel](
    deps: RunnerDeps,
    ctx: WorkspaceContext,
    task: TaskDefinition[InputT, OutputT],
    task_input: InputT,
    correlation_id: uuid.UUID | None = None,
    *,
    job_id: uuid.UUID | None = None,
    agent_run_id: uuid.UUID | None = None,
) -> TaskOutcome[OutputT]:
    """Run one task. Returns a ``TaskOutcome``; raises ``RetryableError`` for transient provider
    failures so the *job* retries (max attempts and backoff belong to the job)."""
    settings = deps.settings
    model = settings.llm_model_for(task.name) if not deps.provider.is_fake else "fake"
    now = deps.clock.now()
    snapshot = redact_value(task.snapshot(task_input))

    # [T1] budget check and the run row, committed before the call.
    with deps.session_factory() as session:
        session.scalar(select(Workspace).where(Workspace.id == ctx.workspace_id).with_for_update())
        if _budget_used(session, deps, ctx) >= settings.llm_max_calls_per_workspace_per_day:
            run = _start_or_create_run(
                session, deps, ctx, task, agent_run_id, snapshot, model, correlation_id, job_id
            )
            run.status = "failed"
            run.error_code = BUDGET_EXCEEDED
            run.completed_at = now
            session.commit()
            _log.warning("llm_budget_exceeded", task=task.name, workspace_id=str(ctx.workspace_id))
            return TaskOutcome("failed", run.id, error_code=BUDGET_EXCEEDED)
        run = _start_or_create_run(
            session, deps, ctx, task, agent_run_id, snapshot, model, correlation_id, job_id
        )
        run_id = run.id
        session.commit()

    execution = execute_task(
        deps.provider,
        task,
        task_input,
        model,
        reserve_repair=lambda: reserve_repair_call(deps, ctx, run_id),
    )
    if execution.error is not None:
        return _finish_with_error(deps, run_id, execution.totals, execution.error)
    if execution.output is None:
        _finalise(
            deps,
            run_id,
            execution.totals,
            status="failed",
            error_code="LLM_OUTPUT_INVALID",
            validation_errors=execution.problems,
        )
        return TaskOutcome(
            "failed", run_id, error_code="LLM_OUTPUT_INVALID", validation_errors=execution.problems
        )

    _finalise(
        deps,
        run_id,
        execution.totals,
        status="succeeded",
        output=execution.output.model_dump(mode="json"),
    )
    return TaskOutcome("succeeded", run_id, output=execution.output)


@dataclass
class Execution[OutputT: BaseModel]:
    """What one model interaction produced: a validated output, or why not."""

    output: OutputT | None
    problems: list[str]
    totals: "_Totals"
    error: LLMError | None = None  # a provider error other than invalid output


def execute_task[InputT, OutputT: BaseModel](
    provider: LLMProvider,
    task: TaskDefinition[InputT, OutputT],
    task_input: InputT,
    model: str,
    *,
    reserve_repair: Callable[[], bool] = lambda: True,
) -> Execution[OutputT]:
    """The model call itself: prompt, call, validation, and at most one repair call.

    No database and no clock, so evals run exactly the logic production runs (``run_task``
    wraps this with the budget, the ``agent_runs`` row and retry classification).
    """
    system = render_system(task.name, task.prompt_version, task.system_variables())
    messages = task.build_messages(task_input)
    totals = _Totals()
    problems: list[str] = []
    raw_text: str | None = None

    for attempt in range(2):  # the original call and at most one repair call
        try:
            result = provider.generate_structured(
                task=task.name,
                model=model,
                system=system,
                messages=messages,
                output_schema=task.output_schema,
                max_output_tokens=task.max_output_tokens,
                timeout_s=task.timeout_s,
                context=task_input,
            )
        except LLMInvalidOutput as exc:
            totals.calls += 1
            raw_text = exc.raw_text
            problems = [exc.detail or "invalid output"]
        except LLMError as exc:
            return Execution(None, problems, totals, error=exc)
        else:
            totals.add(result.usage, result.latency_ms)
            raw_text = result.raw_text
            output, problems = _validate(task, task_input, result.raw_text)
            if output is not None:
                return Execution(output, [], totals)
        if attempt == 0:  # one repair call, carrying the validation errors back to the model
            if not reserve_repair():
                return Execution(None, [BUDGET_EXCEEDED], totals)
            history = list(messages)
            if raw_text:
                history.append(LLMMessage("assistant", raw_text))
            messages = [*history, _repair_message(problems)]
            totals.repairs += 1
    return Execution(None, problems, totals)


@dataclass
class _Totals:
    calls: int = 0
    repairs: int = 0
    input_tokens: int | None = None
    output_tokens: int | None = None
    latency_ms: int = 0

    def add(self, usage: LLMUsage, latency_ms: int) -> None:
        self.calls += 1
        self.latency_ms += latency_ms
        if usage.input_tokens is not None:
            self.input_tokens = (self.input_tokens or 0) + usage.input_tokens
        if usage.output_tokens is not None:
            self.output_tokens = (self.output_tokens or 0) + usage.output_tokens


def _validate[InputT, OutputT: BaseModel](
    task: TaskDefinition[InputT, OutputT], task_input: InputT, raw_text: str
) -> tuple[OutputT | None, list[str]]:
    """Always re-validate with Pydantic (even if the provider guarantees the schema), then the
    task's own semantic checks."""
    try:
        parsed = task.output_schema.model_validate_json(raw_text)
    except ValidationError as exc:
        return None, _validation_problems(exc)
    except ValueError as exc:  # not JSON at all
        return None, [f"not valid JSON: {exc.__class__.__name__}"]
    semantic = task.post_validate(task_input, parsed)
    return (None, semantic) if semantic else (parsed, [])


def _start_or_create_run(
    session: Session,
    deps: RunnerDeps,
    ctx: WorkspaceContext,
    task: TaskDefinition[Any, Any],
    agent_run_id: uuid.UUID | None,
    snapshot: dict[str, Any],
    model: str,
    correlation_id: uuid.UUID | None,
    job_id: uuid.UUID | None,
) -> AgentRun:
    now = deps.clock.now()
    run: AgentRun | None = None
    if agent_run_id is not None:
        run = session.scalar(
            select(AgentRun)
            .where(AgentRun.workspace_id == ctx.workspace_id, AgentRun.id == agent_run_id)
            .with_for_update()
        )
    if run is None:
        run = AgentRun(
            workspace_id=ctx.workspace_id, task=task.name, created_at=now, status="running"
        )
        session.add(run)
    elif run.input_snapshot is not None and not snapshot:
        snapshot = run.input_snapshot  # keep what the endpoint stored (pasted text)
    run.status = "running"
    run.provider = deps.provider.name
    run.model = model
    run.prompt_version = task.prompt_version
    run.input_snapshot = snapshot or None
    run.job_id = job_id
    run.correlation_id = correlation_id or run.correlation_id
    run.is_fake = deps.provider.is_fake
    run.started_at = now
    run.error_code = None
    session.flush()
    return run


def _finalise(
    deps: RunnerDeps,
    run_id: uuid.UUID,
    totals: _Totals,
    *,
    status: Literal["succeeded", "failed"],
    output: dict[str, Any] | None = None,
    error_code: str | None = None,
    validation_errors: list[str] | None = None,
) -> None:
    with deps.session_factory() as session:
        run = session.get(AgentRun, run_id)
        if run is None:  # purged meanwhile; nothing to record
            return
        run.status = status
        run.output = output
        run.error_code = error_code
        run.validation_errors = validation_errors
        run.repair_attempts = totals.repairs
        run.input_tokens = totals.input_tokens
        run.output_tokens = totals.output_tokens
        run.latency_ms = totals.latency_ms
        run.completed_at = deps.clock.now()
        session.commit()


def _finish_with_error(
    deps: RunnerDeps, run_id: uuid.UUID, totals: _Totals, exc: LLMError
) -> TaskOutcome[Any]:
    """Classify a provider error: transient → the job retries; everything else is final."""
    code = exc.code
    _finalise(deps, run_id, totals, status="failed", error_code=code)
    if isinstance(exc, LLMTransientError):
        raise RetryableError(code, exc.detail, retry_after_seconds=exc.retry_after_seconds) from exc
    if isinstance(exc, LLMConfigError):
        _log.error("llm_config_error", detail=exc.detail)  # operator problem, not retryable
    elif isinstance(exc, LLMRefusal):
        _log.warning("llm_refused")
    return TaskOutcome("failed", run_id, error_code=code)
