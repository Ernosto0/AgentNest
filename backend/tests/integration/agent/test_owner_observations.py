"""Between-claim source fences and customer-private owner context."""

import uuid
from dataclasses import replace

import pytest
from sqlalchemy import select

from app.agent import coordinator
from app.agent.context import assemble
from app.agent.grounding import ReplyValidationArgs
from app.agent.models import AgentThread
from app.agent.tools.broker import build_default_broker
from app.owner_requests import service
from app.owner_requests.models import OwnerQuestion
from tests.integration.agent.test_coordinator import deps, result
from tests.integration.agent.test_dm import deliver, drain
from tests.integration.agent.test_owner_requests import answer, waiting

pytestmark = pytest.mark.commits


def test_answer_change_between_claims_discards_personal_observation(
    session_factory, clock, monkeypatch
):
    world, fake, qid, context = waiting(session_factory, clock, monkeypatch)
    aid, version = answer(session_factory, clock, world, qid, text="Original exception details.")
    args = ReplyValidationArgs(
        template="", language="en", owner_answer={"id": aid, "version": version}
    )
    fake.queue_step(
        result("tool", tool_name="reply.validate", tool_arguments=args.model_dump(mode="json"))
    )
    fake.queue_step(result())
    original = coordinator.claim
    claims = []

    def intercept(runner, workspace, thread):
        if claims:
            with session_factory() as db:
                q = db.get(OwnerQuestion, qid)
                service.decide(
                    db,
                    clock,
                    world[0],
                    world[1],
                    qid,
                    service.AnswerRequest(
                        expected_version=q.version,
                        client_request_id=uuid.uuid4(),
                        body="Replacement private answer.",
                    ),
                )
                db.commit()
        claims.append(True)
        return original(runner, workspace, thread)

    monkeypatch.setattr(coordinator, "claim", intercept)
    coordinator.run_activation(
        deps(session_factory, clock, fake),
        world[0].workspace_id,
        context.thread_id,
        build_default_broker(),
    )
    assert fake.step_calls[-1].observations == ()
    assert "Original exception details" not in fake.step_calls[-1].messages[0].content
    assert "Replacement private answer" in fake.step_calls[-1].messages[0].content


def test_same_wording_questions_and_answers_never_cross_customers(
    session_factory, clock, monkeypatch
):
    world, fake, first, context = waiting(session_factory, clock, monkeypatch)
    answer(session_factory, clock, world, first, text="PRIVATE-FIRST-CUSTOMER-EXCEPTION")
    # Complete the first goal without sending, then create a distinct customer source.
    fake.queue_step(result())
    drain(session_factory, clock)
    fake.queue_step(
        result(
            "tool",
            tool_name="owner.ask",
            tool_arguments={
                "question": "Can this customer receive a one-off exception?",
                "required_info": "exception",
                "visibility": "customer_reply",
            },
        )
    )
    deliver(
        session_factory,
        clock,
        world,
        "Can I receive an exception for my request?",
        customer="customer-two",
    )
    drain(session_factory, clock)
    with session_factory() as db:
        questions = db.scalars(select(OwnerQuestion)).all()
        assert len(questions) == 2 and len({q.continuation_key for q in questions}) == 2
        other = next(q for q in questions if q.id != first)
        assert other.customer_identity_id != db.get(OwnerQuestion, first).customer_identity_id
        thread = db.get(AgentThread, other.thread_id)
        other_context = replace(context, thread_id=thread.id)
        assert service.private_answers(db, clock, other_context) == []
        assert (
            "PRIVATE-FIRST-CUSTOMER-EXCEPTION"
            not in assemble(db, clock, other_context).messages[0].content
        )
