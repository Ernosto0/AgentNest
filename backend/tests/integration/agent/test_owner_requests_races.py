"""Current-authority and queued-dispatch races for owner answer continuations."""

import uuid
from dataclasses import replace
from datetime import timedelta

import pytest
from sqlalchemy import select

from app.agent.models import AgentAction
from app.approvals.models import Approval
from app.core.errors import AppError
from app.inbox.models import ReplyDraft
from app.integrations.instagram.models import SimSentMessage
from app.owner_requests import service
from app.owner_requests.models import OwnerQuestion
from tests.integration.agent.test_dm import drain, project_until_send_job
from tests.integration.agent.test_owner_requests import answer, queue_answer, waiting

pytestmark = pytest.mark.commits


@pytest.mark.parametrize("mode", ["ask", "off"])
def test_information_never_overrides_dm_authority(session_factory, clock, monkeypatch, mode):
    world, fake, qid, _ = waiting(session_factory, clock, monkeypatch, mode=mode)
    aid, version = answer(session_factory, clock, world, qid, text="okay")
    queue_answer(fake, aid, version)
    drain(session_factory, clock)
    with session_factory() as db:
        action = db.scalar(select(AgentAction))
        assert not db.scalars(select(SimSentMessage)).all()
        if mode == "off":
            assert action.status == "cancelled"
            return
        from app.approvals import service as approvals

        approval = db.get(Approval, action.approval_id)
        original = approval.id
        assert approval.status == "pending" and approval.subject_type == "agent_action"
        approvals.decide(
            db, clock, world[0], original, decision="approve", payload_hash=approval.payload_hash
        )
        db.commit()
    drain(session_factory, clock)
    with session_factory() as db:
        assert len(db.scalars(select(SimSentMessage)).all()) == 1
        assert db.scalar(select(ReplyDraft)).approval_id == original


@pytest.mark.parametrize("mutation", ["cancel", "replace", "facts", "source", "window", "policy"])
def test_queued_quote_rechecks_before_dispatch(session_factory, clock, monkeypatch, mutation):
    from app.operations.send import execute_send_reply

    world, fake, qid, _ = waiting(session_factory, clock, monkeypatch)
    aid, version = answer(session_factory, clock, world, qid)
    queue_answer(fake, aid, version)
    project_until_send_job(session_factory, clock)
    with session_factory() as db:
        draft_id = db.scalar(select(ReplyDraft.id))
        q = db.get(OwnerQuestion, qid)
        if mutation == "cancel":
            service.decide(
                db,
                clock,
                world[0],
                world[1],
                qid,
                service.CancelRequest(expected_version=q.version, client_request_id=uuid.uuid4()),
            )
        elif mutation == "replace":
            service.decide(
                db,
                clock,
                world[0],
                world[1],
                qid,
                service.AnswerRequest(
                    expected_version=q.version,
                    client_request_id=uuid.uuid4(),
                    body="The prior exception is withdrawn.",
                ),
            )
        elif mutation == "facts":
            from app.identity.models import Workspace
            from tests.factories import create_fact

            create_fact(
                db,
                db.get(Workspace, world[0].workspace_id),
                "custom.new_policy",
                {"text": "A new policy."},
                value_type="text",
            )
        elif mutation == "source":
            from app.inbox.models import Message

            db.get(Message, q.source_message_id).text = "A changed request"
        elif mutation == "window":
            clock.advance(timedelta(hours=25))
        elif mutation == "policy":
            from app.agent.delegation import apply
            from app.agent.models import AccountAgent
            from tests.integration.agent.test_delegation import _change, _policy

            account = db.scalar(select(AccountAgent))
            apply(
                db, clock, world[0], world[1], _change(_policy(dm="off"), account.config_version, 1)
            )
        db.commit()
    execute_send_reply(session_factory, clock, world[3], world[0].workspace_id, draft_id)
    with session_factory() as db:
        assert not db.scalars(select(SimSentMessage)).all()
        if mutation in {"cancel", "replace"}:
            assert db.get(ReplyDraft, draft_id).status == "cancelled"
            assert db.scalar(select(AgentAction)).status == "cancelled"


def test_staff_proposal_after_answer_cannot_strand_continuation(
    session_factory, clock, monkeypatch
):
    from app.core.context import ActorRef
    from app.identity.models import WorkspaceMember
    from tests.factories import create_user

    world, _, qid, context = waiting(session_factory, clock, monkeypatch)
    aid, version = answer(session_factory, clock, world, qid)
    with session_factory() as db:
        user = create_user(db)
        db.add(WorkspaceMember(workspace_id=world[0].workspace_id, user_id=user.id, role="staff"))
        db.flush()
        staff = replace(world[0], actor=ActorRef.user(user.id), role="staff")
        before = db.get(OwnerQuestion, qid).version
        with pytest.raises(AppError, match="OWNER_QUESTION_CLOSED"):
            service.decide(
                db,
                clock,
                staff,
                world[1],
                qid,
                service.AnswerRequest(
                    expected_version=before,
                    client_request_id=uuid.uuid4(),
                    kind="proposal",
                    body="Perhaps not.",
                ),
            )
        assert db.get(OwnerQuestion, qid).version == before
        assert service.evidence(db, clock, context, aid, version)


def test_failed_answer_transaction_leaves_no_event_or_wake(session_factory, clock, monkeypatch):
    from app.agent.models import AgentEvent
    from app.owner_requests.models import OwnerAnswer

    world, _, qid, _ = waiting(session_factory, clock, monkeypatch)
    with session_factory() as db:
        service.decide(
            db,
            clock,
            world[0],
            world[1],
            qid,
            service.AnswerRequest(
                expected_version=1, client_request_id=uuid.uuid4(), body="Atomic information"
            ),
        )
        db.rollback()
    with session_factory() as db:
        assert db.get(OwnerQuestion, qid).state == "pending"
        assert not db.scalars(select(OwnerAnswer)).all()
        assert not db.scalars(select(AgentEvent).where(AgentEvent.kind == "owner_answer")).all()


def test_request_approval_tool_is_distinct_from_information_question(
    session_factory, clock, monkeypatch
):
    from app.agent.grounding import ReplyValidationArgs
    from app.integrations.llm.fake import FakeLLMProvider
    from tests.integration.agent.test_coordinator import deps, result
    from tests.integration.agent.test_dm import deliver, setup

    world = setup(session_factory, clock)
    fake = FakeLLMProvider()
    monkeypatch.setattr("app.agent.jobs.deps_for", lambda _: deps(session_factory, clock, fake))
    proposal = ReplyValidationArgs(template="Hello! How can I help?", language="en")
    fake.queue_step(
        result(
            "tool", tool_name="approval.request", tool_arguments=proposal.model_dump(mode="json")
        )
    )
    deliver(session_factory, clock, world)
    drain(session_factory, clock)
    with session_factory() as db:
        assert not db.scalars(select(OwnerQuestion)).all()
        approval = db.scalar(select(Approval))
        assert approval and approval.status == "pending" and approval.subject_type == "agent_action"
        assert db.scalar(select(AgentAction)).policy_grant is None
        assert not db.scalars(select(SimSentMessage)).all()
