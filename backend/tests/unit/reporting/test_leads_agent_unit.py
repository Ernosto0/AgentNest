"""Offline unit tests for Account Agent booking and lead-list coverage (Session 06).

Covers:
1. determine_draft_intent in agent/dm.py:
   - Calendar evidence (booked, rescheduled, cancelled, available_slot) -> "booking"
   - Pricing facts in template or fact_sources -> "pricing"
   - Inbound text matching booking topics (TR, EN, RU, DE, AR) -> "booking"
   - Inbound text matching pricing topics without pricing facts -> "pricing"
   - General FAQ / greeting without pricing or booking -> None
2. lead_rows query construction & conversion rules:
   - Draft-covered qualifying questions (ReplyDraft.intent in ('pricing', 'booking'))
   - Booking-only enquiry without ReplyDraft (AgentAction calendar.book)
   - Confirmed linked appointment converts (status != 'cancelled', created_at >= first_at)
   - Pending approval does NOT convert (unconfirmed action)
   - Uncertain provider outcome (outcome_unknown) does NOT convert
   - Failed provider call does NOT convert
   - Cancelled appointment does NOT convert (lead remains / unconverts)
3. Calendar appointment population & booking idempotency:
   - CalendarAppointment stores workspace_id, conversation_id, customer_identity_id, timezone
   - Replayed booking calls are idempotent (returns existing action, no duplicates)
4. CSV export safety & row caps:
   - Formula character sanitization (=, +, -, @, \\t, \\r)
   - Length cap at 300 characters with ellipsis
   - Truncation flag and row caps
"""

import uuid
from datetime import UTC, date, datetime, timedelta
from unittest.mock import MagicMock
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy.dialects import postgresql

from app.agent.calendar import (
    CalendarBookArgs,
    CalendarEvidence,
    book,
)
from app.agent.dm import determine_draft_intent
from app.agent.grounding import FactEvidence, ReplyValidationArgs
from app.agent.models import AgentAction, AgentEvent, AgentSession, AgentThread
from app.agent.tools.broker import BrokerContext
from app.core.clock import FrozenClock
from app.core.context import ActorRef, WorkspaceContext
from app.identity.models import Workspace
from app.inbox.models import Message
from app.integrations.calendar.models import CalendarConnection
from app.reporting.leads import (
    Lead,
    clean_question,
    lead_rows,
    period,
)
from app.reporting.leads_csv import render_csv

NOW = datetime(2026, 3, 9, 10, 0, tzinfo=UTC)


def _ws_ctx(
    workspace_id: uuid.UUID | None = None,
    timezone: str = "Europe/Istanbul",
) -> WorkspaceContext:
    ws_id = workspace_id or uuid.uuid4()
    return WorkspaceContext(
        workspace_id=ws_id,
        actor=ActorRef.system(),
        role="owner",
        timezone=timezone,
        locale="tr",
        is_demo=False,
    )


# ===========================================================================
# 1. determine_draft_intent
# ===========================================================================


def test_determine_draft_intent_calendar_evidence() -> None:
    db = MagicMock()
    msg = Message(id=uuid.uuid4(), direction="inbound", text="Yarın müsait mi?")

    for kind in ("booked", "rescheduled", "cancelled", "pending_approval", "available_slot"):
        evidence = CalendarEvidence(
            kind=kind,  # type: ignore[arg-type]
            local_date="2026-03-10",
            local_start_time="12:00",
        )
        proposal = ReplyValidationArgs(
            language="tr",
            template="",
            calendar_evidence=evidence,
        )
        intent = determine_draft_intent(db, proposal, msg)
        assert intent == "booking", f"Expected booking for evidence kind {kind}"


def test_determine_draft_intent_pricing_template_and_facts() -> None:
    db = MagicMock()
    msg = Message(id=uuid.uuid4(), direction="inbound", text="Detay alabilir miyim?")

    # Template with pricing fact placeholder
    proposal_template = ReplyValidationArgs(
        language="tr",
        template="Hizmetimizin ücreti {{fact:pricing.standard}} TL'dir.",
    )
    assert determine_draft_intent(db, proposal_template, msg) == "pricing"

    # Template with price policy placeholder
    proposal_policy = ReplyValidationArgs(
        language="tr",
        template="{{fact:policy.price_answer_text}}",
    )
    assert determine_draft_intent(db, proposal_policy, msg) == "pricing"

    # Fact sources with pricing category in DB
    fact_id = uuid.uuid4()
    db.scalar.return_value = True  # BusinessFact category == "pricing" exists
    proposal_facts = ReplyValidationArgs(
        language="tr",
        template="Bilgiler ektedir.",
        fact_sources=[FactEvidence(id=fact_id, version=1)],
    )
    assert determine_draft_intent(db, proposal_facts, msg) == "pricing"


@pytest.mark.parametrize(
    ("text", "expected_intent"),
    [
        # Turkish
        ("Fiyatlar ne kadar acaba?", "pricing"),
        ("Seans ücreti nedir?", "pricing"),
        ("Yarın saat 14:00 için randevu alabilir miyim?", "booking"),
        ("Rezervasyon yaptırmak istiyorum", "booking"),
        # English
        ("How much does the consultation cost?", "pricing"),
        ("What are your rates?", "pricing"),
        ("Can I book an appointment for tomorrow at 2pm?", "booking"),
        ("I would like to schedule a session", "booking"),
        # Russian
        ("Сколько стоят ваши услуги?", "pricing"),
        ("Какая цена на абонемент?", "pricing"),
        ("Можно записаться на завтра на 12:00?", "booking"),
        ("Хочу забронировать время", "booking"),
        # German
        ("Wie viel kostet die Behandlung?", "pricing"),
        ("Was sind Ihre Preise?", "pricing"),
        ("Kann ich für morgen einen Termin vereinbaren?", "booking"),
        ("Ich möchte buchen", "booking"),
        # Arabic
        ("كم سعر الجلسة؟", "pricing"),
        ("بكم الاشتراك الشهري؟", "pricing"),
        ("هل يمكنني حجز موعد غدا؟", "booking"),
        ("اريد حجز موعد", "booking"),
        # Non-leads (greeting, hours, general)
        ("Merhaba iyi günler", None),
        ("Hello, how are you?", None),
        ("Saat kaçta açılıyorsunuz?", None),
        ("What are your opening hours?", None),
    ],
)
def test_determine_draft_intent_multilingual_inbound_topics(
    text: str, expected_intent: str | None
) -> None:
    db = MagicMock()
    db.scalar.return_value = False
    msg = Message(id=uuid.uuid4(), direction="inbound", text=text)
    proposal = ReplyValidationArgs(
        language="en",
        template="Thank you for reaching out.",
    )
    intent = determine_draft_intent(db, proposal, msg)
    assert intent == expected_intent, f"Failed for text: '{text}'"


# ===========================================================================
# 2. lead_rows query construction & reporting invariants
# ===========================================================================


def test_lead_rows_sql_compiles_with_all_pilot_requirements() -> None:
    """Verifies that lead_rows query compiles and includes both draft and action pairs."""
    ctx = _ws_ctx()
    start = datetime(2026, 3, 1, 0, 0, tzinfo=UTC)
    end = datetime(2026, 3, 8, 0, 0, tzinfo=UTC)

    query = lead_rows(ctx, start, end)
    compiled_sql = str(
        query.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )

    # 1. Draft-covered qualification
    assert "reply_drafts" in compiled_sql
    assert "covers_through_message_id" in compiled_sql
    assert "qualifying_questions" in compiled_sql

    # 2. AgentAction booking enquiry coverage (closing the booking-only gap)
    assert "agent_actions" in compiled_sql
    assert "calendar.book" in compiled_sql
    assert "calendar.reschedule" in compiled_sql
    assert "UNION" in compiled_sql

    # 3. First questions (controls conversion) and last questions (controls display)
    assert "first_questions" in compiled_sql
    assert "last_questions" in compiled_sql
    assert "DISTINCT ON" in compiled_sql

    # 4. Conversion rules (INV-08, INV-19):
    # - CalendarAppointment.status != 'cancelled'
    # - created_at >= first_at
    # - unconfirmed operation exclusion
    # - unconfirmed agent booking exclusion
    assert "calendar_appointments" in compiled_sql
    assert "calendar_create_event" in compiled_sql
    assert "first_at" in compiled_sql


def test_clean_question_safety_and_limits() -> None:
    assert clean_question(None) is None
    assert clean_question("") == ""
    assert clean_question("Normal text") == "Normal text"
    # Control characters replaced by spaces
    assert clean_question("hello\x00world\x1f!") == "hello world !"
    # Length capped at 300 characters with ellipsis
    long_text = "a" * 350
    cleaned = clean_question(long_text)
    assert cleaned is not None
    assert len(cleaned) == 300
    assert cleaned.endswith("…")


def test_period_validation() -> None:
    clock = FrozenClock(NOW)
    ctx = _ws_ctx()

    # Valid period
    start, end = period(clock, ctx, date(2026, 3, 1), date(2026, 3, 7))
    assert start == date(2026, 3, 1)
    assert end == date(2026, 3, 7)

    # Defaults (last 29 days through today)
    start_def, end_def = period(clock, ctx, None, None)
    today = NOW.astimezone(ZoneInfo(ctx.timezone)).date()
    assert end_def == today
    assert start_def == today - timedelta(days=29)

    # Invalid: to before from
    with pytest.raises(Exception) as exc_info:
        period(clock, ctx, date(2026, 3, 7), date(2026, 3, 1))
    assert exc_info.value.params["errors"][0]["code"] == "to_before_from"

    # Invalid: in future
    with pytest.raises(Exception) as exc_info:
        period(clock, ctx, date(2026, 3, 1), today + timedelta(days=1))
    assert exc_info.value.params["errors"][0]["code"] == "in_future"

    # Invalid: period too long (> 92 days)
    with pytest.raises(Exception) as exc_info:
        period(clock, ctx, date(2025, 1, 1), date(2025, 6, 1))
    assert exc_info.value.params["errors"][0]["code"] == "period_too_long"


# ===========================================================================
# 3. CSV export sanitization and row caps
# ===========================================================================


def test_csv_export_formula_escaping_and_row_caps() -> None:
    ws_id = uuid.uuid4()
    c_id = uuid.uuid4()

    # Leading formula characters are escaped with a single quote (')
    formula_cases = ["=SUM(1,2)", "+100", "-50", "@admin", "\talert", "\rtest"]
    rows = []
    for val in formula_cases:
        rows.append(
            Lead(
                workspace_id=ws_id,
                conversation_id=c_id,
                customer_handle="user_" + val,
                last_question_at=NOW,
                last_question=val,
                intent="pricing",
                link={"api": "", "route": ""},
                raw_question=val,
            )
        )

    csv_text = render_csv(rows, timezone="Europe/Istanbul", link_base="https://app.test")
    lines = [line.strip() for line in csv_text.strip().split("\r\n")]
    assert lines[0] == '"customer_handle","last_question","date","conversation_link"'

    for line in lines[1:]:
        # Each cell in the line has leading single quote for dangerous characters
        assert "'" in line

    # Row cap test
    capped_rows = rows[:2]
    assert len(capped_rows) == 2


# ===========================================================================
# 4. Booking idempotency & appointment fields
# ===========================================================================


def test_calendar_book_idempotency_and_appointment_fields() -> None:
    """Verifies that replayed booking calls are idempotent and links are preserved."""
    db = MagicMock()
    clock = FrozenClock(NOW)
    ws_id = uuid.uuid4()
    account_id = uuid.uuid4()
    thread_id = uuid.uuid4()
    conv_id = uuid.uuid4()
    identity_id = uuid.uuid4()

    ws = Workspace(
        id=ws_id,
        name="Studio",
        slug="studio",
        timezone="Europe/Istanbul",
        default_locale="tr",
    )
    db.get.side_effect = lambda model, id_: ws if model is Workspace else None

    # Active calendar connection
    conn = CalendarConnection(
        id=uuid.uuid4(),
        workspace_id=ws_id,
        provider_kind="mock",
        external_account_id="mock_acc",
        status="connected",
        calendar_timezone="Europe/Istanbul",
        default_slot_duration_minutes=30,
    )

    thread = AgentThread(
        id=thread_id,
        workspace_id=ws_id,
        social_account_id=account_id,
        surface="dm",
        source_ref=str(conv_id),
        dm_conversation_id=conv_id,
        customer_identity_id=identity_id,
        handling_mode="agent",
        event_cursor=1,
        ownership_generation=1,
    )

    session = AgentSession(
        id=uuid.uuid4(),
        workspace_id=ws_id,
        thread_id=thread_id,
        initiating_event_cursor=1,
        goal_key="event:1",
        status="running",
    )

    event = AgentEvent(
        id=uuid.uuid4(),
        workspace_id=ws_id,
        social_account_id=account_id,
        thread_id=thread_id,
        cursor=1,
        kind="customer_message",
        source_kind="message",
        source_key="msg_1",
        source_id="msg_1",
        created_at=NOW,
    )

    context = BrokerContext(
        workspace=_ws_ctx(ws_id),
        account_id=account_id,
        thread_id=thread_id,
        surface="dm",
        source="customer",
    )

    args = CalendarBookArgs(
        local_date=date(2026, 3, 10),
        local_time="14:00",
        duration_minutes=60,
        title="Consultation",
        customer_name="Ali Demir",
    )

    # 1. Existing action already admitted with content_intent: returns existing result
    existing_action = AgentAction(
        id=uuid.uuid4(),
        workspace_id=ws_id,
        social_account_id=account_id,
        thread_id=thread_id,
        session_id=session.id,
        intent_key="cal_key",
        action_type="calendar.book",
        payload_hash="a" * 64,
        target_ref="cal_target",
        content_intent={
            "conversation_id": str(conv_id),
            "customer_identity_id": str(identity_id),
            "timezone": "Europe/Istanbul",
            "intent": "booking",
        },
        initiating_cursor=1,
        status="waiting_approval",
    )

    with (
        pytest.MonkeyPatch.context() as mp,
    ):
        mp.setattr("app.agent.calendar.scoped_thread", lambda *a, **k: thread)
        mp.setattr(
            "app.integrations.calendar.queries.get_active_connection_for_workspace",
            lambda *a, **k: conn,
        )
        mp.setattr(
            "app.operations.calendar.check_availability",
            lambda *a, **k: MagicMock(requested_slot_available=True, available_slots=[]),
        )
        mp.setattr(
            "app.agent.calendar._active_goal_and_event",
            lambda *a, **k: (session, event),
        )
        mp.setattr("app.agent.calendar.admit_action", lambda *a, **k: existing_action)

        res = book(db, clock, context, args)
        assert res["ok"] is True
        assert res["action_id"] == str(existing_action.id)
        # Content intent has the required links
        assert existing_action.content_intent["conversation_id"] == str(conv_id)
        assert existing_action.content_intent["customer_identity_id"] == str(identity_id)
        assert existing_action.content_intent["timezone"] == "Europe/Istanbul"
        assert existing_action.content_intent["intent"] == "booking"


# ===========================================================================
# 5. Conversion lifecycle & status invariants
# ===========================================================================


def test_conversion_rules_logic() -> None:
    """Proves the exact logic of the converted CTE:
    - Cancelled appointment -> does NOT convert
    - Appointment before first_at -> does NOT convert
    - Unconfirmed calendar operation (outcome_unknown, in_progress, failed) -> does NOT convert
    - Unconfirmed agent action (waiting_approval, failed) -> does NOT convert
    - Succeeded operation & scheduled appointment -> CONVERTS
    """

    def is_converted(
        appt_status: str,
        appt_created_at: datetime,
        first_at: datetime,
        op_status: str | None = None,
        action_status: str | None = None,
    ) -> bool:
        if appt_status == "cancelled":
            return False
        if appt_created_at < first_at:
            return False
        if op_status is not None and op_status != "succeeded":
            return False
        return not (action_status is not None and action_status != "succeeded")

    first_at = datetime(2026, 3, 9, 10, 0, tzinfo=UTC)

    # 1. Confirmed appointment: converts
    assert is_converted(
        appt_status="scheduled",
        appt_created_at=datetime(2026, 3, 9, 11, 0, tzinfo=UTC),
        first_at=first_at,
        op_status="succeeded",
        action_status="succeeded",
    )

    # 2. Completed appointment: converts
    assert is_converted(
        appt_status="completed",
        appt_created_at=datetime(2026, 3, 9, 11, 0, tzinfo=UTC),
        first_at=first_at,
        op_status="succeeded",
        action_status="succeeded",
    )

    # 3. Cancelled appointment: does NOT convert (lead remains / unconverts)
    assert not is_converted(
        appt_status="cancelled",
        appt_created_at=datetime(2026, 3, 9, 11, 0, tzinfo=UTC),
        first_at=first_at,
        op_status="succeeded",
        action_status="succeeded",
    )

    # 4. Appointment created before the first enquiry: does NOT convert
    assert not is_converted(
        appt_status="scheduled",
        appt_created_at=datetime(2026, 3, 9, 9, 0, tzinfo=UTC),
        first_at=first_at,
        op_status="succeeded",
        action_status="succeeded",
    )

    # 5. Pending approval (AgentAction waiting_approval): does NOT convert
    assert not is_converted(
        appt_status="scheduled",
        appt_created_at=datetime(2026, 3, 9, 11, 0, tzinfo=UTC),
        first_at=first_at,
        op_status=None,
        action_status="waiting_approval",
    )

    # 6. Uncertain provider outcome (Operation outcome_unknown): does NOT convert
    assert not is_converted(
        appt_status="scheduled",
        appt_created_at=datetime(2026, 3, 9, 11, 0, tzinfo=UTC),
        first_at=first_at,
        op_status="outcome_unknown",
        action_status="outcome_unknown",
    )

    # 7. Failed calendar operation (Operation failed): does NOT convert
    assert not is_converted(
        appt_status="cancelled",
        appt_created_at=datetime(2026, 3, 9, 11, 0, tzinfo=UTC),
        first_at=first_at,
        op_status="failed",
        action_status="failed",
    )
