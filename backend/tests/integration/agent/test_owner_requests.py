"""Signed ingestion -> durable human wait -> scoped answer -> existing send ledger."""

import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import timedelta

import pytest
from sqlalchemy import select

from app.agent.context import assemble
from app.agent.coordinator import valid_wait
from app.agent.grounding import ReplyValidationArgs, validate_reply
from app.agent.jobs import AgentRecoverPayload, agent_recover
from app.agent.models import AgentAction, AgentEvent, AgentSession, AgentStep, AgentThread
from app.agent.tools.broker import BrokerContext
from app.approvals.models import Approval
from app.core.errors import AppError
from app.inbox.models import ReplyDraft
from app.inbox.service import takeover
from app.integrations.instagram.models import SimSentMessage
from app.integrations.llm.fake import FakeLLMProvider
from app.jobs.models import Job
from app.jobs.registry import JobContext
from app.knowledge.models import FactCandidate
from app.memory.service import erase_source
from app.notifications.models import Notification
from app.owner_requests import service
from app.owner_requests.models import OwnerAnswer, OwnerQuestion
from tests.integration.agent.test_coordinator import deps, result
from tests.integration.agent.test_dm import deliver, drain, process_inbound, setup

pytestmark = pytest.mark.commits


def recovery(factory, clock):
    return JobContext(
        job_id=uuid.uuid4(),
        job_type="agent_recover",
        workspace_id=None,
        correlation_id=None,
        payload=AgentRecoverPayload(),
        attempt=1,
        max_attempts=3,
        session_factory=factory,
        clock=clock,
        _heartbeat=lambda: None,
    )


def waiting(
    factory, clock, monkeypatch, *, mode="automatic", holding=False, customer="customer-one"
):
    world = setup(factory, clock, mode)
    fake = FakeLLMProvider()
    monkeypatch.setattr("app.agent.jobs.deps_for", lambda _: deps(factory, clock, fake))
    fake.queue_step(
        result(
            "tool",
            tool_name="owner.ask",
            tool_arguments={
                "question": "Can this customer receive a one-off exception?",
                "required_info": "exception",
                "visibility": "customer_reply",
                "holding_response": holding,
            },
        )
    )
    deliver(factory, clock, world, "Can I receive an exception for my request?", customer=customer)
    drain(factory, clock)
    with factory() as db:
        q = db.scalar(select(OwnerQuestion))
        assert q
        thread = db.get(AgentThread, q.thread_id)
        context = BrokerContext(world[0], world[1], thread.id, "dm", "customer")
        return world, fake, q.id, context


def answer(factory, clock, world, qid, text="A one-off exception is available for 350 TL.", **kw):
    with factory() as db:
        q = db.get(OwnerQuestion, qid)
        a = service.decide(
            db,
            clock,
            world[0],
            world[1],
            qid,
            service.AnswerRequest(
                expected_version=q.version, client_request_id=uuid.uuid4(), body=text, **kw
            ),
        )
        db.commit()
        return a.id, a.version


def queue_answer(fake, aid, version):
    proposal = ReplyValidationArgs(
        template="", language="en", owner_answer={"id": aid, "version": version}
    )
    fake.queue_step(
        result("tool", tool_name="dm.send", tool_arguments=proposal.model_dump(mode="json"))
    )
    fake.queue_step(result())
    return proposal


def test_missing_information_answer_runs_real_jobs_and_mock_ledger(
    session_factory, clock, monkeypatch
):
    world, fake, qid, context = waiting(session_factory, clock, monkeypatch)
    with session_factory() as db:
        goal = db.scalar(select(AgentSession))
        assert goal.status == "waiting_owner" and goal.wake_ref == str(qid)
        assert all(s.status == "consumed" for s in db.scalars(select(AgentStep)))
        assert not db.scalars(select(SimSentMessage)).all()
        before = goal.model_steps
    drain(session_factory, clock)
    aid, version = answer(session_factory, clock, world, qid)
    proposal = queue_answer(fake, aid, version)
    drain(session_factory, clock)
    with session_factory() as db:
        sent = db.scalars(select(SimSentMessage)).all()
        assert len(sent) == 1 and "350 TL" in sent[0].text
        assert db.scalar(select(AgentSession)).model_steps == before + 2
        assert db.scalar(select(AgentAction)).status == "succeeded"
        assert db.scalar(select(ReplyDraft)).validation["agent_proposal"]["owner_answer"][
            "id"
        ] == str(aid)
        assert validate_reply(db, clock, context, proposal).valid
        # The same literal critical price cannot borrow owner-answer authority.
        assert not validate_reply(
            db, clock, context, ReplyValidationArgs(template="It costs 350 TL.", language="en")
        ).valid
        for job in db.scalars(select(Job)):
            assert "350 TL" not in str(job.payload)


def test_concurrent_answer_replay_conflict_and_atomic_wake(session_factory, clock, monkeypatch):
    world, fake, qid, _ = waiting(session_factory, clock, monkeypatch)
    request = service.AnswerRequest(expected_version=1, client_request_id=uuid.uuid4(), body="okay")

    def submit(body):
        with session_factory() as db:
            try:
                a = service.decide(db, clock, world[0], world[1], qid, body)
                db.commit()
                return a.id
            except AppError as exc:
                return exc.code

    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(submit, [request, request]))
    assert results[0] == results[1]
    assert submit(request.model_copy(update={"body": "changed"})) == "VERSION_CONFLICT"
    assert (
        submit(request.model_copy(update={"client_request_id": uuid.uuid4()})) == "VERSION_CONFLICT"
    )
    with session_factory() as db:
        assert len(db.scalars(select(OwnerAnswer)).all()) == 1
        events = db.scalars(select(AgentEvent).where(AgentEvent.kind == "owner_answer")).all()
        assert len(events) == 1
        assert not db.scalars(select(Approval)).all()  # free 'okay' has no action authority
        assert len(db.scalars(select(Job).where(Job.dedup_key.like("%:owner:%"))).all()) == 1
        # Simulate a worker dying after answer commit but before consuming its wake.
        for j in db.scalars(select(Job).where(Job.status == "queued")):
            j.status = "succeeded"
        db.commit()
    queue_answer(fake, results[0], 2)
    agent_recover(recovery(session_factory, clock))
    drain(session_factory, clock)
    with session_factory() as db:
        assert len(db.scalars(select(SimSentMessage)).all()) == 1


@pytest.mark.parametrize(
    "race", ["takeover", "changed_request", "private", "wrong_version", "source_deleted", "expired"]
)
def test_answer_evidence_fails_closed(session_factory, clock, monkeypatch, race):
    world, _, qid, context = waiting(session_factory, clock, monkeypatch)
    aid, version = answer(session_factory, clock, world, qid)
    proposal = ReplyValidationArgs(
        template="", language="en", owner_answer={"id": aid, "version": version}
    )
    with session_factory() as db:
        q = db.get(OwnerQuestion, qid)
        if race == "takeover":
            takeover(db, clock, world[0], db.get(AgentThread, q.thread_id).dm_conversation_id)
        elif race == "private":
            q.visibility = "private_business"
        elif race == "wrong_version":
            proposal.owner_answer.version += 1
        elif race == "source_deleted":
            from app.inbox.models import Message

            erase_source(db, clock, db.get(Message, q.source_message_id))
        elif race == "expired":
            clock.advance(timedelta(days=8))
        db.commit()
    if race == "changed_request":
        deliver(session_factory, clock, world, "Actually I want something completely different.")
        process_inbound(session_factory, clock)
    with session_factory() as db:
        assert not validate_reply(db, clock, context, proposal).valid
        assert service.private_answers(db, clock, replace(context, surface="comment")) == []
        if race != "wrong_version":
            assert (
                "350 TL"
                not in assemble(db, clock, replace(context, surface="dm")).messages[0].content
            )


def test_staff_can_propose_only_and_reusable_is_unverified(session_factory, clock, monkeypatch):
    world, _, qid, _ = waiting(session_factory, clock, monkeypatch)
    from app.core.context import ActorRef
    from app.identity.models import User, WorkspaceMember

    with session_factory() as db:
        from tests.factories import create_user

        user = create_user(db)
        staff = WorkspaceMember(workspace_id=world[0].workspace_id, user_id=user.id, role="staff")
        db.add(staff)
        db.flush()
        assert db.get(User, staff.user_id)
        ctx = replace(world[0], actor=ActorRef.user(staff.user_id), role="staff")
        request = service.AnswerRequest(
            expected_version=1, client_request_id=uuid.uuid4(), body="Perhaps yes.", kind="proposal"
        )
        a = service.decide(db, clock, ctx, world[1], qid, request)
        db.commit()
        assert a.kind == "proposal" and db.get(OwnerQuestion, qid).state == "pending"
        with pytest.raises(AppError, match="FORBIDDEN"):
            service.decide(
                db, clock, ctx, world[1], qid, request.model_copy(update={"kind": "answer"})
            )
    aid, _ = answer(
        session_factory,
        clock,
        world,
        qid,
        reusable_knowledge=service.ReusableKnowledge(
            key="custom.exception", text="Ask the business about exceptions."
        ),
    )
    with session_factory() as db:
        c = db.scalar(select(FactCandidate))
        assert (
            c.status == "pending" and c.source_type == "owner_answer" and c.owner_answer_id == aid
        )
        assert c.proposed_by_actor_id == world[0].actor.id


def test_dedup_wording_and_holding_send_once(session_factory, clock, monkeypatch):
    world, fake, qid, context = waiting(session_factory, clock, monkeypatch, holding=True)
    with session_factory() as db:
        q = db.get(OwnerQuestion, qid)
        # Ask replay happens before any owner event changes the source cursor.
        replay = service.ask(
            db,
            clock,
            context,
            service.AskOwner(
                question="Reworded missing data?",
                required_info="exception",
                visibility="private_business",
                holding_response=True,
            ),
        )
        assert replay["question_id"] == str(qid)
        assert q.holding_action_id
        assert len(db.scalars(select(SimSentMessage)).all()) == 1
        assert (
            len(
                db.scalars(
                    select(Notification).where(Notification.type == "owner_question.requested")
                ).all()
            )
            == 1
        )
        assert len(db.scalars(select(OwnerQuestion)).all()) == 1


def test_closed_window_retains_answer_for_same_request_reopened(
    session_factory, clock, monkeypatch
):
    world, fake, qid, context = waiting(session_factory, clock, monkeypatch)
    clock.advance(timedelta(hours=25))
    aid, version = answer(session_factory, clock, world, qid)
    proposal = ReplyValidationArgs(
        template="", language="en", owner_answer={"id": aid, "version": version}
    )
    fake.queue_step(
        result("tool", tool_name="dm.send", tool_arguments=proposal.model_dump(mode="json"))
    )
    drain(session_factory, clock)
    with session_factory() as db:
        assert not db.scalars(select(SimSentMessage)).all()
        assert db.scalar(select(AgentSession)).status == "waiting_customer"
        assert db.get(OwnerAnswer, aid).body
    queue_answer(fake, aid, version)
    deliver(session_factory, clock, world, "Can I receive an exception for my request?")
    drain(session_factory, clock)
    with session_factory() as db:
        assert len(db.scalars(select(SimSentMessage)).all()) == 1


def test_owner_wait_reference_and_expiry_recovery(session_factory, clock, monkeypatch):
    world, fake, qid, _ = waiting(session_factory, clock, monkeypatch)
    with session_factory() as db:
        goal = db.scalar(select(AgentSession))
        thread = db.get(AgentThread, goal.thread_id)
        assert valid_wait(
            db, goal, thread, result("wait", wait_for="owner", metadata={"reference_id": str(qid)})
        )
        assert not valid_wait(
            db,
            goal,
            thread,
            result("wait", wait_for="owner", metadata={"reference_id": str(uuid.uuid4())}),
        )
    clock.advance(timedelta(days=8))
    fake.queue_step(result())
    agent_recover(recovery(session_factory, clock))
    drain(session_factory, clock)
    with session_factory() as db:
        assert db.get(OwnerQuestion, qid).state == "expired"
        assert db.get(OwnerQuestion, qid).body is None
        with pytest.raises(AppError, match="OWNER_QUESTION_CLOSED"):
            service.decide(
                db,
                clock,
                world[0],
                world[1],
                qid,
                service.AnswerRequest(
                    expected_version=2, client_request_id=uuid.uuid4(), body="Late"
                ),
            )
