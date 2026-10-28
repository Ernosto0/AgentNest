"""Operator review: owner information never substitutes for action permission."""

import uuid

import pytest
from sqlalchemy import select

from app.agent import subject
from app.agent.models import AgentAction
from app.approvals.models import Approval
from app.integrations.instagram.models import SimSentMessage
from app.owner_requests import service
from app.owner_requests.models import OwnerQuestion
from tests.integration.agent.test_dm import drain
from tests.integration.agent.test_owner_requests import answer, queue_answer, waiting

pytestmark = pytest.mark.commits


@pytest.mark.parametrize("mode", ["ask", "off"])
def test_owner_information_preserves_delegated_action_permission(
    session_factory, clock, monkeypatch, mode
):
    world, fake, qid, _ = waiting(session_factory, clock, monkeypatch, mode=mode)
    aid, version = answer(session_factory, clock, world, qid, text="okay")
    queue_answer(fake, aid, version)
    drain(session_factory, clock)
    with session_factory() as db:
        assert db.get(OwnerQuestion, qid).state == "answered"
        assert not db.scalars(select(SimSentMessage)).all()
        action = db.scalar(select(AgentAction))
        assert action is not None
        approvals = db.scalars(select(Approval)).all()
        if mode == "ask":
            assert action.status == "waiting_approval"
            assert len(approvals) == 1 and approvals[0].status == "pending"
            assert approvals[0].decided_by_user_id is None
            assert approvals[0].decision_channel is None
        else:
            assert action.status == "cancelled"
            assert not approvals


def test_cancelled_answer_immediately_stales_pending_approval(session_factory, clock, monkeypatch):
    world, fake, qid, _ = waiting(session_factory, clock, monkeypatch, mode="ask")
    aid, version = answer(session_factory, clock, world, qid)
    queue_answer(fake, aid, version)
    drain(session_factory, clock)
    with session_factory() as db:
        approval = db.scalar(select(Approval))
        assert approval is not None and approval.status == "pending"
        action_id = approval.subject_id
        q = db.get(OwnerQuestion, qid)
        service.decide(
            db,
            clock,
            world[0],
            world[1],
            qid,
            service.CancelRequest(expected_version=q.version, client_request_id=uuid.uuid4()),
        )
        db.commit()
    with session_factory() as db:
        # The card is stale before deferred cleanup acquires approval locks.
        assert subject.current_version(db, world[0], action_id) is None
    drain(session_factory, clock)
    with session_factory() as db:
        assert db.scalar(select(Approval)).status == "cancelled"
        assert not db.scalars(select(SimSentMessage)).all()
