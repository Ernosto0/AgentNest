"""Operator tests for source-bound numeric clarification through the real send job."""

import pytest
from sqlalchemy import select

from app.agent.delegation import apply
from app.agent.grounding import CustomerClarification, ReplyValidationArgs
from app.agent.models import AccountAgent, AgentThread
from app.inbox.models import Message, ReplyDraft
from app.integrations.instagram.models import SimSentMessage
from app.integrations.llm.fake import FakeLLMProvider
from app.jobs.queue import claim_one
from app.jobs.worker import execute_job
from tests.integration.agent.test_coordinator import deps, result
from tests.integration.agent.test_delegation import _change, _policy
from tests.integration.agent.test_dm import deliver, drain, reply, setup

pytestmark = pytest.mark.commits


@pytest.mark.parametrize("delete_before_dispatch", [False, True])
def test_customer_date_send_revalidates_domain_source(
    session_factory, clock, monkeypatch, delete_before_dispatch
):
    world = setup(session_factory, clock)

    class ClarificationFake(FakeLLMProvider):
        def generate_step(self, request):
            if not self.step_calls:
                with session_factory() as db:
                    message = db.scalar(select(Message).where(Message.direction == "inbound"))
                    start = message.text.index("2026-11-03")
                    proposal = ReplyValidationArgs(
                        template="",
                        language="en",
                        customer_clarification=CustomerClarification(
                            message_id=message.id, start=start, end=start + 10, kind="date"
                        ),
                    )
                self.queue_step(
                    result(
                        "tool", tool_name="dm.send", tool_arguments=proposal.model_dump(mode="json")
                    )
                )
                self.queue_step(result())
            return super().generate_step(request)

    fake = ClarificationFake()
    monkeypatch.setattr("app.agent.jobs.deps_for", lambda _: deps(session_factory, clock, fake))
    deliver(session_factory, clock, world, "Hello, I prefer 2026-11-03. Can you help?")
    for _ in range(12):
        job = claim_one(session_factory, clock, "projection-worker", 120)
        assert job is not None
        assert execute_job(session_factory, clock, job, lease_seconds=120) == "succeeded"
        with session_factory() as db:
            draft = db.scalar(select(ReplyDraft))
            if draft is not None:
                assert draft.status == "queued"
                assert draft.text.startswith("You mentioned") and "2026-11-03" in draft.text
                if delete_before_dispatch:
                    source = db.scalar(select(Message).where(Message.direction == "inbound"))
                    source.is_deleted = True
                    db.commit()
                break
    else:
        pytest.fail("agent did not project clarification")
    drain(session_factory, clock)
    with session_factory() as db:
        sent = db.scalars(select(SimSentMessage)).all()
        assert len(sent) == (0 if delete_before_dispatch else 1)
        assert db.scalar(select(ReplyDraft)).status == (
            "cancelled" if delete_before_dispatch else "sent"
        )


@pytest.mark.parametrize("interrupt", ["revocation", "native_echo"])
def test_queued_agent_send_is_fenced_before_remote_dispatch(
    session_factory, clock, monkeypatch, interrupt
):
    world = setup(session_factory, clock)
    fake = FakeLLMProvider()
    reply(fake)
    fake.queue_step(result())
    monkeypatch.setattr("app.agent.jobs.deps_for", lambda _: deps(session_factory, clock, fake))
    deliver(session_factory, clock, world)
    for _ in range(12):
        job = claim_one(session_factory, clock, "proposal-worker", 120)
        assert job is not None
        assert execute_job(session_factory, clock, job, lease_seconds=120) == "succeeded"
        with session_factory() as db:
            if db.scalar(select(ReplyDraft.id)) is not None:
                break
    else:
        pytest.fail("no queued proposal")
    if interrupt == "revocation":
        with session_factory() as db:
            account = db.scalar(select(AccountAgent))
            from app.agent.delegation import current_delegation

            delegation = current_delegation(db, world[0].workspace_id, world[1])
            apply(
                db,
                clock,
                world[0],
                world[1],
                _change(_policy(dm="off"), account.config_version, delegation.version),
            )
            db.commit()
    else:
        from app.inbox.models import InboundEvent
        from app.inbox.processing import process_inbound_event

        deliver(session_factory, clock, world, "The owner replied natively", echo=True)
        with session_factory() as db:
            inbound = db.scalar(select(InboundEvent).where(InboundEvent.status == "received"))
            process_inbound_event(db, clock, world[0].workspace_id, inbound.id, debounce_seconds=0)
    drain(session_factory, clock)
    with session_factory() as db:
        assert not db.scalars(select(SimSentMessage)).all()
        assert db.scalar(select(ReplyDraft)).status in {"cancelled", "superseded"}
        if interrupt == "native_echo":
            assert db.scalar(select(AgentThread)).handling_mode == "human"
