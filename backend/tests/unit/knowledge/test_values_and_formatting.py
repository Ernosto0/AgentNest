"""Value validation (canonical form) and rendering for people (P2-01)."""

from decimal import Decimal
from typing import Any

import pytest

from app.core.errors import AppError
from app.knowledge.formatting import format_money_amount, format_value
from app.knowledge.values import validate_value, values_equal


def _errors(exc: pytest.ExceptionInfo[AppError]) -> dict[str, str]:
    return {e["field"]: e["code"] for e in exc.value.params["errors"]}


# --- validation -----------------------------------------------------------------------------


def test_money_is_canonical_two_decimal_string_and_drops_empty_conditions() -> None:
    value = validate_value(
        "money", {"amount": "6000", "currency": "TRY", "unit": "month", "conditions": {"tr": " "}}
    )
    assert value == {"amount": "6000.00", "currency": "TRY", "unit": "month"}


def test_money_currency_defaults_to_the_workspace_currency() -> None:
    value = validate_value("money", {"amount": "10"}, default_currency="EUR")
    assert value["currency"] == "EUR"


@pytest.mark.parametrize(
    ("amount", "code"),
    [(-1, "amount_negative"), ("-5", "amount_negative"), ("1.234", "too_many_decimals")],
)
def test_money_rejects_negative_and_over_precise_amounts(amount: Any, code: str) -> None:
    with pytest.raises(AppError) as raised:
        validate_value("money", {"amount": amount, "currency": "TRY"})
    assert _errors(raised)["value.amount"] == code


def test_money_never_accepts_floats() -> None:
    with pytest.raises(AppError) as raised:
        validate_value("money", {"amount": 6000.0, "currency": "TRY"})
    assert _errors(raised)["value.amount"] == "amount_must_be_decimal_string"


def test_weekly_hours_are_sorted_and_validated() -> None:
    value = validate_value(
        "weekly_hours",
        {
            "mon": [["14:00", "20:00"], ["07:00", "12:00"]],
            "exceptions": [
                {"date": "2026-12-25", "closed": True},
                {"date": "2026-10-29", "closed": True},
            ],
        },
    )
    assert value["mon"] == [["07:00", "12:00"], ["14:00", "20:00"]]
    assert [e["date"] for e in value["exceptions"]] == ["2026-10-29", "2026-12-25"]


@pytest.mark.parametrize(
    "mon",
    [[["22:00", "02:00"]], [["09:00", "09:00"]], [["09:00", "13:00"], ["12:00", "15:00"]]],
)
def test_weekly_hours_reject_overnight_empty_and_overlapping_ranges(mon: list[list[str]]) -> None:
    with pytest.raises(AppError):
        validate_value("weekly_hours", {"mon": mon})


def test_phone_display_is_derived_and_email_is_lowercased() -> None:
    assert validate_value("phone", {"e164": "+905550000000", "display": "x"}) == {
        "e164": "+905550000000",
        "display": "0555 000 00 00",
    }
    assert validate_value("email", {"email": " Info@Example.COM "}) == {"email": "info@example.com"}


def test_enum_must_be_one_of_the_allowed_values() -> None:
    assert validate_value("enum", {"value": "share"}, allowed_values=("share", "do_not_share"))
    with pytest.raises(AppError) as raised:
        validate_value("enum", {"value": "maybe"}, allowed_values=("share", "do_not_share"))
    assert _errors(raised)["value.value"] == "not_allowed"


def test_text_and_lists_are_cleaned() -> None:
    assert validate_value("text", {"text": "  Hello   world \r\n"}) == {"text": "Hello world"}
    assert validate_value("string_list", {"items": ["avukat", " Avukat ", "", "avukat"]}) == {
        "items": ["avukat", "Avukat"]
    }
    with pytest.raises(AppError):
        validate_value("localized_text", {"tr": " ", "en": None})


def test_unknown_type_and_non_object_values_fail_validation() -> None:
    with pytest.raises(AppError):
        validate_value("nope", {})
    with pytest.raises(AppError):
        validate_value("text", "just a string")  # type: ignore[arg-type]


def test_equality_compares_canonical_forms() -> None:
    a = {"amount": "6000", "currency": "TRY"}
    b = {"amount": "6000.00", "currency": "TRY", "conditions": None}
    assert values_equal("money", a, b)
    assert not values_equal("money", a, {"amount": "6001", "currency": "TRY"})
    assert not values_equal("money", a, {**a, "unit": "month"})


# --- formatting -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("amount", "currency", "locale", "expected"),
    [
        ("6000.00", "TRY", "tr", "6.000 ₺"),
        ("7000.50", "TRY", "tr", "7.000,50 ₺"),
        ("1200.00", "EUR", "en", "€1,200"),
        ("6000.00", "TRY", "en", "TRY 6,000"),
        ("1200.00", "EUR", "tr", "1.200 €"),
        ("50.00", "USD", "en", "$50"),
        ("0.50", "TRY", "tr", "0,50 ₺"),
    ],
)
def test_money_amounts_render_like_the_docs(
    amount: str, currency: str, locale: str, expected: str
) -> None:
    assert format_money_amount(Decimal(amount), currency, locale) == expected


def test_money_with_unit_and_conditions() -> None:
    value = {
        "amount": "4500.00",
        "currency": "TRY",
        "unit": "month",
        "conditions": {"tr": "geçerli öğrenci belgesi", "en": "valid student ID"},
    }
    assert format_value("money", value, "tr") == "4.500 ₺ / ay (geçerli öğrenci belgesi)"
    assert format_value("money", value, "en") == "TRY 4,500 / month (valid student ID)"


HOURS: dict[str, Any] = {
    "mon": [["07:00", "23:00"]],
    "tue": [["07:00", "23:00"]],
    "wed": [["07:00", "23:00"]],
    "thu": [["07:00", "23:00"]],
    "fri": [["07:00", "23:00"]],
    "sat": [["09:00", "21:00"]],
    "sun": [],
    "exceptions": [{"date": "2026-10-29", "closed": True, "ranges": []}],
}


def test_weekly_hours_group_consecutive_days() -> None:
    assert format_value("weekly_hours", HOURS, "tr") == (
        "Pzt–Cum 07:00–23:00, Cmt 09:00–21:00, Paz kapalı · 29 Eki: kapalı"
    )
    assert format_value("weekly_hours", HOURS, "en") == (
        "Mon–Fri 07:00–23:00, Sat 09:00–21:00, Sun closed · 29 Oct: closed"
    )


def test_split_shifts_and_open_exceptions() -> None:
    hours = {
        **HOURS,
        "sat": [["09:00", "12:00"], ["14:00", "18:00"]],
        "exceptions": [{"date": "2026-12-31", "closed": False, "ranges": [["09:00", "13:00"]]}],
    }
    assert "Cmt 09:00–12:00 & 14:00–18:00" in format_value("weekly_hours", hours, "tr")
    assert format_value("weekly_hours", hours, "en").endswith("· 31 Dec: 09:00–13:00")


def test_other_types_render_in_the_requested_locale_with_fallback() -> None:
    assert format_value("boolean", {"value": True}, "tr") == "Evet"
    assert format_value("boolean", {"value": False}, "en") == "No"
    assert format_value("enum", {"value": "share"}, "en") == "Share prices"
    assert format_value("localized_text", {"tr": "Merhaba"}, "en", "tr") == "Merhaba"
    assert format_value("localized_text", {"tr": "Merhaba", "en": "Hello"}, "en") == "Hello"
    address = {"lines": ["Örnek Mah. Demo Sok. No: 1"], "district": "Bucak", "city": "Burdur"}
    assert format_value("address", address, "tr") == "Örnek Mah. Demo Sok. No: 1, Bucak / Burdur"
    assert format_value("string_list", {"items": ["a", "b"]}, "tr") == "a, b"
    assert format_value("phone", {"e164": "+905550000000", "display": "0555 000 00 00"}, "tr") == (
        "0555 000 00 00"
    )


def test_address_lines_must_be_strings_and_are_never_dropped_silently() -> None:
    # In YAML, an unquoted ``No: 1`` is a mapping; that must fail loudly, not vanish.
    with pytest.raises(AppError) as raised:
        validate_value("address", {"lines": [{"No": 1}], "city": "Burdur"})
    assert _errors(raised)["value.lines"] == "invalid_line"
    assert validate_value("address", {"lines": [" A ", ""], "city": " Burdur "}) == {
        "lines": ["A"],
        "city": "Burdur",
    }
