"""Practice uses real Agent schemas/grounding against migrated PostgreSQL, with no effects."""

import uuid

import pytest
from sqlalchemy import event, func, select

from app.agent.models import AccountAgent, AgentAction, AgentSession, AgentThread
from app.agent.practice import PracticeSnapshot, run_practice
from app.ai.models import AgentRun
from app.ai.runner import RunnerDeps
from app.approvals.models import Approval
from app.identity.models import Workspace
from app.inbox import sandbox
from app.inbox.jobs import assistant_test_draft
from app.inbox.models import AssistantTestTurn, Conversation, Message, ReplyDraft
from app.inbox.payloads import AssistantTestDraftPayload
from app.integrations.calendar.models import CalendarAppointment
from app.integrations.llm.base import LLMUsage
from app.integrations.llm.errors import LLMInvalidOutput
from app.integrations.llm.fake import FakeLLMProvider
from app.integrations.llm.steps import LLMStepResult
from app.jobs.registry import JobContext
from app.knowledge.models import BusinessFact
from app.memory.models import CustomerMemory
from app.notifications.models import Notification
from app.operations.models import Operation
from app.owner_requests.models import OwnerQuestion
from tests.helpers.gym import seed_gym_facts
from tests.integration.agent.test_dm import setup

pytestmark = pytest.mark.commits


def _counts(db):
    models = (
        Conversation,
        Message,
        ReplyDraft,
        Approval,
        Operation,
        Notification,
        OwnerQuestion,
        CustomerMemory,
        CalendarAppointment,
        AgentAction,
        AgentThread,
        AgentSession,
    )
    return {
        model.__tablename__: db.scalar(select(func.count()).select_from(model)) for model in models
    }


@pytest.mark.parametrize(
    ("mode", "expected"),
    [
        ("automatic", "auto"),
        ("ask", "approval_required"),
        ("off", "blocked"),
    ],
)
def test_agent_practice_job_uses_step_provider_and_migrated_decisions(
    session_factory,
    clock,
    monkeypatch,
    mode,
    expected,
):
    ctx, _, _, settings = setup(session_factory, clock, mode=mode)
    provider = FakeLLMProvider()
    provider.queue_step(
        LLMStepResult(
            kind="tool",
            usage=LLMUsage(),
            latency_ms=0,
            provider="fake",
            model="fake",
            is_fake=True,
            tool_name="reply.validate",
            tool_arguments={"language": "en", "template": "Hello!"},
        )
    )
    provider.queue_step(
        LLMStepResult(
            kind="tool",
            usage=LLMUsage(),
            latency_ms=0,
            provider="fake",
            model="fake",
            is_fake=True,
            tool_name="dm.send",
            tool_arguments={"language": "en", "template": "Hello!"},
        )
    )
    deps = RunnerDeps(session_factory, clock, provider, settings)
    monkeypatch.setattr("app.inbox.jobs.runner_deps", lambda *_: deps)
    monkeypatch.setattr(
        "app.inbox.jobs.make_plan", lambda *_: pytest.fail("legacy generation called")
    )
    monkeypatch.setattr(
        "app.agent.tools.broker.ToolBroker.dispatch",
        lambda *_a, **_k: pytest.fail("live broker called"),
    )
    with session_factory() as db:
        turn = sandbox.submit_message(db, clock, settings, ctx, uuid.UUID(ctx.actor.id), "Hello")
        turn_id = turn.id
        baseline = _counts(db)
        db.commit()

    # Any database transaction during a model call violates the provider boundary.
    active = set()
    bind = session_factory.kw["bind"]

    def begin(conn):
        active.add(id(conn))

    def finish(conn):
        active.discard(id(conn))

    event.listen(bind, "begin", begin)
    event.listen(bind, "commit", finish)
    event.listen(bind, "rollback", finish)
    original = provider.generate_step

    def checked_call(request):
        assert not active, "model called inside a database transaction"
        return original(request)

    provider.generate_step = checked_call
    try:
        assistant_test_draft(
            JobContext(
                job_id=uuid.uuid4(),
                job_type="assistant_test_draft",
                workspace_id=ctx.workspace_id,
                correlation_id=None,
                payload=AssistantTestDraftPayload(turn_id=turn_id),
                attempt=1,
                max_attempts=3,
                session_factory=session_factory,
                clock=clock,
                _heartbeat=lambda: None,
            )
        )
    finally:
        event.remove(bind, "begin", begin)
        event.remove(bind, "commit", finish)
        event.remove(bind, "rollback", finish)
    with session_factory() as db:
        turn = db.get(AssistantTestTurn, turn_id)
        assert turn.status == "ready"
        assert turn.source == "agent"
        assert turn.decision == expected
        assert turn.draft_text == ("Hello!" if expected != "blocked" else None)
        assert _counts(db) == baseline
        runs = list(db.scalars(select(AgentRun).where(AgentRun.workspace_id == ctx.workspace_id)))
        assert len(runs) == 2
        assert all(run.agent_step_id is None for run in runs)
        assert all(run.prompt_version == "practice_v1" for run in runs)
        assert all(run.input_snapshot["is_simulated"] is True for run in runs)
        assert all(run.status == "succeeded" for run in runs)
    assert not provider.calls
    assert len(provider.step_calls) == 2
    assert provider.step_calls[1].observations[0].result["valid"] is True


def test_paused_agent_practice_is_blocked_without_model_call(session_factory, clock):
    ctx, account_id, _, settings = setup(session_factory, clock)
    with session_factory() as db:
        account = db.scalar(
            select(AccountAgent).where(AccountAgent.social_account_id == account_id)
        )
        account.state = "paused"
        db.commit()
        turn = sandbox.submit_message(db, clock, settings, ctx, uuid.UUID(ctx.actor.id), "Hello")
        prepared = sandbox.prepare(db, clock, ctx.workspace_id, turn.id)
        assert sandbox.get_controller_mode(db, ctx.workspace_id) == "agent"
        snapshot = sandbox.prepare_agent_practice(db, clock, prepared)
        db.commit()
    provider = FakeLLMProvider()
    result = run_practice(RunnerDeps(session_factory, clock, provider, settings), snapshot)
    assert result.decision == "blocked"
    assert not provider.step_calls


def test_practice_model_repairs_and_daily_budget_are_accounted(session_factory, clock):
    ctx, _, _, settings = setup(session_factory, clock)
    with session_factory() as db:
        turn = sandbox.submit_message(db, clock, settings, ctx, uuid.UUID(ctx.actor.id), "Hello")
        prepared = sandbox.prepare(db, clock, ctx.workspace_id, turn.id)
        snapshot = sandbox.prepare_agent_practice(db, clock, prepared)
        db.commit()
    assert isinstance(snapshot, PracticeSnapshot)
    provider = FakeLLMProvider()
    provider.queue_step(LLMInvalidOutput("bad schema"))
    provider.queue_step(
        LLMStepResult(
            kind="tool",
            usage=LLMUsage(),
            latency_ms=0,
            provider="fake",
            model="fake",
            is_fake=True,
            tool_name="dm.send",
            tool_arguments={"language": "en", "template": "Hello!"},
        )
    )
    deps = RunnerDeps(
        session_factory,
        clock,
        provider,
        settings.model_copy(update={"llm_max_calls_per_workspace_per_day": 2}),
    )
    assert run_practice(deps, snapshot).decision == "auto"
    assert len(provider.step_calls) == 2
    with session_factory() as db:
        run = db.scalar(select(AgentRun).where(AgentRun.workspace_id == ctx.workspace_id))
        assert run.repair_attempts == 1
    result = run_practice(deps, snapshot)
    assert result.decision == "human_required"
    assert result.reasons == ("LLM_BUDGET_EXCEEDED",)
    assert len(provider.step_calls) == 2


def test_memory_and_calendar_proposals_never_dispatch_live_tools(
    session_factory, clock, monkeypatch
):
    from dataclasses import replace

    ctx, _, _, settings = setup(session_factory, clock)
    with session_factory() as db:
        turn = sandbox.submit_message(db, clock, settings, ctx, uuid.UUID(ctx.actor.id), "Hello")
        prepared = sandbox.prepare(db, clock, ctx.workspace_id, turn.id)
        snapshot = sandbox.prepare_agent_practice(db, clock, prepared)
        baseline = _counts(db)
        db.commit()
    snapshot = replace(snapshot, calendar_connected=True)
    provider = FakeLLMProvider()
    provider.queue_step(
        LLMStepResult(
            kind="tool",
            usage=LLMUsage(),
            latency_ms=0,
            provider="fake",
            model="fake",
            is_fake=True,
            tool_name="memory.write",
            tool_arguments={
                "topic": "service",
                "kind": "preference",
                "source_message_id": str(uuid.uuid4()),
                "quote": "prefers evening",
            },
        )
    )
    provider.queue_step(
        LLMStepResult(
            kind="tool",
            usage=LLMUsage(),
            latency_ms=0,
            provider="fake",
            model="fake",
            is_fake=True,
            tool_name="calendar.book",
            tool_arguments={
                "local_date": "2026-11-21",
                "local_time": "10:00",
                "title": "Practice appointment",
            },
        )
    )
    monkeypatch.setattr(
        "app.agent.tools.broker.ToolBroker.dispatch",
        lambda *_a, **_k: pytest.fail("live broker called"),
    )
    result = run_practice(RunnerDeps(session_factory, clock, provider, settings), snapshot)
    assert result.decision == "human_required"
    assert result.reasons == ("SANDBOX_CALENDAR_SIMULATED",)
    with session_factory() as db:
        sandbox.apply_agent_practice(db, clock, snapshot, result)
        db.commit()
        assert _counts(db) == baseline
        assert db.get(AssistantTestTurn, turn.id).draft_text is None
    assert provider.step_calls[1].observations[0].result["persisted"] is False


@pytest.mark.parametrize("change_fact", [False, True])
def test_agent_practice_validates_real_fact_versions_again_before_saving(
    session_factory, clock, change_fact
):
    ctx, _, _, settings = setup(session_factory, clock)
    with session_factory() as db:
        workspace = db.get(Workspace, ctx.workspace_id)
        seed_gym_facts(db, workspace, clock)
        db.commit()
        turn = sandbox.submit_message(
            db, clock, settings, ctx, uuid.UUID(ctx.actor.id), "How much is monthly membership?"
        )
        prepared = sandbox.prepare(db, clock, ctx.workspace_id, turn.id)
        snapshot = sandbox.prepare_agent_practice(db, clock, prepared)
        fact = next(f for f in snapshot.context.facts if f.key == "pricing.membership_monthly")
        db.commit()
    provider = FakeLLMProvider()
    provider.queue_step(
        LLMStepResult(
            kind="tool",
            usage=LLMUsage(),
            latency_ms=0,
            provider="fake",
            model="fake",
            is_fake=True,
            tool_name="dm.send",
            tool_arguments={
                "language": "en",
                "template": "Monthly membership: {{fact:pricing.membership_monthly}}.",
                "fact_sources": [{"id": str(fact.fact_id), "version": fact.version}],
            },
        )
    )
    result = run_practice(RunnerDeps(session_factory, clock, provider, settings), snapshot)
    assert result.decision == "auto"
    assert result.rendered[0]["fact_id"] == str(fact.fact_id)
    with session_factory() as db:
        if change_fact:
            db.get(BusinessFact, fact.fact_id).status = "stale"
            db.commit()
        sandbox.apply_agent_practice(db, clock, snapshot, result)
        db.commit()
        turn = db.get(AssistantTestTurn, turn.id)
        assert turn.decision == ("human_required" if change_fact else "auto")
        if change_fact:
            assert turn.draft_text is None
            assert turn.decision_reasons == ["FACT_CHANGED"]
        else:
            assert turn.draft_text == result.text
            assert turn.facts_used[0]["key"] == fact.key
