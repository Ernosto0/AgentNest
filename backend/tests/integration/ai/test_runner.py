"""The task runner against a real database (agent-runtime.md §2, ADR-009)."""

import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.ai import prompt as prompt_module
from app.ai.models import AgentRun
from app.ai.runner import RunnerDeps, TaskDefinition, create_queued_run, run_task
from app.core.clock import FrozenClock
from app.core.config import Settings
from app.core.errors import RetryableError
from app.identity.models import Workspace
from app.integrations.llm import FakeLLMProvider, LLMMessage
from app.integrations.llm import fake as fake_module
from app.integrations.llm.base import LLMResult, LLMUsage
from app.integrations.llm.errors import LLMConfigError, LLMRefusal, LLMTransientError
from tests.factories import create_workspace, knowledge_ctx

# Any task name the table allows. It is a real task now (Phase 5), so the stand-in fake below is
# installed per test and the real one comes back afterwards.
TASK = "draft_content"


class Out(BaseModel):
    value: int

    @field_validator("value")
    @classmethod
    def _small(cls, v: int) -> int:
        if v > 100:
            raise ValueError("too big")
        return v


@dataclass
class In:
    number: int
    api_key: str = "sk-should-be-redacted"


def _impl(context: In, schema: type[BaseModel]) -> BaseModel:
    return schema(value=context.number)


def _definition(post_validate: Any = None) -> TaskDefinition[In, Out]:
    return TaskDefinition(
        name=TASK,
        output_schema=Out,
        max_output_tokens=100,
        timeout_s=5,
        build_messages=lambda i: [
            LLMMessage("user", f"<task_parameters>{i.number}</task_parameters>")
        ],
        post_validate=post_validate or (lambda _i, _o: []),
        snapshot=lambda i: {"number": i.number, "api_key": i.api_key},
    )


@pytest.fixture(autouse=True)
def _stand_in_fake(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(fake_module._IMPLEMENTATIONS, TASK, _impl)


@pytest.fixture(autouse=True)
def _prompt_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    (tmp_path / TASK).mkdir()
    (tmp_path / TASK / "v1.md").write_text("You are a test task.", encoding="utf-8")
    monkeypatch.setattr(prompt_module, "PROMPTS_DIR", tmp_path)
    prompt_module.load_prompt.cache_clear()
    yield
    prompt_module.load_prompt.cache_clear()


@pytest.fixture
def workspace(db_session: Session) -> Workspace:
    return create_workspace(db_session)


@pytest.fixture
def provider() -> FakeLLMProvider:
    return FakeLLMProvider()


def _deps(
    factory: sessionmaker[Session],
    clock: FrozenClock,
    provider: Any,
    **settings: Any,
) -> RunnerDeps:
    return RunnerDeps(factory, clock, provider, Settings(_env_file=None, **settings))


def _runs(session: Session) -> list[AgentRun]:
    session.expire_all()  # the runner writes through its own sessions
    return list(session.scalars(select(AgentRun).order_by(AgentRun.created_at, AgentRun.id)))


def test_success_records_a_fake_run_with_a_redacted_snapshot(
    db_session: Session,
    shared_session_factory: sessionmaker[Session],
    clock: FrozenClock,
    provider: FakeLLMProvider,
    workspace: Workspace,
) -> None:
    deps = _deps(shared_session_factory, clock, provider)
    job_id, correlation = uuid.uuid4(), uuid.uuid4()

    outcome = run_task(
        deps, knowledge_ctx(workspace), _definition(), In(7), correlation, job_id=job_id
    )

    assert outcome.ok and outcome.output == Out(value=7)
    (run,) = _runs(db_session)
    assert run.id == outcome.agent_run_id
    assert (run.task, run.status, run.provider, run.model) == (TASK, "succeeded", "fake", "fake")
    assert run.is_fake is True and run.prompt_version == "v1"
    assert run.output == {"value": 7}
    assert run.input_snapshot == {"number": 7, "api_key": "[REDACTED]"}
    assert (run.job_id, run.correlation_id) == (job_id, correlation)
    assert run.input_tokens is None  # tokens are only recorded for a real provider
    assert run.started_at == clock.now() and run.completed_at == clock.now()
    assert provider.calls[0].system == "You are a test task."


def test_a_real_provider_run_records_tokens_and_is_not_fake(
    db_session: Session,
    shared_session_factory: sessionmaker[Session],
    clock: FrozenClock,
    workspace: Workspace,
) -> None:
    class Real:
        name = "openai"
        is_fake = False

        def generate_structured(self, **kwargs: Any) -> LLMResult:
            return LLMResult(
                raw_text='{"value": 3}',
                usage=LLMUsage(input_tokens=100, output_tokens=20),
                latency_ms=250,
                provider="openai",
                model="gpt-6-luna",
                is_fake=False,
            )

    deps = _deps(shared_session_factory, clock, Real(), llm_model_default="gpt-6-luna")
    run_task(deps, knowledge_ctx(workspace), _definition(), In(3))
    (run,) = _runs(db_session)
    assert (run.provider, run.model, run.is_fake) == ("openai", "gpt-6-luna", False)
    assert (run.input_tokens, run.output_tokens, run.latency_ms) == (100, 20, 250)


def test_the_run_row_is_committed_before_the_provider_is_called(
    db_session: Session,
    shared_session_factory: sessionmaker[Session],
    clock: FrozenClock,
    workspace: Workspace,
) -> None:
    seen: list[str] = []

    class Spy:
        name = "fake"
        is_fake = True

        def generate_structured(self, **kwargs: Any) -> LLMResult:
            seen.extend(r.status for r in _runs(db_session))
            return LLMResult('{"value": 1}', LLMUsage(), 1, "fake", "fake", True)

    run_task(
        _deps(shared_session_factory, clock, Spy()), knowledge_ctx(workspace), _definition(), In(1)
    )
    assert seen == ["running"]  # a crash during the call would leave this trace


def test_invalid_output_is_repaired_once_with_the_errors_sent_back(
    db_session: Session,
    shared_session_factory: sessionmaker[Session],
    clock: FrozenClock,
    provider: FakeLLMProvider,
    workspace: Workspace,
) -> None:
    provider.queue(TASK, {"value": "not a number"})
    outcome = run_task(
        _deps(shared_session_factory, clock, provider),
        knowledge_ctx(workspace),
        _definition(),
        In(5),
    )

    assert outcome.ok and outcome.output == Out(value=5)
    (run,) = _runs(db_session)
    assert run.repair_attempts == 1 and run.status == "succeeded"
    repair_call = provider.calls[1]
    assert repair_call.messages[-1].role == "user"
    assert "did not pass validation" in repair_call.messages[-1].content
    assert "value" in repair_call.messages[-1].content
    assert repair_call.messages[-2].role == "assistant"  # the bad output is shown to the model


def test_still_invalid_after_the_repair_fails_with_llm_output_invalid(
    db_session: Session,
    shared_session_factory: sessionmaker[Session],
    clock: FrozenClock,
    provider: FakeLLMProvider,
    workspace: Workspace,
) -> None:
    provider.queue(TASK, "this is not json")
    provider.queue(TASK, {"value": 1000})  # valid JSON, fails the schema's own validator
    outcome = run_task(
        _deps(shared_session_factory, clock, provider),
        knowledge_ctx(workspace),
        _definition(),
        In(5),
    )

    assert not outcome.ok and outcome.error_code == "LLM_OUTPUT_INVALID"
    assert len(provider.calls) == 2  # exactly one repair, never more
    (run,) = _runs(db_session)
    assert (run.status, run.error_code, run.repair_attempts) == ("failed", "LLM_OUTPUT_INVALID", 1)
    assert run.validation_errors and "too big" in run.validation_errors[0]
    assert run.output is None


def test_the_post_validator_failure_goes_through_the_same_repair(
    db_session: Session,
    shared_session_factory: sessionmaker[Session],
    clock: FrozenClock,
    provider: FakeLLMProvider,
    workspace: Workspace,
) -> None:
    provider.queue(TASK, {"value": 1})  # schema-valid but semantically unacceptable
    definition = _definition(lambda _i, o: ["value must be 5"] if o.value != 5 else [])
    outcome = run_task(
        _deps(shared_session_factory, clock, provider), knowledge_ctx(workspace), definition, In(5)
    )
    assert outcome.ok and outcome.output == Out(value=5)
    assert "value must be 5" in provider.calls[1].messages[-1].content


def test_transient_provider_errors_are_raised_for_the_job_to_retry(
    db_session: Session,
    shared_session_factory: sessionmaker[Session],
    clock: FrozenClock,
    provider: FakeLLMProvider,
    workspace: Workspace,
) -> None:
    provider.queue(TASK, LLMTransientError("down", retry_after_seconds=30))
    with pytest.raises(RetryableError) as info:
        run_task(
            _deps(shared_session_factory, clock, provider),
            knowledge_ctx(workspace),
            _definition(),
            In(5),
        )
    assert info.value.code == "LLM_UNAVAILABLE" and info.value.retry_after_seconds == 30
    (run,) = _runs(db_session)
    assert (run.status, run.error_code) == ("failed", "LLM_UNAVAILABLE")


@pytest.mark.parametrize(
    ("error", "code"),
    [(LLMRefusal("no"), "LLM_REFUSED"), (LLMConfigError("bad key"), "LLM_UNAVAILABLE")],
)
def test_refusals_and_config_errors_are_final_and_never_fall_back_to_fake(
    db_session: Session,
    shared_session_factory: sessionmaker[Session],
    clock: FrozenClock,
    provider: FakeLLMProvider,
    workspace: Workspace,
    error: Exception,
    code: str,
) -> None:
    provider.queue(TASK, error)
    outcome = run_task(
        _deps(shared_session_factory, clock, provider),
        knowledge_ctx(workspace),
        _definition(),
        In(5),
    )
    assert not outcome.ok and outcome.error_code == code
    assert len(provider.calls) == 1  # no repair, no second attempt
    (run,) = _runs(db_session)
    assert (run.status, run.error_code) == ("failed", code)


def test_the_daily_budget_stops_calls_but_still_leaves_a_trace(
    db_session: Session,
    shared_session_factory: sessionmaker[Session],
    clock: FrozenClock,
    provider: FakeLLMProvider,
    workspace: Workspace,
) -> None:
    deps = _deps(shared_session_factory, clock, provider, llm_max_calls_per_workspace_per_day=2)
    ctx = knowledge_ctx(workspace)
    assert run_task(deps, ctx, _definition(), In(1)).ok
    assert run_task(deps, ctx, _definition(), In(2)).ok

    blocked = run_task(deps, ctx, _definition(), In(3))
    assert blocked.error_code == "LLM_BUDGET_EXCEEDED" and not blocked.ok
    assert len(provider.calls) == 2  # the provider was not called
    codes = [r.error_code for r in _runs(db_session)]  # same frozen instant: order is arbitrary
    assert len(codes) == 3 and codes.count("LLM_BUDGET_EXCEEDED") == 1

    # Rejected attempts do not count against the budget, and the window rolls forward.
    clock.advance(timedelta(hours=24, minutes=1))
    assert run_task(deps, ctx, _definition(), In(4)).ok


def test_the_budget_is_per_workspace(
    db_session: Session,
    shared_session_factory: sessionmaker[Session],
    clock: FrozenClock,
    provider: FakeLLMProvider,
    workspace: Workspace,
) -> None:
    other = create_workspace(db_session)
    deps = _deps(shared_session_factory, clock, provider, llm_max_calls_per_workspace_per_day=1)
    assert run_task(deps, knowledge_ctx(workspace), _definition(), In(1)).ok
    assert run_task(deps, knowledge_ctx(other), _definition(), In(1)).ok


def test_a_queued_run_keeps_its_snapshot_and_is_reused(
    db_session: Session,
    shared_session_factory: sessionmaker[Session],
    clock: FrozenClock,
    provider: FakeLLMProvider,
    workspace: Workspace,
) -> None:
    deps = _deps(shared_session_factory, clock, provider)
    ctx = knowledge_ctx(workspace)
    queued = create_queued_run(
        db_session,
        deps.clock,
        deps.provider,
        ctx,
        TASK,
        {"text": "pasted bio", "token": "x"},
        uuid.uuid4(),
    )
    db_session.commit()
    assert queued.status == "queued" and queued.input_snapshot == {
        "text": "pasted bio",
        "token": "[REDACTED]",
    }

    definition = TaskDefinition(
        name=TASK,
        output_schema=Out,
        max_output_tokens=100,
        timeout_s=5,
        build_messages=lambda i: [LLMMessage("user", "x")],
    )  # no snapshot of its own: the stored one must survive
    outcome = run_task(deps, ctx, definition, In(2), agent_run_id=queued.id)

    assert outcome.agent_run_id == queued.id
    runs = _runs(db_session)
    assert len(runs) == 1 and runs[0].status == "succeeded"
    assert runs[0].input_snapshot == {"text": "pasted bio", "token": "[REDACTED]"}


def test_queued_runs_do_not_count_against_the_budget(
    db_session: Session,
    shared_session_factory: sessionmaker[Session],
    clock: FrozenClock,
    provider: FakeLLMProvider,
    workspace: Workspace,
) -> None:
    deps = _deps(shared_session_factory, clock, provider, llm_max_calls_per_workspace_per_day=1)
    ctx = knowledge_ctx(workspace)
    queued = create_queued_run(db_session, deps.clock, deps.provider, ctx, TASK, {"n": 1}, None)
    db_session.commit()
    assert run_task(deps, ctx, _definition(), In(1), agent_run_id=queued.id).ok


def test_the_runner_does_not_keep_a_transaction_open_during_the_call(
    shared_session_factory: sessionmaker[Session],
    clock: FrozenClock,
    workspace: Workspace,
) -> None:
    """No external call inside a DB transaction (CLAUDE.md non-negotiable)."""
    live: list[Session] = []

    class Tracking:
        def __call__(self) -> Session:
            session = shared_session_factory()
            live.append(session)
            return session

    in_transaction_during_call: list[bool] = []

    class Spy:
        name = "fake"
        is_fake = True

        def generate_structured(self, **kwargs: Any) -> LLMResult:
            in_transaction_during_call.append(any(s.in_transaction() for s in live))
            return LLMResult('{"value": 1}', LLMUsage(), 1, "fake", "fake", True)

    deps = RunnerDeps(Tracking(), clock, Spy(), Settings(_env_file=None))  # type: ignore[arg-type]
    run_task(deps, knowledge_ctx(workspace), _definition(), In(1))
    assert live and in_transaction_during_call == [False]
