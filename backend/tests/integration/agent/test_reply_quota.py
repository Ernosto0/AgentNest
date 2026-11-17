"""P-11: the monthly AI reply allowance on the account agent's direct-message path.

The agent is skipped before any model call once the grace is used up; the customer's message
still arrives and the owner is told; nothing stays stuck; the agent answers again as soon as the
allowance does.
"""

import uuid

import pytest
from sqlalchemy import select

from app.agent.coordinator import claim
from app.agent.dm import send
from app.agent.grounding import ReplyValidationArgs
from app.agent.models import AgentSession, AgentThread
from app.agent.tools.broker import BrokerContext
from app.inbox.models import Conversation, InboundEvent, Message, ReplyDraft
from app.inbox.processing import process_inbound_event
from app.integrations.instagram.models import SimSentMessage
from app.integrations.llm.fake import FakeLLMProvider
from app.jobs.models import Job
from app.notifications.models import Notification
from app.plans import service
from tests.integration.agent.test_coordinator import deps, result
from tests.integration.agent.test_dm import deliver, drain, reply, setup

pytestmark = pytest.mark.commits


def set_plan(factory, clock, workspace_id, *, quota=None, used=None):
    with factory() as db:
        row = service.get_plan(db, clock, workspace_id)
        if quota is not None:
            row.quota_override = quota
        if used is not None:
            row.used = used
        db.commit()


def usage(factory, clock, workspace_id):
    with factory() as db:
        row = service.get_plan(db, clock, workspace_id)
        db.commit()
        return row.used, service.state(row)


def notifications(factory, kind):
    with factory() as db:
        return list(db.scalars(select(Notification).where(Notification.type == kind)))


def test_an_agent_reply_is_counted_once(session_factory, clock, monkeypatch):
    world = setup(session_factory, clock)
    set_plan(session_factory, clock, world[0].workspace_id, quota=100, used=0)
    fake = FakeLLMProvider()
    monkeypatch.setattr("app.agent.jobs.deps_for", lambda _: deps(session_factory, clock, fake))
    deliver(session_factory, clock, world)
    reply(fake)
    fake.queue_step(result())
    drain(session_factory, clock)
    with session_factory() as db:
        assert len(db.scalars(select(SimSentMessage)).all()) == 1
    assert usage(session_factory, clock, world[0].workspace_id) == (1, "normal")


def test_a_paused_workspace_skips_the_model_but_keeps_the_message_and_tells_the_owner(
    session_factory, clock, monkeypatch
):
    world = setup(session_factory, clock)
    workspace_id = world[0].workspace_id
    set_plan(session_factory, clock, workspace_id, quota=10, used=11)  # the grace is used up
    fake = FakeLLMProvider()
    monkeypatch.setattr("app.agent.jobs.deps_for", lambda _: deps(session_factory, clock, fake))
    deliver(session_factory, clock, world, "Hello, what services do you offer?")
    drain(session_factory, clock)  # asserts that every job succeeded: nothing is stuck

    assert fake.step_calls == []  # no model call
    with session_factory() as db:
        assert db.scalars(select(SimSentMessage)).all() == []
        assert db.scalars(select(ReplyDraft)).all() == []
        (message,) = db.scalars(select(Message).where(Message.direction == "inbound")).all()
        assert message.text == "Hello, what services do you offer?"
        goal = db.scalar(select(AgentSession))
        assert (goal.status, goal.outcome_code) == ("failed", "REPLY_QUOTA_PAUSED")
        assert db.scalar(select(Conversation)).attention == "needs_human"
        assert all(j.status == "succeeded" for j in db.scalars(select(Job)))
        waiting = list(
            db.scalars(select(Notification).where(Notification.type == "conversation.needs_human"))
        )
        assert waiting and all(n.params["reasons"] == ["REPLY_QUOTA_PAUSED"] for n in waiting)
    assert len(notifications(session_factory, "quota.paused")) >= 1
    assert usage(session_factory, clock, workspace_id)[0] == 11  # nothing counted


def test_the_agent_answers_again_when_the_plan_changes(session_factory, clock, monkeypatch):
    world = setup(session_factory, clock)
    workspace_id = world[0].workspace_id
    set_plan(session_factory, clock, workspace_id, quota=10, used=11)
    fake = FakeLLMProvider()
    monkeypatch.setattr("app.agent.jobs.deps_for", lambda _: deps(session_factory, clock, fake))
    deliver(session_factory, clock, world, "Hello, what services do you offer?")
    drain(session_factory, clock)
    assert fake.step_calls == []

    set_plan(session_factory, clock, workspace_id, quota=100)  # the operator changed the plan
    deliver(session_factory, clock, world, "Anyone there? I would like an answer.")
    reply(fake)
    fake.queue_step(result())
    drain(session_factory, clock)
    with session_factory() as db:
        assert len(db.scalars(select(SimSentMessage)).all()) == 1
    assert usage(session_factory, clock, workspace_id) == (12, "normal")


def test_the_last_slot_goes_to_one_draft_only(session_factory, clock):
    """Two proposals past the claim check (both started while 109 of 110 were used)."""
    world = setup(session_factory, clock)
    workspace_id = world[0].workspace_id
    set_plan(session_factory, clock, workspace_id, quota=100, used=109)
    deliver(session_factory, clock, world, customer="customer-one")
    deliver(session_factory, clock, world, customer="customer-two")
    # Store both messages without running any queued job (a wake job would draft and spend
    # the slot before the test proposes anything).
    with session_factory() as db:
        for event in db.scalars(select(InboundEvent)).all():
            process_inbound_event(db, clock, workspace_id, event.id, debounce_seconds=0)
        db.commit()
    with session_factory() as db:
        threads = list(db.scalars(select(AgentThread)))
        assert len(threads) == 2
    contexts = []
    for thread in threads:  # both are claimed while 109 of 110 are used
        assert claim(deps(session_factory, clock), workspace_id, thread.id) is not None
        contexts.append(BrokerContext(world[0], world[1], thread.id, "dm", "customer"))
    args = ReplyValidationArgs(template="Hello! How can I help?", language="en")
    outcomes = []
    for context in contexts:
        with session_factory() as db:
            outcomes.append(send(db, clock, context, args))
            db.commit()
    statuses = [o.get("status") for o in outcomes]
    assert statuses.count("quota_paused") == 1
    assert usage(session_factory, clock, workspace_id) == (110, "paused")
    with session_factory() as db:
        assert len(db.scalars(select(ReplyDraft)).all()) == 1  # no half-created draft
    assert uuid.UUID(str(workspace_id))
