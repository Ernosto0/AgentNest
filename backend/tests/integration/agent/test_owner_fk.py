"""Owner-question composite references reject real persisted foreign records."""

import uuid

import pytest
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from app.owner_requests import service
from app.owner_requests.models import OwnerQuestion
from tests.helpers.env import build_env
from tests.integration.agent.test_owner_requests_api import question


def test_question_references_cannot_bind_other_customer_source_or_answer(
    db_session, make_client, clock
):
    env = build_env(db_session, make_client, clock)
    first, q1 = question(env)
    first.status = "disconnected"
    db_session.flush()
    second, q2 = question(env, customer="two")
    a = service.decide(
        db_session,
        clock,
        env.ctx(env.owner),
        second.id,
        q2,
        service.AnswerRequest(
            expected_version=1, client_request_id=uuid.uuid4(), body="Second customer's answer."
        ),
    )
    db_session.commit()
    foreign = db_session.scalar(select(OwnerQuestion).where(OwnerQuestion.id == q2))
    for column, value in [
        ("answer_id", a.id),
        ("customer_identity_id", foreign.customer_identity_id),
        ("source_message_id", foreign.source_message_id),
    ]:
        with pytest.raises(IntegrityError), db_session.begin_nested():
            db_session.execute(
                update(OwnerQuestion).where(OwnerQuestion.id == q1).values(**{column: value})
            )
