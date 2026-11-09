"""Unit tests for narrator.py (conversational speech and INV-08 numeric grounding)."""

from app.commands.narrator import narrate_fallback, validate_metrics_grounding
from app.integrations.channels.base import ChannelRecipient
from app.integrations.channels.formatting import (
    format_command_for_telegram,
    format_command_for_whatsapp,
)


def test_narrate_activity_summary_english_when_asking_dm_answers():
    params = {
        "period": "last_7_days",
        "inbound_messages": 11,
        "conversations": 1,
        "replies_sent": 11,
        "replies_auto": 5,
        "replies_approved": 4,
        "replies_by_owner": 2,
        "escalations": 1,
        "attention_now": 0,
    }
    query = "How many dms did you answer this week?"
    narrated = narrate_fallback(
        "command.activity_summary", params, user_locale="en", user_query=query
    )

    assert "11" in narrated
    assert "5 automatically" in narrated
    assert "4 after your approval" in narrated
    assert "2 yourself" in narrated
    assert "everything is caught up right now" in narrated
    # INV-08 check
    problems = validate_metrics_grounding(narrated, params)
    assert problems == []


def test_narrate_activity_summary_turkish():
    params = {
        "period": "today",
        "inbound_messages": 15,
        "conversations": 8,
        "replies_sent": 40,
        "replies_auto": 13,
        "replies_approved": 12,
        "replies_by_owner": 14,
        "escalations": 7,
        "attention_now": 0,
    }
    query = "Bugün kaç DM yanıtladın?"
    narrated = narrate_fallback(
        "command.activity_summary", params, user_locale="tr", user_query=query
    )

    assert "40" in narrated
    assert "13 otomatik" in narrated
    assert "12 onayınızla" in narrated
    assert "14 tanesini doğrudan siz" in narrated
    problems = validate_metrics_grounding(narrated, params)
    assert problems == []


def test_validate_metrics_grounding_rejects_hallucinated_numbers():
    params = {"inbound_messages": 5, "conversations": 2}
    valid = "You received 5 messages across 2 conversations."
    assert validate_metrics_grounding(valid, params) == []

    hallucinated = "You received 50 messages across 99 conversations."
    problems = validate_metrics_grounding(hallucinated, params)
    assert len(problems) > 0


def test_format_command_for_telegram_and_whatsapp():
    class DummyCmd:
        status = "completed"
        raw_text = "How many dms did you answer this week?"
        result = {
            "message_key": "command.activity_summary",
            "params": {
                "period": "last_7_days",
                "inbound_messages": 11,
                "conversations": 1,
                "replies_sent": 11,
                "replies_auto": 5,
                "replies_approved": 4,
                "replies_by_owner": 2,
                "escalations": 1,
                "attention_now": 0,
            },
            "links": [{"target": "report", "date": "2026-01-15"}],
        }

    recipient = ChannelRecipient(
        user_id="u1",  # type: ignore
        workspace_id="w1",  # type: ignore
        channel="telegram",
        channel_chat_id="12345",
        ui_locale="en",
    )

    tg_text, markup = format_command_for_telegram(DummyCmd(), recipient)
    assert tg_text.startswith("💬 ")
    assert "11" in tg_text
    assert markup is not None
    assert "inline_keyboard" in markup

    wa_text = format_command_for_whatsapp(DummyCmd(), recipient)
    assert wa_text.startswith("💬 ")
    assert "11" in wa_text


def test_format_command_unsupported_with_reply_text():
    class DummyUnsupportedCmd:
        status = "unsupported"
        raw_text = "Merhaba"
        result = {
            "message_key": "command.unsupported",
            "reply_text": "Merhaba! Size nasıl yardımcı olabilirim?",
            "params": {"reason": "other"},
            "links": [],
        }

    recipient = ChannelRecipient(
        user_id="u1",  # type: ignore
        workspace_id="w1",  # type: ignore
        channel="telegram",
        channel_chat_id="12345",
        ui_locale="tr",
    )

    tg_text, _ = format_command_for_telegram(DummyUnsupportedCmd(), recipient)
    assert tg_text == "💬 Merhaba! Size nasıl yardımcı olabilirim?"

    wa_text = format_command_for_whatsapp(DummyUnsupportedCmd(), recipient)
    assert wa_text == "💬 Merhaba! Size nasıl yardımcı olabilirim?"


def test_validate_metrics_grounding_allows_user_query_numbers():
    params = {"monthly_membership": "5000 TL"}
    query = "Aylık üyelik 7000 TL mi?"
    # Model repeats the user's question or addresses 7000
    narrated = "Aylık üyelik ücreti 7000 TL değil, 5000 TL."
    problems = validate_metrics_grounding(narrated, params, user_query=query)
    assert problems == []
