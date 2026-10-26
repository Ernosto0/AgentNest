"""Model call evidence is committed before and after a scripted account-agent step."""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.agent.models import AgentSession, AgentStep, AgentThread
from app.ai.models import AgentRun
from app.ai.runner import RunnerDeps
from app.ai.step_runner import run_step
from app.core.clock import FrozenClock
from app.core.config import Settings
from app.core.context import ActorRef, WorkspaceContext
from app.identity.models import Workspace
from app.integrations.instagram.models import SocialAccount
from app.integrations.llm.base import LLMMessage, LLMUsage
from app.integrations.llm.errors import LLMInvalidOutput
from app.integrations.llm.fake import FakeLLMProvider
from app.integrations.llm.steps import LLMStepRequest, LLMStepResult


def _seed(db: Session) -> tuple[WorkspaceContext, uuid.UUID]:
    workspace = Workspace(
        name="Step",
        slug=f"step-{uuid.uuid4().hex[:8]}",
        business_category="services",
        market="global",
        default_locale="en",
        timezone="UTC",
        currency="USD",
    )
    db.add(workspace)
    db.flush()
    account = SocialAccount(
        workspace_id=workspace.id, provider_kind="mock", external_account_id=uuid.uuid4().hex
    )
    db.add(account)
    db.flush()
    thread = AgentThread(
        workspace_id=workspace.id,
        social_account_id=account.id,
        surface="owner_task",
        source_ref=uuid.uuid4().hex,
    )
    db.add(thread)
    db.flush()
    goal = AgentSession(
        workspace_id=workspace.id,
        thread_id=thread.id,
        initiating_event_cursor=0,
        goal_key="goal-1",
    )
    db.add(goal)
    db.flush()
    step = AgentStep(
        workspace_id=workspace.id,
        session_id=goal.id,
        sequence=1,
        claim_token=uuid.uuid4(),
        captured_cursor=0,
        captured_epoch=0,
        captured_deletion_generation=0,
        status="model_pending",
    )
    db.add(step)
    db.flush()
    return (
        WorkspaceContext(workspace.id, ActorRef.system("test"), None, "UTC", "en", False),
        step.id,
    )


def test_scripted_step_links_redacted_run_and_repair_count(
    db_session: Session,
    shared_session_factory: sessionmaker[Session],
    clock: FrozenClock,
) -> None:
    ctx, step_id = _seed(db_session)
    fake = FakeLLMProvider()
    fake.queue_step(LLMInvalidOutput("bad schema", usage=LLMUsage(3, 2)))
    fake.queue_step(
        LLMStepResult("complete", LLMUsage(12, 4), 3, "fake", "fake", True, explanation="done")
    )
    deps = RunnerDeps(
        shared_session_factory,
        clock,
        fake,
        Settings(_env_file=None, llm_provider="fake"),
    )
    request = LLMStepRequest(
        task="account_agent_step",
        model="fake",
        system="trusted",
        messages=(LLMMessage("user", "<untrusted_customer>private body</untrusted_customer>"),),
        tools=(),
    )
    outcome = run_step(deps, ctx, step_id, request)
    assert outcome.error_code is None and outcome.result is not None
    assert outcome.repair_attempts == 1
    assert len(fake.step_calls) == 2
    run = db_session.scalar(select(AgentRun).where(AgentRun.id == outcome.agent_run_id))
    assert run is not None
    assert run.agent_step_id == step_id and run.status == "succeeded"
    assert (run.input_tokens, run.output_tokens, run.repair_attempts) == (15, 6, 1)
    assert "private body" not in str(run.input_snapshot)
    assert "private body" not in str(run.output)


def test_repair_call_is_denied_when_daily_budget_has_one_slot(
    db_session: Session,
    shared_session_factory: sessionmaker[Session],
    clock: FrozenClock,
) -> None:
    ctx, step_id = _seed(db_session)
    fake = FakeLLMProvider()
    fake.queue_step(LLMInvalidOutput("bad schema"))
    fake.queue_step(
        LLMStepResult("complete", LLMUsage(), 0, "fake", "fake", True, explanation="done")
    )
    deps = RunnerDeps(
        shared_session_factory,
        clock,
        fake,
        Settings(_env_file=None, llm_provider="fake", llm_max_calls_per_workspace_per_day=1),
    )
    request = LLMStepRequest(
        task="account_agent_step",
        model="fake",
        system="trusted",
        messages=(LLMMessage("user", "task"),),
        tools=(),
    )
    outcome = run_step(deps, ctx, step_id, request)
    assert outcome.result is None and outcome.error_code == "LLM_BUDGET_EXCEEDED"
    assert len(fake.step_calls) == 1
    run = db_session.scalar(select(AgentRun).where(AgentRun.id == outcome.agent_run_id))
    assert run is not None and run.status == "failed" and run.repair_attempts == 0
    assert run.output == {"provider_calls": 1, "kind": None, "tool_name": None}
    first_step = db_session.get(AgentStep, step_id)
    assert first_step is not None
    next_step = AgentStep(
        workspace_id=ctx.workspace_id,
        session_id=first_step.session_id,
        sequence=2,
        claim_token=uuid.uuid4(),
        captured_cursor=0,
        captured_epoch=0,
        captured_deletion_generation=0,
        status="model_pending",
    )
    db_session.add(next_step)
    db_session.flush()
    denied = run_step(deps, ctx, next_step.id, request)
    assert denied.error_code == "LLM_BUDGET_EXCEEDED" and len(fake.step_calls) == 1
