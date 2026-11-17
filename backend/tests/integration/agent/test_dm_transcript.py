"""F-03 Session 02: the account agent's reply in a conversation with a transcribed voice note
always needs a person, even when the account's delegation makes ``dm.send`` automatic.

The agent does not read transcripts yet (its context shows an audio attachment as
``[attachment: audio]``); the guard is deterministic and reads stored rows, so it holds the day the
agent does. The control is the same flow with no voice note, which sends by itself."""

import uuid

import pytest
from sqlalchemy import select

from app.agent.models import AgentAction
from app.approvals.models import Approval
from app.inbox.ingest import ingest_webhook
from app.inbox.models import MessageTranscript
from app.integrations.instagram import webhook_format as wf
from app.integrations.instagram.models import SimInboundMessage, SimSentMessage
from app.integrations.llm.fake import FakeLLMProvider
from tests.integration.agent.test_coordinator import deps, result
from tests.integration.agent.test_dm import drain, reply, setup

pytestmark = pytest.mark.commits


def deliver_with_voice(factory, clock, world, text, *, voice: bool, customer="customer-one"):
    ctx, account_id, external, settings = world
    mid = uuid.uuid4().hex
    attachments = [wf.audio_attachment("mock-audio://price_question_tr")] if voice else None
    payload = wf.build_message_payload(
        external, customer, mid, text, clock.now(), attachments=attachments
    )
    raw = wf.serialize(payload)
    with factory() as db:
        db.add(
            SimInboundMessage(
                workspace_id=ctx.workspace_id,
                social_account_id=account_id,
                sender_id=customer,
                mid=mid,
                received_at=clock.now(),
            )
        )
        db.commit()
        return ingest_webhook(
            db,
            clock,
            settings,
            "mock",
            raw,
            {
                wf.SIGNATURE_HEADER: wf.sign(
                    raw, settings.mock_instagram_app_secret.get_secret_value()
                )
            },
        )


@pytest.mark.parametrize("voice", [False, True])
def test_an_automatic_dm_delegation_still_asks_when_a_voice_note_is_in_the_conversation(
    session_factory, clock, monkeypatch, voice
):
    world = setup(session_factory, clock, "automatic")
    fake = FakeLLMProvider()
    monkeypatch.setattr("app.agent.jobs.deps_for", lambda _: deps(session_factory, clock, fake))
    deliver_with_voice(session_factory, clock, world, "Hello, what do you offer?", voice=voice)
    reply(fake, "Hello! What would you like help with?")
    fake.queue_step(result())
    drain(session_factory, clock)
    with session_factory() as db:
        sent = db.scalars(select(SimSentMessage)).all()
        action = db.scalar(select(AgentAction))
        transcripts = db.scalars(select(MessageTranscript)).all()
        if not voice:
            assert transcripts == [] and len(sent) == 1  # control: automatic, sent by itself
            assert action.status == "succeeded"
            return
        assert [t.status for t in transcripts] == ["succeeded"]
        assert sent == []  # nothing went out without a person
        assert action.status == "waiting_approval"
        approval = db.get(Approval, action.approval_id)
        assert approval.status == "pending" and approval.subject_type == "agent_action"
        assert action.policy_grant is None  # no automatic grant was ever recorded
