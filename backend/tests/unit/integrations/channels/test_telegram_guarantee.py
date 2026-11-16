"""D-01: the Telegram daily summary ends with the two guarantee numbers, taken from the daily
report's summary dict, shown at zero and omitted when the report has no such number."""

from app.integrations.channels.telegram.handlers import _guarantee_lines


def test_both_numbers_are_shown_even_at_zero_in_english() -> None:
    text = _guarantee_lines({"replies_sent": 12, "unverified_values_sent": 0}, False)
    assert text == "• <b>Replies sent:</b> 12\n• <b>Replies with unverified values sent:</b> 0"


def test_the_turkish_lines_carry_the_same_numbers() -> None:
    text = _guarantee_lines({"replies_sent": 3, "unverified_values_sent": 2}, True)
    assert "<b>Gönderilen yanıtlar:</b> 3" in text
    assert "<b>Doğrulanmamış değer gönderilen yanıt:</b> 2" in text


def test_nothing_is_shown_when_the_report_has_no_such_number() -> None:
    assert _guarantee_lines({"replies_sent": 5, "unverified_values_sent": None}, True) == ""
    assert _guarantee_lines({"replies_sent": 5}, False) == ""
