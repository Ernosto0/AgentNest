"""Committed cutover rehearsal against two populated, isolated mock accounts."""

import uuid

import pytest
from sqlalchemy import select

from app.agent.control import ControllerChange, change_controller
from app.agent.models import AccountAgent, AgentAction
from app.approvals import service as approvals
from app.approvals.models import Approval
from app.inbox.models import ReplyDraft
from app.integrations.instagram.models import SimFailureRule, SimSentMessage
from app.integrations.llm.fake import FakeLLMProvider
from app.operations.models import Operation
from app.operations.send import execute_send_reply
from app.owner_requests.models import OwnerQuestion
from tests.integration.agent.test_coordinator import deps, result
from tests.integration.agent.test_dm import deliver, drain, project_until_send_job, reply, setup
from tests.integration.agent.test_owner_requests import waiting

pytestmark = pytest.mark.commits


def test_rollback_fences_pending_approval_and_keeps_other_account_active(
    session_factory, clock, monkeypatch
):
    waiting = setup(session_factory, clock, mode="ask")
    active = setup(session_factory, clock)
    fake = FakeLLMProvider()
    monkeypatch.setattr("app.agent.jobs.deps_for", lambda _: deps(session_factory, clock, fake))

    deliver(session_factory, clock, waiting)
    reply(fake)
    drain(session_factory, clock)
    with session_factory() as db:
        old_account = db.scalar(
            select(AccountAgent).where(AccountAgent.social_account_id == waiting[1])
        )
        old_epoch = old_account.controller_epoch
        pending = db.scalar(
            select(Approval)
            .join(AgentAction, AgentAction.approval_id == Approval.id)
            .where(AgentAction.social_account_id == waiting[1])
        )
        assert pending.status == "pending"
        pending_id = pending.id
        change_controller(
            db,
            clock,
            waiting[0],
            waiting[1],
            ControllerChange(
                expected_config_version=old_account.config_version,
                client_request_id=uuid.uuid4(),
                mode="legacy",
            ),
        )
        db.commit()

    drain(session_factory, clock)
    with session_factory() as db:
        old_account = db.scalar(
            select(AccountAgent).where(AccountAgent.social_account_id == waiting[1])
        )
        other = db.scalar(select(AccountAgent).where(AccountAgent.social_account_id == active[1]))
        assert (old_account.controller_mode, old_account.state) == ("legacy", "inactive")
        assert old_account.controller_epoch > old_epoch
        assert (other.controller_mode, other.state) == ("agent", "active")
        assert db.get(Approval, pending_id).status == "cancelled"
        assert not db.scalars(select(SimSentMessage)).all()

    deliver(session_factory, clock, active)
    reply(fake)
    fake.queue_step(result())
    drain(session_factory, clock)
    with session_factory() as db:
        sent = db.scalars(select(SimSentMessage)).all()
        assert len(sent) == 1 and sent[0].social_account_id == active[1]
        assert not db.scalars(
            select(ReplyDraft).where(
                ReplyDraft.workspace_id == waiting[0].workspace_id,
                ReplyDraft.status == "sent",
            )
        ).all()


def test_rollback_keeps_ambiguous_send_for_reconciliation(session_factory, clock, monkeypatch):
    world = setup(session_factory, clock)
    fake = FakeLLMProvider()
    monkeypatch.setattr("app.agent.jobs.deps_for", lambda _: deps(session_factory, clock, fake))
    with session_factory() as db:
        db.add(
            SimFailureRule(
                workspace_id=world[0].workspace_id,
                social_account_id=world[1],
                operation="send",
                mode="timeout_after_success",
                remaining=1,
            )
        )
        db.commit()
    deliver(session_factory, clock, world)
    reply(fake)
    drain(session_factory, clock)
    with session_factory() as db:
        action = db.scalar(select(AgentAction))
        operation = db.get(Operation, action.operation_id)
        assert action.status == "outcome_unknown"
        assert operation.status == "outcome_unknown"
        action_id, operation_id = action.id, operation.id
        account = db.scalar(select(AccountAgent))
        change_controller(
            db,
            clock,
            world[0],
            world[1],
            ControllerChange(
                expected_config_version=account.config_version,
                client_request_id=uuid.uuid4(),
                mode="legacy",
            ),
        )
        db.commit()
    drain(session_factory, clock)
    with session_factory() as db:
        assert db.get(AgentAction, action_id).status == "outcome_unknown"
        assert db.get(Operation, operation_id).status == "outcome_unknown"
        assert len(db.scalars(select(SimSentMessage)).all()) == 1


def test_approved_queued_send_is_fenced_by_rollback(session_factory, clock, monkeypatch):
    world = setup(session_factory, clock, mode="ask")
    fake = FakeLLMProvider()
    monkeypatch.setattr("app.agent.jobs.deps_for", lambda _: deps(session_factory, clock, fake))
    deliver(session_factory, clock, world)
    reply(fake)
    drain(session_factory, clock)
    with session_factory() as db:
        approval = db.scalar(select(Approval))
        approvals.decide(
            db,
            clock,
            world[0],
            approval.id,
            decision="approve",
            payload_hash=approval.payload_hash,
        )
        db.commit()
    project_until_send_job(session_factory, clock)
    with session_factory() as db:
        draft_id = db.scalar(select(ReplyDraft.id))
        account = db.scalar(select(AccountAgent))
        change_controller(
            db,
            clock,
            world[0],
            world[1],
            ControllerChange(
                expected_config_version=account.config_version,
                client_request_id=uuid.uuid4(),
                mode="legacy",
            ),
        )
        db.commit()
    assert (
        execute_send_reply(session_factory, clock, world[3], world[0].workspace_id, draft_id).kind
        == "failed"
    )
    drain(session_factory, clock)
    with session_factory() as db:
        assert db.get(ReplyDraft, draft_id).status == "cancelled"
        assert not db.scalars(select(SimSentMessage)).all()


def test_waiting_question_survives_rollback_without_agent_dispatch(
    session_factory, clock, monkeypatch
):
    world, fake, question_id, _ = waiting(session_factory, clock, monkeypatch)
    with session_factory() as db:
        account = db.scalar(select(AccountAgent))
        change_controller(
            db,
            clock,
            world[0],
            world[1],
            ControllerChange(
                expected_config_version=account.config_version,
                client_request_id=uuid.uuid4(),
                mode="legacy",
            ),
        )
        db.commit()
    drain(session_factory, clock)
    with session_factory() as db:
        assert db.get(OwnerQuestion, question_id).state == "pending"
        assert not db.scalars(select(SimSentMessage)).all()
    assert len(fake.step_calls) == 1
