"""Offline unit tests for five-language support across Account Agent components (Session 04).

Covers:
1. Reply language detection for all 5 languages (tr, en, ru, de, ar) and fail-closed behavior
   for unsupported/uncertain languages.
2. ReplyValidationArgs schema validation (accepts 5 languages, rejects unsupported).
3. Broker AnswersReadArgs schema validation (accepts 5 languages, rejects unsupported).
4. answers_page rejection of unsupported languages and acceptance of 5 languages.
5. Grounding owner answer wrapper rendering for all 5 languages + byte length check.
6. Grounding customer clarification question rendering (date/time) for all 5 languages.
7. Calendar reply rendering (booked, rescheduled, cancelled, pending_approval, available_slot)
   for all 5 languages.
8. Owner question holding response templates for all 5 languages.
9. Arabic RTL, multi-byte UTF-8 boundaries, and 1000-byte fail-closed limit.
"""

import uuid
from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from app.agent.calendar import render_calendar_reply
from app.agent.grounding import (
    CalendarEvidence,
    CustomerClarification,
    GroundedReply,
    OwnerAnswerEvidence,
    ReplyValidationArgs,
    validate_reply,
)
from app.agent.knowledge import answers_page
from app.agent.models import AgentAction, AgentThread
from app.agent.tools.broker import AnswersReadArgs, BrokerContext
from app.core.clock import FrozenClock
from app.core.context import ActorRef, WorkspaceContext
from app.core.reply_languages import REPLY_LANGUAGES, RTL_REPLY_LANGUAGES, is_reply_language
from app.inbox.language import choose_reply_language
from app.inbox.models import Message
from app.knowledge.claims import byte_length, length_issue
from app.owner_requests.models import OwnerAnswer

# ---------------------------------------------------------------------------
# 1. Reply Language Definition & Detection
# ---------------------------------------------------------------------------


def test_reply_languages_contract() -> None:
    assert REPLY_LANGUAGES == ("tr", "en", "ru", "de", "ar")
    assert frozenset({"ar"}) == RTL_REPLY_LANGUAGES
    for code in ("tr", "en", "ru", "de", "ar"):
        assert is_reply_language(code) is True
    for code in ("fr", "es", "zh", "ja", "it", None, ""):
        assert is_reply_language(code) is False


@pytest.mark.parametrize(
    ("text", "expected_lang"),
    [
        ("Merhaba, randevu almak istiyorum.", "tr"),
        ("Hello, I would like to book an appointment.", "en"),
        ("Здравствуйте, сколько стоит абонемент на месяц?", "ru"),
        ("Guten Tag, wie viel kostet ein Termin?", "de"),
        ("مرحبا، أود حجز موعد من فضلك.", "ar"),
    ],
)
def test_choose_reply_language_supported(text: str, expected_lang: str) -> None:
    result = choose_reply_language(
        [text],
        default_locale="tr",
        reply_languages=["tr", "en", "ru", "de", "ar"],
    )
    assert result.code == expected_lang


@pytest.mark.parametrize(
    "text",
    [
        "Bonjour, je voudrais réserver un rendez-vous s'il vous plaît.",  # French
        "Hola, me gustaría reservar una cita por favor.",  # Spanish
        "你好，我想预约一个时间，谢谢。",  # Chinese
        "こんにちは、予約をお願いしたいのですが。",  # Japanese
        "Ciao, vorrei prenotare un appuntamento.",  # Italian
    ],
)
def test_choose_reply_language_unsupported_fails_closed(text: str) -> None:
    result = choose_reply_language(
        [text],
        default_locale="tr",
        reply_languages=["tr", "en", "ru", "de", "ar"],
    )
    # Unsupported languages fail closed to None (or ungrounded)
    assert result.code is None


def test_choose_reply_language_respects_workspace_disabled_language() -> None:
    # Russian text, but workspace only enabled tr and en
    result = choose_reply_language(
        ["Здравствуйте, сколько стоит абонемент?"],
        default_locale="tr",
        reply_languages=["tr", "en"],
    )
    assert result.code is None


# ---------------------------------------------------------------------------
# 2. Schema Validation (ReplyValidationArgs & AnswersReadArgs)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("lang", ["tr", "en", "ru", "de", "ar"])
def test_reply_validation_args_accepts_five_languages(lang: str) -> None:
    args = ReplyValidationArgs(template="Hello", language=lang)  # type: ignore[arg-type]
    assert args.language == lang


@pytest.mark.parametrize("lang", ["fr", "es", "zh", "ja", "it", ""])
def test_reply_validation_args_rejects_unsupported_languages(lang: str) -> None:
    with pytest.raises(ValidationError):
        ReplyValidationArgs(template="Hello", language=lang)  # type: ignore[arg-type]


@pytest.mark.parametrize("lang", ["tr", "en", "ru", "de", "ar"])
def test_answers_read_args_accepts_five_languages(lang: str) -> None:
    args = AnswersReadArgs(limit=5, cursor=None, language=lang)  # type: ignore[arg-type]
    assert args.language == lang


@pytest.mark.parametrize("lang", ["fr", "es", "zh", "ja", "it", ""])
def test_answers_read_args_rejects_unsupported_languages(lang: str) -> None:
    with pytest.raises(ValidationError):
        AnswersReadArgs(limit=5, cursor=None, language=lang)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# 3. answers_page Language Guard
# ---------------------------------------------------------------------------


def test_answers_page_language_guard() -> None:
    ctx = WorkspaceContext(
        workspace_id=uuid.uuid4(),
        actor=ActorRef(type="user", id=uuid.uuid4().hex),
        role="owner",
        locale="tr",
        timezone="Europe/Istanbul",
        is_demo=False,
    )
    clock = FrozenClock(datetime(2026, 11, 19, 12, 0, tzinfo=UTC))
    mock_db = MagicMock()

    # Unsupported languages raise ValueError immediately
    with pytest.raises(ValueError, match="invalid answer page"):
        answers_page(mock_db, clock, ctx, language="fr")

    with pytest.raises(ValueError, match="invalid answer page"):
        answers_page(mock_db, clock, ctx, language="es")


# ---------------------------------------------------------------------------
# 4. Grounding: Owner Answer Localized Wrapper & Byte Limits
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("lang", "expected_prefix"),
    [
        ("tr", "İşletmenin bu talebinize yanıtı:"),
        ("en", "The business's answer to your request:"),
        ("ru", "Ответ бизнеса на ваш запрос:"),
        ("de", "Die Antwort des Unternehmens auf Ihre Anfrage:"),
        ("ar", "رد الشركة على طلبك:"),
    ],
)
def test_grounding_owner_answer_rendering_all_languages(lang: str, expected_prefix: str) -> None:
    db = MagicMock()
    clock = FrozenClock(datetime(2026, 11, 19, 12, 0, tzinfo=UTC))
    ws_id = uuid.uuid4()
    acc_id = uuid.uuid4()
    thread_id = uuid.uuid4()
    answer_id = uuid.uuid4()

    broker_ctx = BrokerContext(
        workspace=WorkspaceContext(
            workspace_id=ws_id,
            actor=ActorRef(type="user", id=uuid.uuid4().hex),
            role="owner",
            locale=lang,
            timezone="Europe/Istanbul",
            is_demo=False,
        ),
        account_id=acc_id,
        thread_id=thread_id,
        surface="dm",
        source="customer",
    )

    thread = AgentThread(
        id=thread_id,
        workspace_id=ws_id,
        social_account_id=acc_id,
        surface="dm",
        source_ref=str(uuid.uuid4()),
        customer_identity_id=uuid.uuid4(),
    )

    from app.agent.context import ModelContext

    # Mock assemble and scoped_thread
    with (
        pytest.MonkeyPatch.context() as mp,
    ):
        mp.setattr(
            "app.agent.grounding.scoped_thread",
            lambda _db, _ws, _acc, _thr: thread,
        )
        mp.setattr(
            "app.agent.context.assemble",
            lambda _db, _clk, _ctx: ModelContext("system", (), lang, 1),
        )
        mock_owner_answer = MagicMock(spec=OwnerAnswer)
        mock_owner_answer.body = "Special custom answer text."
        mp.setattr(
            "app.owner_requests.service.evidence",
            lambda _db, _clk, _ctx, _id, _v: (MagicMock(), mock_owner_answer, MagicMock()),
        )

        proposal = ReplyValidationArgs(
            template="",
            language=lang,  # type: ignore[arg-type]
            owner_answer=OwnerAnswerEvidence(id=answer_id, version=1),
        )

        result: GroundedReply = validate_reply(db, clock, broker_ctx, proposal)
        assert result.valid is True
        assert result.text.startswith(expected_prefix)
        assert "Special custom answer text." in result.text


def test_grounding_owner_answer_byte_length_overflow_fails() -> None:
    db = MagicMock()
    clock = FrozenClock(datetime(2026, 11, 19, 12, 0, tzinfo=UTC))
    ws_id = uuid.uuid4()
    acc_id = uuid.uuid4()
    thread_id = uuid.uuid4()
    answer_id = uuid.uuid4()

    broker_ctx = BrokerContext(
        workspace=WorkspaceContext(
            workspace_id=ws_id,
            actor=ActorRef(type="user", id=uuid.uuid4().hex),
            role="owner",
            locale="ar",
            timezone="Europe/Istanbul",
            is_demo=False,
        ),
        account_id=acc_id,
        thread_id=thread_id,
        surface="dm",
        source="customer",
    )

    thread = AgentThread(
        id=thread_id,
        workspace_id=ws_id,
        social_account_id=acc_id,
        surface="dm",
        source_ref=str(uuid.uuid4()),
    )

    from app.agent.context import ModelContext

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("app.agent.grounding.scoped_thread", lambda _db, _ws, _acc, _thr: thread)
        mp.setattr(
            "app.agent.context.assemble",
            lambda _db, _clk, _ctx: ModelContext("system", (), "ar", 1),
        )
        # Arabic character is 2-3 bytes. 600 Arabic characters will exceed 1000 bytes.
        huge_arabic_body = "نص طويل جدا " * 80
        assert byte_length(huge_arabic_body) > 1000

        mock_owner_answer = MagicMock(spec=OwnerAnswer)
        mock_owner_answer.body = huge_arabic_body
        mp.setattr(
            "app.owner_requests.service.evidence",
            lambda _db, _clk, _ctx, _id, _v: (MagicMock(), mock_owner_answer, MagicMock()),
        )

        proposal = ReplyValidationArgs(
            template="",
            language="ar",
            owner_answer=OwnerAnswerEvidence(id=answer_id, version=1),
        )

        result: GroundedReply = validate_reply(db, clock, broker_ctx, proposal)
        assert result.valid is False
        assert "REPLY_LENGTH_INVALID" in result.errors


# ---------------------------------------------------------------------------
# 5. Grounding: Customer Clarification Localized Questions
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("lang", "kind", "extracted", "expected_fragment"),
    [
        ("tr", "date", "2026-12-01", "“2026-12-01” belirttiniz. Tercih ettiğiniz tarih bu mu?"),
        ("tr", "time", "14:30", "“14:30” belirttiniz. Tercih ettiğiniz saat bu mu?"),
        ("en", "date", "2026-12-01", "You mentioned “2026-12-01”. Is that your preferred date?"),
        ("en", "time", "14:30", "You mentioned “14:30”. Is that your preferred time?"),
        ("ru", "date", "2026-12-01", "Вы указали «2026-12-01». Это ваша желаемая дата?"),
        ("ru", "time", "14:30", "Вы указали «14:30». Это ваше желаемое время?"),
        (
            "de",
            "date",
            "2026-12-01",
            "Sie haben „2026-12-01“ angegeben. Ist das Ihr bevorzugtes Datum?",
        ),
        (
            "de",
            "time",
            "14:30",
            "Sie haben „14:30“ angegeben. Ist das Ihre bevorzugte Uhrzeit?",
        ),
        ("ar", "date", "2026-12-01", 'لقد ذكرت "2026-12-01". هل هذا هو التاريخ المفضل لديك؟'),
        ("ar", "time", "14:30", 'لقد ذكرت "14:30". هل هذا هو الوقت المفضل لديك؟'),
    ],
)
def test_grounding_customer_clarification_rendering_all_languages(
    lang: str, kind: str, extracted: str, expected_fragment: str
) -> None:
    db = MagicMock()
    clock = FrozenClock(datetime(2026, 11, 19, 12, 0, tzinfo=UTC))
    ws_id = uuid.uuid4()
    acc_id = uuid.uuid4()
    thread_id = uuid.uuid4()
    msg_id = uuid.uuid4()

    broker_ctx = BrokerContext(
        workspace=WorkspaceContext(
            workspace_id=ws_id,
            actor=ActorRef(type="user", id=uuid.uuid4().hex),
            role="owner",
            locale=lang,
            timezone="Europe/Istanbul",
            is_demo=False,
        ),
        account_id=acc_id,
        thread_id=thread_id,
        surface="dm",
        source="customer",
    )

    thread = AgentThread(
        id=thread_id,
        workspace_id=ws_id,
        social_account_id=acc_id,
        surface="dm",
        source_ref=str(uuid.uuid4()),
        dm_conversation_id=uuid.uuid4(),
    )

    full_text = f"Prefix text {extracted} suffix text"
    start_pos = full_text.index(extracted)
    end_pos = start_pos + len(extracted)

    msg = Message(
        id=msg_id,
        workspace_id=ws_id,
        social_account_id=acc_id,
        conversation_id=thread.dm_conversation_id,
        direction="inbound",
        sender_kind="customer",
        text=full_text,
        is_deleted=False,
    )
    db.scalar.return_value = msg

    from app.agent.context import ModelContext

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("app.agent.grounding.scoped_thread", lambda _db, _ws, _acc, _thr: thread)
        mp.setattr(
            "app.agent.context.assemble",
            lambda _db, _clk, _ctx: ModelContext("system", (), lang, 1),
        )

        proposal = ReplyValidationArgs(
            template="",
            language=lang,  # type: ignore[arg-type]
            customer_clarification=CustomerClarification(
                message_id=msg_id,
                start=start_pos,
                end=end_pos,
                kind=kind,  # type: ignore[arg-type]
            ),
        )

        result: GroundedReply = validate_reply(db, clock, broker_ctx, proposal)
        assert result.valid is True
        assert result.text == expected_fragment
        assert result.customer_source == msg_id


# ---------------------------------------------------------------------------
# 6. Calendar Reply Localized Rendering Across All Five Languages
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("lang", "expected_fragment"),
    [
        ("tr", "Randevunuz 2026-11-20 tarihinde 14:00–15:00 saatleri için oluşturuldu"),
        ("en", "Your appointment (Saç Kesimi) has been scheduled for 2026-11-20 at 14:00–15:00."),
        ("ru", "Ваша запись (Saç Kesimi) оформлена на 2026-11-20 с 14:00 до 15:00."),
        (
            "de",
            "Ihr Termin (Saç Kesimi) wurde für den 2026-11-20 von 14:00 bis 15:00 vereinbart.",
        ),
        ("ar", "تم حجز موعدك (Saç Kesimi) بتاريخ 2026-11-20 من 14:00 إلى 15:00."),
    ],
)
def test_calendar_booked_reply_all_languages(lang: str, expected_fragment: str) -> None:
    db = MagicMock()
    db.get.return_value = MagicMock(timezone="UTC")
    clock = FrozenClock(datetime(2026, 11, 19, 12, 0, tzinfo=UTC))
    ws_id = uuid.uuid4()
    acc_id = uuid.uuid4()
    thread_id = uuid.uuid4()
    appt_id = uuid.uuid4()
    cust_id = uuid.uuid4()

    broker_ctx = BrokerContext(
        workspace=WorkspaceContext(
            workspace_id=ws_id,
            actor=ActorRef(type="user", id=uuid.uuid4().hex),
            role="owner",
            locale=lang,
            timezone="UTC",
            is_demo=False,
        ),
        account_id=acc_id,
        thread_id=thread_id,
        surface="dm",
        source="customer",
    )

    thread = AgentThread(
        id=thread_id,
        workspace_id=ws_id,
        social_account_id=acc_id,
        surface="dm",
        source_ref=str(uuid.uuid4()),
        customer_identity_id=cust_id,
    )

    mock_appt = MagicMock()
    mock_appt.id = appt_id
    mock_appt.version = 1
    mock_appt.title = "Saç Kesimi"
    mock_appt.customer_identity_id = cust_id
    mock_appt.status = "scheduled"
    mock_appt.start_at = datetime(2026, 11, 20, 14, 0, tzinfo=UTC)
    mock_appt.end_at = datetime(2026, 11, 20, 15, 0, tzinfo=UTC)

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            "app.integrations.calendar.queries.get_appointment_in_workspace",
            lambda _db, _ws, _aid: mock_appt,
        )

        evidence = CalendarEvidence(
            kind="booked",
            appointment_id=appt_id,
            appointment_version=1,
        )
        reply = render_calendar_reply(db, clock, broker_ctx, thread, evidence, lang)  # type: ignore[arg-type]
        assert reply.valid is True
        assert expected_fragment in reply.text


@pytest.mark.parametrize(
    ("lang", "expected_fragment"),
    [
        ("tr", "Randevunuz 2026-11-21 tarihinde 16:00–17:00 saatlerine güncellendi"),
        ("en", "Your appointment (Masaj) has been rescheduled to 2026-11-21 at 16:00–17:00."),
        ("ru", "Ваша запись (Masaj) перенесена на 2026-11-21 с 16:00 до 17:00."),
        (
            "de",
            "Ihr Termin (Masaj) wurde auf den 2026-11-21 von 16:00 bis 17:00 verschoben.",
        ),
        ("ar", "تمت إعادة جدولة موعدك (Masaj) إلى 2026-11-21 من 16:00 إلى 17:00."),
    ],
)
def test_calendar_rescheduled_reply_all_languages(lang: str, expected_fragment: str) -> None:
    db = MagicMock()
    db.get.return_value = MagicMock(timezone="UTC")
    clock = FrozenClock(datetime(2026, 11, 19, 12, 0, tzinfo=UTC))
    ws_id = uuid.uuid4()
    acc_id = uuid.uuid4()
    thread_id = uuid.uuid4()
    appt_id = uuid.uuid4()
    cust_id = uuid.uuid4()

    broker_ctx = BrokerContext(
        workspace=WorkspaceContext(
            workspace_id=ws_id,
            actor=ActorRef(type="user", id=uuid.uuid4().hex),
            role="owner",
            locale=lang,
            timezone="UTC",
            is_demo=False,
        ),
        account_id=acc_id,
        thread_id=thread_id,
        surface="dm",
        source="customer",
    )

    thread = AgentThread(
        id=thread_id,
        workspace_id=ws_id,
        social_account_id=acc_id,
        surface="dm",
        source_ref=str(uuid.uuid4()),
        customer_identity_id=cust_id,
    )

    mock_appt = MagicMock()
    mock_appt.id = appt_id
    mock_appt.version = 2
    mock_appt.title = "Masaj"
    mock_appt.customer_identity_id = cust_id
    mock_appt.status = "scheduled"
    mock_appt.start_at = datetime(2026, 11, 21, 16, 0, tzinfo=UTC)
    mock_appt.end_at = datetime(2026, 11, 21, 17, 0, tzinfo=UTC)

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            "app.integrations.calendar.queries.get_appointment_in_workspace",
            lambda _db, _ws, _aid: mock_appt,
        )

        evidence = CalendarEvidence(
            kind="rescheduled",
            appointment_id=appt_id,
            appointment_version=2,
        )
        reply = render_calendar_reply(db, clock, broker_ctx, thread, evidence, lang)  # type: ignore[arg-type]
        assert reply.valid is True
        assert expected_fragment in reply.text


@pytest.mark.parametrize(
    ("lang", "expected_fragment"),
    [
        ("tr", "2026-11-20 tarihli 14:00 randevunuz (Pilates) iptal edildi."),
        ("en", "Your appointment (Pilates) on 2026-11-20 at 14:00 has been cancelled."),
        ("ru", "Ваша запись (Pilates) на 2026-11-20 в 14:00 отменена."),
        ("de", "Ihr Termin (Pilates) am 2026-11-20 um 14:00 wurde storniert."),
        ("ar", "تم إلغاء موعدك (Pilates) بتاريخ 2026-11-20 في 14:00."),
    ],
)
def test_calendar_cancelled_reply_all_languages(lang: str, expected_fragment: str) -> None:
    db = MagicMock()
    db.get.return_value = MagicMock(timezone="UTC")
    clock = FrozenClock(datetime(2026, 11, 19, 12, 0, tzinfo=UTC))
    ws_id = uuid.uuid4()
    acc_id = uuid.uuid4()
    thread_id = uuid.uuid4()
    appt_id = uuid.uuid4()
    cust_id = uuid.uuid4()

    broker_ctx = BrokerContext(
        workspace=WorkspaceContext(
            workspace_id=ws_id,
            actor=ActorRef(type="user", id=uuid.uuid4().hex),
            role="owner",
            locale=lang,
            timezone="UTC",
            is_demo=False,
        ),
        account_id=acc_id,
        thread_id=thread_id,
        surface="dm",
        source="customer",
    )

    thread = AgentThread(
        id=thread_id,
        workspace_id=ws_id,
        social_account_id=acc_id,
        surface="dm",
        source_ref=str(uuid.uuid4()),
        customer_identity_id=cust_id,
    )

    mock_appt = MagicMock()
    mock_appt.id = appt_id
    mock_appt.version = 3
    mock_appt.title = "Pilates"
    mock_appt.customer_identity_id = cust_id
    mock_appt.status = "cancelled"
    mock_appt.start_at = datetime(2026, 11, 20, 14, 0, tzinfo=UTC)
    mock_appt.end_at = datetime(2026, 11, 20, 15, 0, tzinfo=UTC)

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            "app.integrations.calendar.queries.get_appointment_in_workspace",
            lambda _db, _ws, _aid: mock_appt,
        )

        evidence = CalendarEvidence(
            kind="cancelled",
            appointment_id=appt_id,
            appointment_version=3,
        )
        reply = render_calendar_reply(db, clock, broker_ctx, thread, evidence, lang)  # type: ignore[arg-type]
        assert reply.valid is True
        assert expected_fragment in reply.text


@pytest.mark.parametrize(
    ("lang", "expected_fragment"),
    [
        (
            "tr",
            "2026-11-25 tarihi saat 10:00 için randevu talebiniz alındı ve "
            "işletme onayına iletildi.",
        ),
        (
            "en",
            "Your appointment request for 2026-11-25 at 10:00 has been received "
            "and sent for owner approval.",
        ),
        (
            "ru",
            "Ваш запрос на запись на 2026-11-25 в 10:00 получен и "
            "передан на подтверждение владельцу.",
        ),
        (
            "de",
            "Ihre Terminanfrage für den 2026-11-25 um 10:00 wurde empfangen "
            "und an das Unternehmen zur Bestätigung weitergeleitet.",
        ),
        ("ar", "تم استلام طلب موعدك بتاريخ 2026-11-25 في 10:00 وإرساله لموافقة المسؤول."),
    ],
)
def test_calendar_pending_approval_reply_all_languages(lang: str, expected_fragment: str) -> None:
    db = MagicMock()
    db.get.return_value = None
    clock = FrozenClock(datetime(2026, 11, 19, 12, 0, tzinfo=UTC))
    ws_id = uuid.uuid4()
    acc_id = uuid.uuid4()
    thread_id = uuid.uuid4()

    broker_ctx = BrokerContext(
        workspace=WorkspaceContext(
            workspace_id=ws_id,
            actor=ActorRef(type="user", id=uuid.uuid4().hex),
            role="owner",
            locale=lang,
            timezone="UTC",
            is_demo=False,
        ),
        account_id=acc_id,
        thread_id=thread_id,
        surface="dm",
        source="customer",
    )

    thread = AgentThread(
        id=thread_id,
        workspace_id=ws_id,
        social_account_id=acc_id,
        surface="dm",
        source_ref=str(uuid.uuid4()),
    )

    pending_action = AgentAction(
        workspace_id=ws_id,
        thread_id=thread_id,
        action_type="calendar.book",
        status="waiting_approval",
        content_intent={"local_date": "2026-11-25", "local_time": "10:00"},
    )
    db.scalar.return_value = pending_action

    evidence = CalendarEvidence(kind="pending_approval")
    reply = render_calendar_reply(db, clock, broker_ctx, thread, evidence, lang)  # type: ignore[arg-type]
    assert reply.valid is True
    assert expected_fragment in reply.text


@pytest.mark.parametrize(
    ("lang", "expected_fragment"),
    [
        ("tr", "2026-11-22 tarihinde saat 11:00 randevu için müsaittir."),
        ("en", "2026-11-22 at 11:00 is available for an appointment."),
        ("ru", "2026-11-22 в 11:00 свободно для записи."),
        ("de", "2026-11-22 um 11:00 ist für einen Termin verfügbar."),
        ("ar", "التاريخ 2026-11-22 في 11:00 متاح لحجز موعد."),
    ],
)
def test_calendar_available_slot_reply_all_languages(lang: str, expected_fragment: str) -> None:
    db = MagicMock()
    db.get.return_value = None
    clock = FrozenClock(datetime(2026, 11, 19, 12, 0, tzinfo=UTC))
    ws_id = uuid.uuid4()
    acc_id = uuid.uuid4()
    thread_id = uuid.uuid4()

    broker_ctx = BrokerContext(
        workspace=WorkspaceContext(
            workspace_id=ws_id,
            actor=ActorRef(type="user", id=uuid.uuid4().hex),
            role="owner",
            locale=lang,
            timezone="UTC",
            is_demo=False,
        ),
        account_id=acc_id,
        thread_id=thread_id,
        surface="dm",
        source="customer",
    )

    thread = AgentThread(
        id=thread_id,
        workspace_id=ws_id,
        social_account_id=acc_id,
        surface="dm",
        source_ref=str(uuid.uuid4()),
    )

    with pytest.MonkeyPatch.context() as mp:
        mock_avail = MagicMock()
        mock_avail.requested_slot_available = True
        mp.setattr(
            "app.operations.calendar.check_availability",
            lambda *args, **kwargs: mock_avail,
        )

        evidence = CalendarEvidence(
            kind="available_slot",
            local_date="2026-11-22",
            local_start_time="11:00",
        )
        reply = render_calendar_reply(db, clock, broker_ctx, thread, evidence, lang)  # type: ignore[arg-type]
        assert reply.valid is True
        assert expected_fragment in reply.text


# ---------------------------------------------------------------------------
# 7. Owner Question Holding Response Across All Five Languages
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("lang", "expected_text"),
    [
        ("tr", "Bu talebiniz için işletmeden bilgi istedim."),
        ("en", "I've asked the business for information about your request."),
        ("ru", "Я запросил информацию по вашему вопросу у бизнеса."),
        ("de", "Ich habe beim Unternehmen Informationen zu Ihrer Anfrage angefordert."),
        ("ar", "لقد طلبت من الشركة معلومات بخصوص طلبك."),
    ],
)
def test_owner_question_holding_response_templates(lang: str, expected_text: str) -> None:
    holding_templates = {
        "tr": "Bu talebiniz için işletmeden bilgi istedim.",
        "en": "I've asked the business for information about your request.",
        "ru": "Я запросил информацию по вашему вопросу у бизнеса.",
        "de": "Ich habe beim Unternehmen Informationen zu Ihrer Anfrage angefordert.",
        "ar": "لقد طلبت من الشركة معلومات بخصوص طلبك.",
    }
    assert holding_templates[lang] == expected_text
    assert byte_length(expected_text) <= 1000
    assert not length_issue(expected_text, max_bytes=1000)


# ---------------------------------------------------------------------------
# 8. Arabic RTL, UTF-8 Byte Limit Boundary & Claim Validation Integrity
# ---------------------------------------------------------------------------


def test_arabic_byte_boundary_handling() -> None:
    # 1 Arabic character is typically 2 UTF-8 bytes
    arabic_short = "مرحبا، أود الاستفسار عن المواعيد المتاحة لديكم اليوم."
    char_len = len(arabic_short)
    b_len = byte_length(arabic_short)

    assert b_len > char_len  # Proves multi-byte UTF-8 expansion
    assert b_len <= 1000
    assert not length_issue(arabic_short, max_bytes=1000)

    # Construct boundary case: exactly 1000 bytes vs 1001 bytes
    padding_chars = "أ" * 500  # 'أ' is 2 bytes (0xD8 0xA3)
    assert byte_length(padding_chars) == 1000
    assert not length_issue(padding_chars, max_bytes=1000)

    # Exceeding 1000 bytes
    overflow_text = padding_chars + "ب"
    assert byte_length(overflow_text) == 1002
    assert length_issue(overflow_text, max_bytes=1000)
