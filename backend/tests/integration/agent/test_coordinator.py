"""Commit-level coordinator fences, persistence and worker execution."""

import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.agent.coordinator import claim, fresh, run_activation
from app.agent.models import AccountAgent, AgentSession, AgentStep, AgentThread
from app.agent.repository import add_event_and_wake
from app.agent.tools.broker import build_default_broker
from app.ai.runner import RunnerDeps
from app.core.clock import FrozenClock
from app.core.config import Settings
from app.identity.models import Workspace
from app.integrations.instagram.models import SocialAccount
from app.integrations.llm.base import LLMUsage
from app.integrations.llm.fake import FakeLLMProvider
from app.integrations.llm.steps import LLMStepResult
from app.jobs.models import Job
from app.jobs.queue import claim_one
from app.jobs.worker import execute_job

pytestmark = pytest.mark.commits


def seed(factory: sessionmaker[Session], clock: FrozenClock) -> tuple[uuid.UUID, uuid.UUID]:
    with factory() as db:
        ws = Workspace(
            name="Coordinator",
            slug=uuid.uuid4().hex,
            business_category="services",
            market="global",
            default_locale="en",
            timezone="UTC",
            currency="USD",
        )
        db.add(ws)
        db.flush()
        social = SocialAccount(
            workspace_id=ws.id, provider_kind="mock", external_account_id=uuid.uuid4().hex
        )
        db.add(social)
        db.flush()
        account = db.scalar(select(AccountAgent).where(AccountAgent.social_account_id == social.id))
        assert account is not None
        account.state = "active"
        account.controller_mode = "agent"
        thread = AgentThread(
            workspace_id=ws.id,
            social_account_id=social.id,
            source_ref=uuid.uuid4().hex,
            surface="owner_task",
        )
        db.add(thread)
        db.flush()
        add_event(db, clock, thread)
        db.commit()
        return ws.id, thread.id


def add_event(db: Session, clock: FrozenClock, thread: AgentThread) -> None:
    add_event_and_wake(
        db,
        workspace_id=thread.workspace_id,
        account_id=thread.social_account_id,
        thread_id=thread.id,
        kind="customer_message",
        source_kind="message",
        source_key=uuid.uuid4().hex,
        source_id=str(uuid.uuid4()),
        source_version=1,
        clock=clock,
    )


def deps(
    factory: sessionmaker[Session], clock: FrozenClock, fake: FakeLLMProvider | None = None
) -> RunnerDeps:
    return RunnerDeps(
        factory, clock, fake or FakeLLMProvider(), Settings(_env_file=None, llm_provider="fake")
    )


def result(kind: str = "complete", **kw: object) -> LLMStepResult:
    return LLMStepResult(kind, LLMUsage(4, 2), 1, "fake", "fake", True, **kw)  # type: ignore[arg-type]


def test_worker_read_result_followup_and_duplicate_wakes(session_factory, clock, monkeypatch):
    ws, thread_id = seed(session_factory, clock)
    fake = FakeLLMProvider()
    fake.queue_step(
        result(
            "tool",
            tool_name="knowledge.read",
            tool_arguments={"limit": 2, "cursor": None},
            call_id="read",
        )
    )
    fake.queue_step(result())
    runner = deps(session_factory, clock, fake)
    monkeypatch.setattr("app.agent.jobs.deps_for", lambda _: runner)
    job = claim_one(session_factory, clock, "first", 120)
    assert job is not None
    assert execute_job(session_factory, clock, job, lease_seconds=120) == "succeeded"
    assert len(fake.step_calls) == 2
    assert fake.step_calls[1].observations[0].name == "knowledge.read"
    run_activation(runner, ws, thread_id, build_default_broker())
    assert len(fake.step_calls) == 2
    with session_factory() as db:
        goal = db.scalar(select(AgentSession))
        assert goal.status == "completed" and goal.model_steps == 2 and goal.tool_calls == 1
        assert goal.input_tokens == 8 and goal.reserved_tokens == 80000


def test_duplicate_claims_and_restart_do_not_reset_budget(session_factory, clock):
    ws, tid = seed(session_factory, clock)
    runner = deps(session_factory, clock)
    with ThreadPoolExecutor(max_workers=2) as pool:
        claims = list(pool.map(lambda _: claim(runner, ws, tid), range(2)))
    assert sum(item is not None for item in claims) == 1
    first = next(item for item in claims if item)
    clock.advance(timedelta(minutes=3))
    # Same activation is exhausted by wall time: restart never grants free calls.
    assert claim(deps(session_factory, clock), ws, tid) is None
    with session_factory() as db:
        assert db.get(AgentStep, first.step_id).status == "abandoned"
        goal = db.scalar(select(AgentSession))
        assert goal.model_steps == 1 and goal.status == "failed"
        assert goal.outcome_code == "AGENT_BUDGET_EXCEEDED"


@pytest.mark.parametrize("change", ["event", "epoch", "deletion", "takeover"])
def test_stale_model_result_is_never_dispatched(session_factory, clock, change):
    ws, tid = seed(session_factory, clock)
    runner = deps(session_factory, clock)
    claimed = claim(runner, ws, tid)
    assert claimed is not None
    with session_factory() as db:
        thread = db.get(AgentThread, tid)
        if change == "event":
            add_event(db, clock, thread)
        elif change == "epoch":
            account = db.scalar(select(AccountAgent))
            account.controller_epoch += 1
        elif change == "deletion":
            thread.deletion_generation += 1
        else:
            thread.handling_mode = "human"
        db.commit()
    with session_factory() as db:
        assert fresh(db, runner, claimed) is None
        db.commit()
    with session_factory() as db:
        assert db.get(AgentStep, claimed.step_id).status == "stale"


def test_event_committed_before_running_wake_finalizes_gets_own_job(session_factory, clock):
    ws, tid = seed(session_factory, clock)
    job = claim_one(session_factory, clock, "busy", 120)
    assert job is not None
    with session_factory() as db:
        add_event(db, clock, db.get(AgentThread, tid))
        db.commit()
    with session_factory() as db:
        jobs = db.scalars(select(Job).where(Job.job_type == "agent_wake")).all()
        assert len(jobs) == 2
        assert {item.status for item in jobs} == {"running", "queued"}
        assert len({item.dedup_key for item in jobs}) == 2


def test_customer_wait_survives_days_and_resumes_on_customer_event(session_factory, clock):
    ws, tid = seed(session_factory, clock)
    fake = FakeLLMProvider()
    fake.queue_step(result("wait", wait_for="customer"))
    runner = deps(session_factory, clock, fake)
    run_activation(runner, ws, tid, build_default_broker())
    clock.advance(timedelta(days=30))
    assert claim(runner, ws, tid) is None
    with session_factory() as db:
        thread = db.get(AgentThread, tid)
        add_event(db, clock, thread)
        db.commit()
    fake.queue_step(result())
    run_activation(deps(session_factory, clock, fake), ws, tid, build_default_broker())
    with session_factory() as db:
        goal = db.scalar(select(AgentSession))
        assert goal.status == "completed" and goal.model_steps == 2 and goal.activation_steps == 1


def test_invalid_owner_wait_fails_closed(session_factory, clock):
    ws, tid = seed(session_factory, clock)
    fake = FakeLLMProvider()
    fake.queue_step(result("wait", wait_for="owner", metadata={"reference_id": str(uuid.uuid4())}))
    run_activation(deps(session_factory, clock, fake), ws, tid, build_default_broker())
    with session_factory() as db:
        goal = db.scalar(select(AgentSession))
        assert goal.status == "failed" and goal.outcome_code == "AGENT_WAIT_INVALID"


def test_repeated_identical_tool_hands_off_with_persisted_counter(session_factory, clock):
    ws, tid = seed(session_factory, clock)
    fake = FakeLLMProvider()
    for _ in range(5):
        fake.queue_step(
            result("tool", tool_name="knowledge.read", tool_arguments={"limit": 2, "cursor": None})
        )
    run_activation(deps(session_factory, clock, fake), ws, tid, build_default_broker())
    with session_factory() as db:
        goal = db.scalar(select(AgentSession))
        assert goal.status == "failed" and goal.outcome_code == "AGENT_LOOP_LIMIT"
        assert goal.tool_calls == 3 and goal.model_steps == 4


def test_restart_within_activation_recovers_abandoned_claim(session_factory, clock):
    ws, tid = seed(session_factory, clock)
    runner = deps(session_factory, clock)
    first = claim(runner, ws, tid)
    assert first is not None
    clock.advance(timedelta(seconds=91))
    fake = FakeLLMProvider()
    fake.queue_step(result())
    run_activation(deps(session_factory, clock, fake), ws, tid, build_default_broker())
    with session_factory() as db:
        assert db.get(AgentStep, first.step_id).status == "abandoned"
        goal = db.scalar(select(AgentSession))
        assert goal.status == "completed" and goal.model_steps == 2
        assert len(db.scalars(select(AgentStep)).all()) == 2


def test_committed_read_checkpoint_survives_worker_restart(session_factory, clock):
    from app.agent.coordinator import step_state

    ws, tid = seed(session_factory, clock)
    runner = deps(session_factory, clock)
    first = claim(runner, ws, tid)
    with session_factory() as db:
        step = db.get(AgentStep, first.step_id)
        step_state(db, runner, step, "model_done")
        step.read_checkpoint = {"name": "knowledge.read", "arguments": {"limit": 2, "cursor": None}}
        step_state(db, runner, step, "dispatched")
        step_state(db, runner, step, "consumed")
        db.commit()
    fake = FakeLLMProvider()
    fake.queue_step(result())
    run_activation(deps(session_factory, clock, fake), ws, tid, build_default_broker())
    assert fake.step_calls[0].observations[0].name == "knowledge.read"
    with session_factory() as db:
        goal = db.scalar(select(AgentSession))
        assert goal.model_steps == 2 and goal.status == "completed"


def test_scheduled_wake_uses_durable_job_after_restart(session_factory, clock, monkeypatch):
    from app.agent.coordinator import sleep_until

    ws, tid = seed(session_factory, clock)
    runner = deps(session_factory, clock)
    claimed = claim(runner, ws, tid)
    with session_factory() as db:
        step = db.get(AgentStep, claimed.step_id)
        step.status = "consumed"
        goal = db.get(AgentSession, step.session_id)
        sleep_until(db, runner, goal, db.get(AgentThread, tid), clock.now() + timedelta(days=1))
        db.commit()
    clock.advance(timedelta(days=1))
    fake = FakeLLMProvider()
    fake.queue_step(result())
    monkeypatch.setattr("app.agent.jobs.deps_for", lambda _: deps(session_factory, clock, fake))
    for _ in range(5):
        job = claim_one(session_factory, clock, "recreated", 120)
        if job is None:
            break
        assert execute_job(session_factory, clock, job, lease_seconds=120) == "succeeded"
    with session_factory() as db:
        goal = db.scalar(select(AgentSession))
        assert goal.status == "completed" and goal.model_steps == 2
        assert goal.activation_steps == 1


def test_recovery_does_not_starve_behind_indefinite_waits(session_factory, clock):
    from app.agent.jobs import AgentRecoverPayload, agent_recover
    from app.jobs.registry import JobContext

    ws, tid = seed(session_factory, clock)
    runner = deps(session_factory, clock)
    claim(runner, ws, tid)
    with session_factory() as db:
        thread = db.get(AgentThread, tid)
        for _ in range(201):
            other = AgentThread(
                workspace_id=ws,
                social_account_id=thread.social_account_id,
                surface="owner_task",
                source_ref=uuid.uuid4().hex,
                state="waiting_customer",
            )
            db.add(other)
            db.flush()
            db.add(
                AgentSession(
                    workspace_id=ws,
                    thread_id=other.id,
                    goal_key=uuid.uuid4().hex,
                    initiating_event_cursor=0,
                    status="waiting_customer",
                )
            )
        db.commit()
    agent_recover(
        JobContext(
            uuid.uuid4(),
            "agent_recover",
            None,
            None,
            AgentRecoverPayload(),
            1,
            3,
            session_factory,
            clock,
            lambda: None,
        )
    )
    with session_factory() as db:
        jobs = db.scalars(select(Job).where(Job.dedup_key.like("%recover:%"))).all()
        assert len(jobs) == 1 and jobs[0].payload["thread_id"] == str(tid)


def test_committed_intent_is_not_duplicated_after_worker_crash(session_factory, clock):
    from pydantic import BaseModel, ConfigDict

    from app.agent.models import AgentAction, AgentEvent
    from app.agent.repository import admit_action
    from app.agent.tools.broker import ToolBroker, ToolSpec

    class Args(BaseModel):
        model_config = ConfigDict(extra="forbid")

    def handler(db, local_clock, context, _args):
        goal = db.scalar(select(AgentSession).where(AgentSession.thread_id == context.thread_id))
        event = db.scalar(select(AgentEvent).where(AgentEvent.thread_id == context.thread_id))
        action = admit_action(
            db,
            workspace_id=context.workspace.workspace_id,
            account_id=context.account_id,
            thread_id=context.thread_id,
            session_id=goal.id,
            source_event_id=event.id,
            action_type="content.prepare",
            target_ref="own",
            semantic_slot="one",
            payload_hash="a" * 64,
            clock=local_clock,
        )
        return {"action_id": str(action.id)}

    broker = ToolBroker()
    broker.register(
        ToolSpec(
            "test.intent",
            "v1",
            "Offline intent",
            "internal_write",
            frozenset({"owner_task"}),
            frozenset({"owner_task"}),
            Args,
            handler,
        )
    )
    ws, tid = seed(session_factory, clock)
    fake = FakeLLMProvider()
    fake.queue_step(result("tool", tool_name="test.intent"))
    fake.queue_step(RuntimeError("worker killed after committed intent"))
    with pytest.raises(RuntimeError):
        run_activation(deps(session_factory, clock, fake), ws, tid, broker)
    clock.advance(timedelta(seconds=91))
    restarted = FakeLLMProvider()
    restarted.queue_step(result("tool", tool_name="test.intent"))
    restarted.queue_step(result())
    run_activation(deps(session_factory, clock, restarted), ws, tid, broker)
    with session_factory() as db:
        assert len(db.scalars(select(AgentAction)).all()) == 1
        assert db.scalar(select(AgentSession)).status == "completed"


def test_echo_is_not_a_conversational_event(session_factory, clock):
    from app.agent.repository import AgentScopeError

    ws, tid = seed(session_factory, clock)
    with session_factory() as db:
        thread = db.get(AgentThread, tid)
        with pytest.raises(AgentScopeError):
            add_event_and_wake(
                db,
                workspace_id=ws,
                account_id=thread.social_account_id,
                thread_id=tid,
                kind="echo",
                source_kind="message",
                source_key=uuid.uuid4().hex,
                source_id=None,
                source_version=1,
                clock=clock,
            )
        assert thread.event_cursor == 1


def test_stale_result_charges_usage_without_tool_dispatch_or_open_transaction(
    session_factory, clock
):
    ws, tid = seed(session_factory, clock)

    class InboundDuringModel(FakeLLMProvider):
        def generate_step(self, request):
            assert session_factory.kw["bind"].pool.checkedout() == 0
            with session_factory() as db:
                add_event(db, clock, db.get(AgentThread, tid))
                db.commit()
            return result(
                "tool", tool_name="knowledge.read", tool_arguments={"limit": 2, "cursor": None}
            )

    run_activation(
        deps(session_factory, clock, InboundDuringModel()), ws, tid, build_default_broker()
    )
    with session_factory() as db:
        goal = db.scalar(select(AgentSession))
        step = db.scalar(select(AgentStep))
        assert step.status == "stale" and step.read_checkpoint is None
        assert goal.input_tokens == 4 and goal.output_tokens == 2 and goal.tool_calls == 0


def test_transient_model_failure_retries_without_resetting_activation(
    session_factory, clock, monkeypatch
):
    from app.integrations.llm.errors import LLMTransientError

    ws, tid = seed(session_factory, clock)
    fake = FakeLLMProvider()
    fake.queue_step(LLMTransientError("offline unavailable"))
    fake.queue_step(result())
    monkeypatch.setattr("app.agent.jobs.deps_for", lambda _: deps(session_factory, clock, fake))
    job = claim_one(session_factory, clock, "one", 120)
    assert execute_job(session_factory, clock, job, lease_seconds=120) == "retry"
    clock.advance(timedelta(seconds=20))
    job = claim_one(session_factory, clock, "two", 120)
    assert execute_job(session_factory, clock, job, lease_seconds=120) == "succeeded"
    with session_factory() as db:
        goal = db.scalar(select(AgentSession))
        assert goal.status == "completed" and goal.activation_steps == 2 and goal.model_steps == 2
