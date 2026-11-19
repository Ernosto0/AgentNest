"""Agent enquiries survive abandonment and provider refusal without inventing conversion."""

import uuid
from datetime import timedelta
from unittest.mock import patch

import pytest
from sqlalchemy import func, select, text

from app.agent import calendar
from app.agent.enquiries import record_message_enquiry, record_thread_enquiry
from app.agent.models import AccountAgent, AgentAction, AgentEvent, AgentThread
from app.agent.tools.broker import BrokerContext
from app.inbox import processing
from app.inbox.models import Message, MessageTranscript, ReplyDraft
from app.integrations.instagram.base import NormalizedInboundEvent
from app.operations import data_rights
from app.retention import cleanup
from tests.integration.reporting.test_leads import appointment, page
from tests.integration.reporting.test_missed_customers import MONDAY, NOW, _world, at


def source(db, *, message_text="Can I book an appointment?", when=None):
    world = _world(db)
    controller = db.scalar(
        select(AccountAgent).where(AccountAgent.social_account_id == world.real.account.id)
    )
    controller.controller_mode = "agent"
    controller.state = "active"
    c = world.real.conversation(when or at(MONDAY, 10))
    m = world.real.message(c, "inbound", when or at(MONDAY, 10))
    m.text = message_text
    thread = AgentThread(
        workspace_id=world.workspace.id,
        social_account_id=world.real.account.id,
        surface="dm",
        source_ref=str(c.id),
        dm_conversation_id=c.id,
        event_cursor=1,
    )
    db.add(thread)
    db.flush()
    event = AgentEvent(
        workspace_id=world.workspace.id,
        social_account_id=world.real.account.id,
        thread_id=thread.id,
        cursor=1,
        kind="customer_message",
        source_kind="message",
        source_key=str(m.id),
        source_id=str(m.id),
        source_version=1,
        created_at=m.provider_timestamp,
    )
    db.add(event)
    db.flush()
    ctx = BrokerContext(world.ctx(), world.real.account.id, thread.id, "dm", "customer")
    return world, c, m, thread, event, ctx


def record(world, message, *, text_value=None):
    record_message_enquiry(
        world.session,
        world.clock,
        workspace_id=world.workspace.id,
        account_id=world.real.account.id,
        message_id=message.id,
        text=text_value,
    )


@pytest.mark.parametrize(
    "body",
    [
        "Randevu alabilir miyim?",
        "Can I book an appointment?",
        "Kann ich einen Termin buchen?",
        "Хочу записаться",
        "أريد حجز موعد",
    ],
)
def test_abandoned_booking_is_a_lead_before_any_draft_or_action(db_session, body):
    w, _, m, _, _, _ = source(db_session, message_text=body)
    record(w, m)
    record(w, m)  # repeated ingestion/media completion has the same original message
    assert m.agent_enquiry_intent == "booking"
    assert page(w).total == 1
    assert page(w).items[0].intent == "booking"
    assert db_session.scalar(select(func.count()).select_from(ReplyDraft)) == 0
    assert db_session.scalar(select(func.count()).select_from(AgentAction)) == 0


def test_availability_refusal_records_enquiry_without_creating_action(db_session):
    w, _, m, _, _, ctx = source(db_session, message_text="Is Tuesday afternoon possible?")
    with (
        patch.object(
            calendar.cal_ops, "check_availability", side_effect=RuntimeError("unavailable")
        ),
        pytest.raises(RuntimeError, match="unavailable"),
    ):
        calendar.availability(
            db_session,
            w.clock,
            ctx,
            calendar.CalendarAvailabilityArgs(local_date=MONDAY, days=1, duration_minutes=30),
        )
    assert m.agent_enquiry_intent == "booking"
    assert page(w).total == 1
    assert db_session.scalar(select(func.count()).select_from(AgentAction)) == 0


def test_disconnected_calendar_keeps_enquiry_before_book_action_admission(db_session):
    w, _, m, _, _, ctx = source(db_session, message_text="Tuesday afternoon please")
    result = calendar.book(
        db_session,
        w.clock,
        ctx,
        calendar.CalendarBookArgs(local_date=MONDAY, local_time="15:00", title="Session"),
    )
    assert result["error"] == "CALENDAR_NOT_CONNECTED"
    assert m.agent_enquiry_intent == "booking"
    assert page(w).total == 1
    assert db_session.scalar(select(func.count()).select_from(AgentAction)) == 0


def test_media_event_resolves_original_message_and_does_not_copy_transcript(db_session):
    w, _, m, _, event, ctx = source(db_session, message_text=None)
    m.attachments = [{"type": "audio", "url": "https://example.invalid/voice"}]
    transcript = MessageTranscript(
        workspace_id=w.workspace.id,
        message_id=m.id,
        status="succeeded",
        text="Kann ich einen Termin buchen?",
        language="de",
        provider="fake",
        model="fake",
    )
    db_session.add(transcript)
    db_session.flush()
    event.source_kind = "message_transcript"
    event.kind = "message.transcript_ready"
    event.source_id = str(transcript.id)
    record(w, m, text_value=transcript.text)
    record_thread_enquiry(db_session, w.clock, ctx)
    assert m.text is None and m.agent_enquiry_intent == "booking"
    assert page(w).total == 1


def test_only_linked_confirmed_appointment_converts_enquiry(db_session):
    w, c, m, _, _, _ = source(db_session)
    record(w, m)
    assert page(w).total == 1
    appt = appointment(w, c, status="scheduled")
    assert page(w).total == 0
    appt.status = "cancelled"
    assert page(w).total == 1


@pytest.mark.parametrize("exclusion", ["deleted", "simulated", "foreign", "owner_task"])
def test_provenance_scope_and_customer_source_are_enforced(db_session, exclusion):
    w, _, m, _, _, ctx = source(db_session)
    if exclusion == "deleted":
        m.is_deleted = True
    elif exclusion == "simulated":
        m.is_simulated = True
    elif exclusion == "foreign":
        record_message_enquiry(
            db_session,
            w.clock,
            workspace_id=uuid.uuid4(),
            account_id=w.real.account.id,
            message_id=m.id,
            intent="booking",
        )
        assert m.agent_enquiry_intent is None
        return
    elif exclusion == "owner_task":
        ctx = BrokerContext(w.ctx(), w.real.account.id, ctx.thread_id, "owner_task", "owner_task")
        record_thread_enquiry(db_session, w.clock, ctx)
        assert m.agent_enquiry_intent is None
        return
    record(w, m)
    assert page(w).total == 0


def test_retention_clears_enum_even_without_text_and_late_media_cannot_restore(
    db_session,
    shared_session_factory,
    settings,
):
    w, _, m, _, _, _ = source(db_session, message_text=None, when=NOW - timedelta(days=400))
    m.agent_enquiry_intent = "booking"
    db_session.flush()
    cleanup.run_retention(shared_session_factory, settings, NOW)
    db_session.expire_all()
    assert m.agent_enquiry_intent is None
    record(w, m, text_value="Randevu alabilir miyim?")
    assert m.agent_enquiry_intent is None


def test_erasure_clears_stored_enum_and_export_contains_it(db_session):
    w, c, m, _, _, _ = source(db_session)
    record(w, m)
    exported = data_rights.export_conversation(db_session, w.clock, w.ctx(), c.id)
    assert exported["messages"][0]["agent_enquiry_intent"] == "booking"
    data_rights.erase_conversation(db_session, w.clock, w.ctx(), c.id)
    assert db_session.get(Message, m.id) is None or m.agent_enquiry_intent is None


def test_migration_has_checked_nullable_column(db_session):
    constraint = db_session.scalar(
        text(
            "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
            "WHERE conname = 'ck_messages_agent_enquiry_intent'"
        )
    )
    assert "pricing" in constraint and "booking" in constraint


def test_customer_ingestion_captures_intent_before_agent_runs(db_session):
    w, _, _, _, _, _ = source(db_session)
    event = w.real.inbound_event("received", at(MONDAY, 12))
    normalized = NormalizedInboundEvent(
        event_type="message",
        account_id=w.real.account.external_account_id,
        customer_id="new-customer",
        provider_timestamp=at(MONDAY, 12),
        mid="booking-enquiry",
        text="Kann ich einen Termin buchen?",
    )
    processing._on_customer_message(
        db_session,
        w.clock,
        w.ctx(),
        w.real.account,
        event,
        normalized,
        0,
    )
    m = db_session.scalar(select(Message).where(Message.external_message_id == normalized.mid))
    assert m.agent_enquiry_intent == "booking"
    assert page(w).total == 1
    assert db_session.scalar(select(func.count()).select_from(ReplyDraft)) == 0
    assert db_session.scalar(select(func.count()).select_from(AgentAction)) == 0


def test_provider_deletion_clears_enquiry_and_prevents_late_restore(db_session):
    w, _, m, _, _, _ = source(db_session)
    m.external_message_id = "delete-original"
    record(w, m)
    event = w.real.inbound_event("received", at(MONDAY, 12))
    normalized = NormalizedInboundEvent(
        event_type="delete",
        account_id=w.real.account.external_account_id,
        customer_id="customer",
        provider_timestamp=at(MONDAY, 12),
        mid=m.external_message_id,
    )
    with patch.object(processing, "_normalized", return_value=normalized):
        processing.process_inbound_event(
            db_session,
            w.clock,
            w.workspace.id,
            event.id,
            debounce_seconds=0,
        )
    assert m.is_deleted and m.agent_enquiry_intent is None
    record(w, m, text_value="Can I book?")
    assert m.agent_enquiry_intent is None and page(w).total == 0
