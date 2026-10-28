"""Operator evidence through actual wake jobs, with a poisoned private link."""

import pytest
from sqlalchemy import select

from app.agent.models import AgentSession, AgentThread
from app.inbox.models import Conversation, Message
from app.integrations.llm.fake import FakeLLMProvider
from tests.integration.agent.test_comments import deliver
from tests.integration.agent.test_coordinator import deps, result
from tests.integration.agent.test_dm import drain, setup

pytestmark = pytest.mark.commits


def test_public_wake_job_never_reads_linked_private_dm(session_factory, clock, monkeypatch):
    world = setup(session_factory, clock)
    fake = FakeLLMProvider()
    fake.queue_step(
        result("tool", tool_name="public.thread", tool_arguments={"limit": 2, "cursor": None})
    )
    fake.queue_step(result())
    monkeypatch.setattr("app.agent.jobs.deps_for", lambda _: deps(session_factory, clock, fake))
    deliver(session_factory, clock, world, text="PUBLIC CUSTOMER REQUEST")
    with session_factory() as db:
        conversation = Conversation(
            workspace_id=world[0].workspace_id,
            social_account_id=world[1],
            customer_external_id="private-customer",
            last_inbound_at=clock.now(),
        )
        db.add(conversation)
        db.flush()
        db.add(
            Message(
                workspace_id=world[0].workspace_id,
                social_account_id=world[1],
                conversation_id=conversation.id,
                direction="inbound",
                sender_kind="customer",
                external_message_id="private-mid",
                text="PRIVATE BILLING SECRET 918273",
                provider_timestamp=clock.now(),
            )
        )
        thread = db.scalar(select(AgentThread).where(AgentThread.surface == "comment"))
        thread.dm_conversation_id = conversation.id
        db.commit()
    drain(session_factory, clock)
    assert len(fake.step_calls) == 2
    for request in fake.step_calls:
        assert "PUBLIC CUSTOMER REQUEST" in str(request.messages)
        assert "PRIVATE BILLING SECRET" not in str(request)
        assert not {tool.name for tool in request.tools} & {
            "thread.read",
            "memory.read",
            "memory.write",
            "owner.ask",
            "dm.send",
            "approval.request",
        }
    with session_factory() as db:
        assert db.scalar(select(AgentSession)).status == "completed"
