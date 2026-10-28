"""Scripted multi-turn fixture mechanics through real durable job execution."""

from datetime import timedelta
from pathlib import Path

import pytest
import yaml
from sqlalchemy import select

from app.agent.models import AccountAgent, AgentSession
from app.agent.repository import add_event_and_wake
from app.inbox.models import Message
from app.integrations.llm.fake import FakeLLMProvider
from app.jobs.queue import claim_one
from app.jobs.worker import execute_job
from tests.integration.agent.test_context_grounding import fact, scenario
from tests.integration.agent.test_coordinator import deps, result

FIXTURE = Path(__file__).parents[3] / "evals/account_agent/initial_journeys.yaml"
JOURNEYS = yaml.safe_load(FIXTURE.read_text(encoding="utf-8"))["journeys"]


@pytest.mark.commits
@pytest.mark.parametrize("journey", JOURNEYS, ids=lambda row: row["id"])
def test_initial_two_turn_journey_uses_actual_jobs(session_factory, clock, monkeypatch, journey):
    with session_factory() as db:
        context, workspace, inbound = scenario(db, clock, language=journey["language"])
        workspace.business_category = journey["category"]
        inbound.text = journey["turns"][0]
        service = fact(db, workspace, text=journey["service"])
        account = db.scalar(
            select(AccountAgent).where(AccountAgent.social_account_id == context.account_id)
        )
        account.state, account.controller_mode = "active", "agent"
        add_event_and_wake(
            db,
            workspace_id=workspace.id,
            account_id=context.account_id,
            thread_id=context.thread_id,
            kind="customer_message",
            source_kind="message",
            source_key=str(inbound.id),
            source_id=str(inbound.id),
            source_version=1,
            clock=clock,
        )
        db.commit()
    fake = FakeLLMProvider()
    fake.queue_step(
        result(
            "tool",
            tool_name="reply.validate",
            tool_arguments={
                "template": journey["greeting"],
                "language": journey["language"],
                "fact_sources": [],
                "customer_clarification": None,
            },
        )
    )
    fake.queue_step(result("wait", wait_for="customer"))
    monkeypatch.setattr("app.agent.jobs.deps_for", lambda _: deps(session_factory, clock, fake))
    job = claim_one(session_factory, clock, "first-worker", 120)
    assert execute_job(session_factory, clock, job, lease_seconds=120) == "succeeded"
    assert fake.step_calls[1].observations[0].result["data"]["valid"] is True
    clock.advance(timedelta(seconds=1))
    with session_factory() as db:
        second = Message(
            workspace_id=workspace.id,
            social_account_id=context.account_id,
            conversation_id=inbound.conversation_id,
            direction="inbound",
            sender_kind="customer",
            text=journey["turns"][1],
            provider_timestamp=clock.now(),
        )
        db.add(second)
        db.flush()
        add_event_and_wake(
            db,
            workspace_id=workspace.id,
            account_id=context.account_id,
            thread_id=context.thread_id,
            kind="customer_message",
            source_kind="message",
            source_key=str(second.id),
            source_id=str(second.id),
            source_version=1,
            clock=clock,
        )
        db.commit()
    fake.queue_step(
        result(
            "tool",
            tool_name="reply.validate",
            tool_arguments={
                "template": journey["reply"],
                "language": journey["language"],
                "fact_sources": [{"id": str(service.id), "version": service.current_version}],
                "customer_clarification": None,
            },
        )
    )
    fake.queue_step(result())
    job = claim_one(session_factory, clock, "recreated-worker", 120)
    assert execute_job(session_factory, clock, job, lease_seconds=120) == "succeeded"
    output = fake.step_calls[3].observations[0].result["data"]
    assert output["valid"] is True and journey["service"] in output["text"]
    with session_factory() as db:
        goal = db.scalar(select(AgentSession))
        assert goal.status == "completed" and goal.model_steps == 4
