"""Exact reply-only Babel formats, leaving TR/EN unchanged."""

from datetime import date, time
from decimal import Decimal

import pytest

from app.knowledge.formatting import (
    format_money_amount,
    format_reply_date,
    format_reply_time,
    format_value,
)


@pytest.mark.parametrize(
    ("locale", "number", "whole"),
    [
        ("de", "1.234,50", "1.200"),
        ("ru", "1\u00a0234,50", "1\u00a0200"),
        ("ar", "1,234.50", "1,200"),
    ],
)
@pytest.mark.parametrize(
    ("currency", "symbol"),
    [("TRY", "₺"), ("EUR", "€"), ("USD", "$"), ("RUB", "₽"), ("GBP", "£"), ("JPY", "JPY")],
)
def test_money(locale, number, whole, currency, symbol):
    assert format_money_amount(Decimal("1234.50"), currency, locale) == number + "\u00a0" + symbol
    assert format_money_amount(Decimal("1200"), currency, locale) == whole + "\u00a0" + symbol


@pytest.mark.parametrize(
    ("locale", "number", "unit", "yes", "no", "share", "private"),
    [
        ("ru", "6\u00a0000", "месяц", "Да", "Нет", "Показывать цены", "Не показывать цены"),
        ("de", "6.000", "Monat", "Ja", "Nein", "Preise teilen", "Preise nicht teilen"),
        ("ar", "6,000", "شهر", "نعم", "لا", "مشاركة الأسعار", "عدم مشاركة الأسعار"),
    ],
)
def test_labels_conditions_and_fallback(locale, number, unit, yes, no, share, private):
    value = {
        "amount": "6000",
        "currency": "TRY",
        "unit": "month",
        "conditions": {"tr": "belge", "en": "valid ID"},
    }
    assert format_value("money", value, locale) == f"{number}\u00a0₺ / {unit} (valid ID)"
    assert format_value("boolean", {"value": True}, locale) == yes
    assert format_value("boolean", {"value": False}, locale) == no
    assert format_value("enum", {"value": "share"}, locale) == share
    assert format_value("enum", {"value": "do_not_share"}, locale) == private
    assert format_value("localized_text", {"tr": "Merhaba", "en": "Hello"}, locale) == "Hello"
    assert format_value("localized_text", {"tr": "Merhaba"}, locale) == "Merhaba"


HOURS = {
    "mon": [["09:00", "18:00"]],
    "tue": [["09:00", "18:00"]],
    "exceptions": [{"date": "2026-11-18", "closed": True}],
}


@pytest.mark.parametrize(
    ("locale", "expected", "day"),
    [
        ("ru", "пн–вт 09:00–18:00, ср–вс закрыто · 18 нояб.: закрыто", "18 ноября 2026"),
        (
            "de",
            "Mo.–Di. 09:00–18:00, Mi.–So. geschlossen · 18 Nov.: geschlossen",
            "18 November 2026",
        ),
        (
            "ar",
            "الاثنين–الثلاثاء 09:00\u200e–\u200e18:00, الأربعاء–الأحد مغلق · 18 نوفمبر: مغلق",
            "18 نوفمبر 2026",
        ),
    ],
)
def test_hours_and_date_helpers(locale, expected, day):
    assert format_value("weekly_hours", HOURS, locale) == expected
    assert format_reply_date(date(2026, 11, 18), locale) == day
    assert format_reply_time(time(9, 5), locale) == "09:05"
    opened = {
        **HOURS,
        "exceptions": [{"date": "2026-11-18", "closed": False, "ranges": [["10:00", "12:00"]]}],
    }
    dash = "\u200e–\u200e" if locale == "ar" else "–"
    assert format_value("weekly_hours", opened, locale).endswith(f"10:00{dash}12:00")


def test_tr_en_and_unknown_default():
    assert format_money_amount(Decimal("6000"), "TRY", "tr") == "6.000 ₺"
    assert format_money_amount(Decimal("1200"), "EUR", "en") == "€1,200"
    assert format_money_amount(Decimal("6000"), "TRY", "unknown") == "6.000 ₺"
