"""Final review: configured expiry and preserving human authority during memory changes."""

import uuid
from datetime import timedelta

import pytest
from sqlalchemy import select

from app.agent.coordinator import claim, run_activation
from app.agent.dm import send
from app.agent.grounding import ReplyValidationArgs
from app.agent.jobs import AgentCleanupPayload, cleanup_approvals
from app.agent.models import AgentAction, AgentThread
from app.agent.tools.broker import build_default_broker
from app.approvals import service as approvals
from app.approvals.models import Approval
from app.approvals.views import approval_out
from app.core.errors import AppError
from app.inbox.models import Message, ReplyDraft
from app.integrations.llm.fake import FakeLLMProvider
from app.jobs.models import Job
from app.jobs.registry import JobContext
from app.memory import service
from app.memory.models import CustomerIdentity, CustomerMemory
from tests.integration.agent.test_coordinator import deps, result
from tests.integration.agent.test_dm import deliver, process_inbound, setup
from tests.integration.agent.test_memory import learn, owner, prepared


def test_configured_seven_day_expiry_applies_to_write_correction_and_reads(
    db_session, clock, settings, monkeypatch
):
    monkeypatch.setattr(
        service,
        "get_settings",
        lambda: settings.model_copy(update={"retention_customer_memory_days": 7}),
    )
    ctx, identity, source = prepared(db_session, clock)
    memory_id = uuid.UUID(learn(db_session, clock, ctx, source)["memory_id"])
    memory = db_session.get(CustomerMemory, memory_id)
    assert memory.expires_at == clock.now() + timedelta(days=7)
    clock.advance(days=1)
    service.change(
        db_session,
        clock,
        owner(ctx),
        ctx.account_id,
        identity.id,
        memory_id,
        service.MemoryChange(expected_version=1, body="I prefer morning schedule."),
    )
    assert memory.expires_at == clock.now() + timedelta(days=7)
    service.private_context(db_session, clock, ctx, "schedule")
    clock.advance(days=7)
    assert service.private_context(db_session, clock, ctx, "schedule")["memories"] == []
    assert (
        service.export_customer(db_session, clock, owner(ctx), ctx.account_id, identity.id)[
            "summaries"
        ]
        == []
    )


@pytest.mark.parametrize("forget", [False, True])
def test_memory_change_preserves_pending_manual_proposal(db_session, clock, forget):
    ctx, identity, source = prepared(db_session, clock)
    memory_id = uuid.UUID(learn(db_session, clock, ctx, source)["memory_id"])
    manual = ReplyDraft(
        workspace_id=source.workspace_id,
        conversation_id=source.conversation_id,
        covers_through_message_id=source.id,
        source="owner",
        origin="legacy",
        status="queued",
        created_by_actor_type="user",
        decision="auto",
        text="A human-written business reply.",
        template="A human-written business reply.",
        validation={"passed": True},
        created_at=clock.now(),
    )
    db_session.add(manual)
    db_session.flush()
    service.change(
        db_session,
        clock,
        owner(ctx),
        ctx.account_id,
        identity.id,
        memory_id,
        None
        if forget
        else service.MemoryChange(expected_version=1, body="I prefer morning schedule."),
    )
    db_session.refresh(manual)
    assert manual.status == "queued" and manual.text == "A human-written business reply."
    assert manual.template == manual.text and manual.validation == {"passed": True}


@pytest.mark.commits
@pytest.mark.parametrize("forget", [False, True])
def test_memory_change_immediately_stales_ask_approval_and_cleanup_closes_it(
    session_factory, clock, forget
):
    world = setup(session_factory, clock, mode="ask")
    deliver(session_factory, clock, world, "I prefer evening schedule.")
    process_inbound(session_factory, clock)
    with session_factory() as db:
        thread_id = db.scalar(select(AgentThread.id))
    captured = claim(deps(session_factory, clock), world[0].workspace_id, thread_id)
    with session_factory() as db:
        source = db.scalar(select(Message).where(Message.direction == "inbound"))
        memory_id = uuid.UUID(learn(db, clock, captured.context, source)["memory_id"])
        identity = db.scalar(select(CustomerIdentity))
        send(
            db,
            clock,
            captured.context,
            ReplyValidationArgs(template="Let us discuss your schedule.", language="en"),
        )
        draft = db.scalar(select(ReplyDraft))
        action = db.scalar(select(AgentAction))
        approval = db.get(Approval, action.approval_id)
        assert approval_out(db, clock, world[0], approval).can_decide
        service.change(
            db,
            clock,
            world[0],
            world[1],
            identity.id,
            memory_id,
            None
            if forget
            else service.MemoryChange(expected_version=1, body="I prefer morning schedule."),
        )
        db.refresh(draft)
        db.refresh(action)
        assert draft.status == action.status == "cancelled"
        assert not approval_out(db, clock, world[0], approval).can_decide
        approval_id, original_hash = approval.id, approval.payload_hash
        assert db.scalar(
            select(Job.id).where(
                Job.dedup_key
                == f"agent_cleanup:{world[1]}:memory:{identity.id}:{identity.generation}"
            )
        )
        db.commit()
    with session_factory() as db, pytest.raises(AppError) as err:
        approvals.decide(
            db, clock, world[0], approval_id, decision="approve", payload_hash=original_hash
        )
    assert err.value.code == "APPROVAL_STALE"
    cleanup_approvals(
        JobContext(
            job_id=uuid.uuid4(),
            job_type="agent_cleanup_approvals",
            workspace_id=world[0].workspace_id,
            correlation_id=None,
            payload=AgentCleanupPayload(account_id=world[1]),
            attempt=1,
            max_attempts=6,
            session_factory=session_factory,
            clock=clock,
            _heartbeat=lambda: None,
        )
    )
    with session_factory() as db:
        assert db.get(Approval, approval_id).status == "cancelled"


@pytest.mark.commits
def test_between_claim_privacy_change_clears_in_process_tool_observations(
    session_factory, clock, monkeypatch
):
    from app.agent import coordinator

    world = setup(session_factory, clock)
    deliver(session_factory, clock, world, "I prefer evening schedule.")
    process_inbound(session_factory, clock)
    with session_factory() as db:
        source_id = db.scalar(select(Message.id).where(Message.direction == "inbound"))
        thread_id = db.scalar(select(AgentThread.id))
    fake = FakeLLMProvider()
    fake.queue_step(
        result(
            "tool",
            tool_name="memory.write",
            tool_arguments={
                "topic": "schedule",
                "kind": "preference",
                "source_message_id": str(source_id),
                "quote": "I prefer evening schedule.",
            },
        )
    )
    fake.queue_step(result())
    original = coordinator.claim
    claims = []

    def intercept(runner, workspace, thread):
        if claims:
            with session_factory() as db:
                identity = db.scalar(select(CustomerIdentity))
                memory = db.scalar(select(CustomerMemory))
                service.change(
                    db,
                    clock,
                    world[0],
                    world[1],
                    identity.id,
                    memory.id,
                    service.MemoryChange(expected_version=1, body="I prefer morning schedule."),
                )
                db.commit()
        claims.append(True)
        return original(runner, workspace, thread)

    monkeypatch.setattr(coordinator, "claim", intercept)
    run_activation(
        deps(session_factory, clock, fake), world[0].workspace_id, thread_id, build_default_broker()
    )
    assert len(fake.step_calls) == 2
    latest = fake.step_calls[1]
    assert latest.observations == ()
    assert "evening" not in latest.messages[0].content
    assert "morning" in latest.messages[0].content
