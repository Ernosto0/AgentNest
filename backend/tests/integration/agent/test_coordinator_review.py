"""Operator regressions for shared quota and approval cleanup contention."""

import uuid
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from types import SimpleNamespace

import pytest
from sqlalchemy import select, text

from app.agent.delegation import apply, authorize_action
from app.agent.jobs import AgentCleanupPayload, cleanup_approvals
from app.agent.models import AgentAction
from app.ai.runner import RunnerDeps, run_task
from app.ai.step_runner import run_step
from app.approvals import service as approvals
from app.approvals.models import Approval
from app.core.config import Settings
from app.core.errors import AppError
from app.integrations.llm.errors import LLMInvalidOutput
from app.integrations.llm.fake import FakeLLMProvider
from app.integrations.llm.steps import LLMStepRequest
from app.jobs.registry import JobContext
from tests.factories import knowledge_ctx, workspace_with_members
from tests.integration.agent.test_delegation import _account, _action, _change, _policy
from tests.integration.agent.test_step_runner import _seed
from tests.integration.ai.test_runner import In, _definition


@pytest.mark.commits
def test_inbound_during_model_call_discards_tool_and_runs_next_wake(
    session_factory, clock, monkeypatch
):
    from app.agent.models import AgentSession, AgentStep, AgentThread
    from app.jobs.queue import claim_one
    from app.jobs.worker import execute_job
    from tests.integration.agent.test_coordinator import add_event, deps, result, seed

    workspace_id, thread_id = seed(session_factory, clock)

    class InterruptingFake(FakeLLMProvider):
        def generate_step(self, request):
            if not self.step_calls:
                with session_factory() as db:
                    add_event(db, clock, db.get(AgentThread, thread_id))
                    db.commit()
            return super().generate_step(request)

    fake = InterruptingFake()
    fake.queue_step(
        result("tool", tool_name="knowledge.read", tool_arguments={"limit": 2, "cursor": None})
    )
    fake.queue_step(result())
    monkeypatch.setattr("app.agent.jobs.deps_for", lambda _: deps(session_factory, clock, fake))
    for _ in range(2):
        job = claim_one(session_factory, clock, "operator-review", 120)
        assert job is not None
        assert execute_job(session_factory, clock, job, lease_seconds=120) == "succeeded"
    assert len(fake.step_calls) == 2
    with session_factory() as db:
        goal = db.scalar(select(AgentSession).where(AgentSession.workspace_id == workspace_id))
        assert goal.status == "completed" and goal.tool_calls == 0
        assert goal.input_tokens == 8
        assert {step.status for step in db.scalars(select(AgentStep))} == {"stale", "consumed"}


def test_denied_agent_repair_does_not_refund_legacy_quota(
    db_session, shared_session_factory, clock
):
    ctx, step_id = _seed(db_session)
    fake = FakeLLMProvider()
    fake.queue_step(LLMInvalidOutput("invalid"))
    deps = RunnerDeps(
        shared_session_factory,
        clock,
        fake,
        Settings(_env_file=None, llm_provider="fake", llm_max_calls_per_workspace_per_day=1),
    )
    request = LLMStepRequest(
        task="account_agent_step", model="fake", system="trusted", messages=(), tools=()
    )
    assert run_step(deps, ctx, step_id, request).error_code == "LLM_BUDGET_EXCEEDED"
    legacy = run_task(deps, ctx, _definition(), In(1))
    assert legacy.error_code == "LLM_BUDGET_EXCEEDED"
    assert len(fake.step_calls) == 1 and len(fake.calls) == 0


@pytest.mark.commits
def test_policy_cleanup_races_stale_human_decision_without_deadlock(session_factory, clock):
    with session_factory() as db:
        workspace, users = workspace_with_members(db)
        ctx = knowledge_ctx(workspace, users["owner"], "owner")
        env = SimpleNamespace(session=db, workspace=workspace)
        social, account = _account(env)
        first = apply(
            db, clock, ctx, social.id, _change(_policy(dm="ask"), account.config_version, None)
        )
        account.state, account.controller_mode = "active", "agent"
        action = _action(env, social, account, "dm.send")
        assert (
            authorize_action(
                db,
                clock,
                ctx,
                action.id,
                source="customer",
                target_owned=True,
                visibility_allowed=True,
                claims_valid=True,
                quota_available=True,
            ).kind
            == "ask"
        )
        approval_id, action_id, account_id = action.approval_id, action.id, social.id
        payload_hash = action.payload_hash
        apply(
            db,
            clock,
            ctx,
            social.id,
            _change(_policy(dm="off"), account.config_version, first.version),
        )
        db.commit()

    barrier = Barrier(2)

    def decide():
        with session_factory() as db:
            db.execute(text("SET LOCAL lock_timeout = '3s'"))
            barrier.wait(timeout=5)
            with pytest.raises(AppError, match="APPROVAL_STALE|APPROVAL_ALREADY_DECIDED"):
                approvals.decide(
                    db, clock, ctx, approval_id, decision="approve", payload_hash=payload_hash
                )
            db.rollback()

    def cleanup():
        barrier.wait(timeout=5)
        cleanup_approvals(
            JobContext(
                uuid.uuid4(),
                "agent_cleanup_approvals",
                ctx.workspace_id,
                None,
                AgentCleanupPayload(account_id=account_id),
                1,
                3,
                session_factory,
                clock,
                lambda: None,
            )
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(decide), pool.submit(cleanup)]
        for future in futures:
            future.result(timeout=10)
    with session_factory() as db:
        assert db.get(Approval, approval_id).status == "cancelled"
        assert (
            db.scalar(select(AgentAction).where(AgentAction.id == action_id)).status == "cancelled"
        )
