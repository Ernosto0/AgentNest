"""Real migrated-DB regressions for response policy and derived-media obligations."""

from datetime import timedelta

import pytest
from sqlalchemy import select

from app.agent.coordinator import claim
from app.agent.dm import revalidate, send
from app.agent.grounding import ReplyValidationArgs
from app.agent.media import wake_for_media
from app.agent.models import AgentAction, AgentThread
from app.agent.reply_evidence import response_evidence
from app.agent.tools.broker import BrokerContext
from app.inbox.models import Conversation, Message, MessageImageDescription, ReplyDraft
from app.inbox.service import release
from app.integrations.instagram.models import SimSentMessage
from app.operations.send import execute_send_reply
from tests.integration.agent.test_coordinator import deps
from tests.integration.agent.test_dm import deliver, process_inbound, setup

pytestmark = pytest.mark.commits


def inbound(factory, clock, world, text):
    deliver(factory, clock, world, text)
    process_inbound(factory, clock)
    with factory() as db:
        return db.scalar(
            select(Message.id)
            .where(Message.direction == "inbound")
            .order_by(Message.created_at.desc())
        )


def propose(factory, clock, world):
    with factory() as db:
        thread = db.scalar(select(AgentThread))
        thread_id = thread.id
    # A real coordinator claim creates the durable current response goal.
    claim(deps(factory, clock), world[0].workspace_id, thread_id)
    with factory() as db:
        result = send(
            db,
            clock,
            BrokerContext(world[0], world[1], thread_id, "dm", "customer"),
            ReplyValidationArgs(template="Hello!", language="en"),
        )
        db.commit()
        return result


def image(factory, world, message_id, *, status="succeeded", injection=False):
    with factory() as db:
        row = MessageImageDescription(
            workspace_id=world[0].workspace_id,
            message_id=message_id,
            attachment_index=0,
            status=status,
            description="Hello" if status == "succeeded" else None,
            provider="fake" if status == "succeeded" else None,
            model="fake" if status == "succeeded" else None,
            injection_suspected=injection,
            is_simulated=True,
        )
        db.add(row)
        db.flush()
        row_id = row.id
        db.commit()
        return row_id


def complete_image(factory, clock, message_id, image_id):
    with factory() as db:
        row = db.get(MessageImageDescription, image_id)
        row.status, row.description, row.provider, row.model = "succeeded", "Hello", "fake", "fake"
        message = db.get(Message, message_id)
        thread = db.scalar(select(AgentThread))
        changed = wake_for_media(
            db,
            clock,
            message=message,
            thread=thread,
            kind="message.image_described",
            source_kind="message_image_description",
            source_key=f"image_desc:{row.id}",
            source_id=str(row.id),
        )
        db.commit()
        return changed


def test_complaint_followed_by_greeting_cannot_auto_send(session_factory, clock):
    world = setup(session_factory, clock)
    first = inbound(session_factory, clock, world, "This service is terrible")
    clock.advance(timedelta(seconds=1))
    second = inbound(session_factory, clock, world, "Hello")
    result = propose(session_factory, clock, world)
    with session_factory() as db:
        action = db.get(AgentAction, result["action_id"])
        evidence = response_evidence(db, db.scalar(select(AgentThread)), second)
        assert set(evidence.message_ids) == {first, second}
        assert action.status == "cancelled" and action.outcome_code == "escalation_complaint"
        assert not db.scalars(select(SimSentMessage)).all()


def test_earlier_image_injection_is_checked_on_newest_greeting(session_factory, clock):
    world = setup(session_factory, clock)
    first = inbound(session_factory, clock, world, "Hello")
    image(session_factory, world, first, injection=True)
    clock.advance(timedelta(seconds=1))
    inbound(session_factory, clock, world, "Hello")
    result = propose(session_factory, clock, world)
    with session_factory() as db:
        action = db.get(AgentAction, result["action_id"])
        assert action.status == "cancelled" and action.outcome_code == "injection_suspected"


def test_pending_image_then_new_text_wakes_once_for_combined_obligation(session_factory, clock):
    world = setup(session_factory, clock)
    first = inbound(session_factory, clock, world, "Hello")
    image_id = image(session_factory, world, first, status="pending")
    clock.advance(timedelta(seconds=1))
    second = inbound(session_factory, clock, world, "Hello")
    assert propose(session_factory, clock, world)["status"] == "waiting_media"
    with session_factory() as db:
        assert not db.scalars(select(ReplyDraft)).all()
    assert complete_image(session_factory, clock, first, image_id)
    result = propose(session_factory, clock, world)
    assert result["status"] == "queued"
    with session_factory() as db:
        draft = db.scalar(select(ReplyDraft))
        assert draft.covers_through_message_id == second
        draft_id = draft.id
    assert (
        execute_send_reply(session_factory, clock, world[3], world[0].workspace_id, draft_id).kind
        == "sent"
    )
    assert not complete_image(session_factory, clock, first, image_id)
    with session_factory() as db:
        assert len(db.scalars(select(SimSentMessage)).all()) == 1
        assert len(db.scalars(select(AgentAction)).all()) == 1


def test_late_media_does_not_reopen_successful_reply(session_factory, clock):
    world = setup(session_factory, clock)
    message_id = inbound(session_factory, clock, world, "Hello")
    propose(session_factory, clock, world)
    with session_factory() as db:
        draft_id = db.scalar(select(ReplyDraft.id))
        old_cursor = db.scalar(select(AgentThread.event_cursor))
    assert (
        execute_send_reply(session_factory, clock, world[3], world[0].workspace_id, draft_id).kind
        == "sent"
    )
    image_id = image(session_factory, world, message_id)
    assert not complete_image(session_factory, clock, message_id, image_id)
    with session_factory() as db:
        assert db.scalar(select(AgentThread.event_cursor)) == old_cursor
        assert len(db.scalars(select(SimSentMessage)).all()) == 1


def test_media_completion_retires_unsent_approval_before_replan(session_factory, clock):
    world = setup(session_factory, clock, mode="ask")
    message_id = inbound(session_factory, clock, world, "Hello")
    first = propose(session_factory, clock, world)
    image_id = image(session_factory, world, message_id)
    assert complete_image(session_factory, clock, message_id, image_id)
    second = propose(session_factory, clock, world)
    assert first["action_id"] != second["action_id"]
    assert second["status"] == "waiting_approval"
    with session_factory() as db:
        first_action = db.get(AgentAction, first["action_id"])
        assert first_action.status == "cancelled"
        assert db.get(ReplyDraft, first_action.payload_ref).status == "superseded"
        assert (
            len(db.scalars(select(ReplyDraft).where(ReplyDraft.status == "pending_approval")).all())
            == 1
        )


@pytest.mark.parametrize(
    "state", ["in_progress", "outcome_unknown", "draft_sending", "draft_outcome_unknown"]
)
def test_media_completion_keeps_uncertain_response_reserved(session_factory, clock, state):
    world = setup(session_factory, clock)
    message_id = inbound(session_factory, clock, world, "Hello")
    first = propose(session_factory, clock, world)
    with session_factory() as db:
        action = db.get(AgentAction, first["action_id"])
        if state.startswith("draft_"):
            db.get(ReplyDraft, action.payload_ref).status = state.removeprefix("draft_")
        else:
            action.status = state
        old_cursor = db.scalar(select(AgentThread.event_cursor))
        db.commit()
    image_id = image(session_factory, world, message_id)
    assert not complete_image(session_factory, clock, message_id, image_id)
    with session_factory() as db:
        assert db.scalar(select(AgentThread.event_cursor)) == old_cursor
        assert len(db.scalars(select(AgentAction)).all()) == 1


def test_native_answer_then_release_discharges_old_complaint(session_factory, clock):
    world = setup(session_factory, clock)
    first = inbound(session_factory, clock, world, "This service is terrible")
    clock.advance(timedelta(seconds=1))
    deliver(session_factory, clock, world, "We resolved your concern", echo=True)
    process_inbound(session_factory, clock)
    with session_factory() as db:
        conversation = db.scalar(select(Conversation))
        release(db, clock, world[0], conversation.id)
    clock.advance(timedelta(seconds=1))
    latest = inbound(session_factory, clock, world, "Hello")
    result = propose(session_factory, clock, world)
    assert result["status"] == "queued"
    with session_factory() as db:
        evidence = response_evidence(db, db.scalar(select(AgentThread)), latest)
        assert latest in evidence.message_ids and first not in evidence.message_ids


def test_send_time_revalidation_checks_all_response_messages(session_factory, clock):
    world = setup(session_factory, clock)
    first = inbound(session_factory, clock, world, "Hello")
    clock.advance(timedelta(seconds=1))
    inbound(session_factory, clock, world, "Hello")
    propose(session_factory, clock, world)
    with session_factory() as db:
        db.get(Message, first).text = "This service is terrible"
        draft = db.scalar(select(ReplyDraft))
        db.flush()
        assert not revalidate(db, clock, draft, db.get(Conversation, draft.conversation_id))
