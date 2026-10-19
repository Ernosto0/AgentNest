"""Placeholder rendering (business-knowledge.md §7.1)."""

import uuid
from dataclasses import dataclass
from typing import Any

import pytest

from app.knowledge.render import (
    FACT_NOT_USABLE,
    PLACEHOLDER_INVALID,
    placeholder_keys,
    render,
)


@dataclass(frozen=True)
class Fact:
    key: str
    value_type: str
    value: dict[str, Any]
    version: int = 1
    fact_id: uuid.UUID = uuid.uuid4()


MONTHLY = Fact(
    "pricing.membership_monthly",
    "money",
    {"amount": "6000.00", "currency": "TRY", "unit": "month"},
    version=3,
    fact_id=uuid.UUID(int=1),
)
REFORMER = Fact(
    "pricing.reformer_8_sessions",
    "money",
    {"amount": "4800.00", "currency": "TRY", "unit": "package"},
    fact_id=uuid.UUID(int=2),
)
PHONE = Fact(
    "contact.phone",
    "phone",
    {"e164": "+905550000000", "display": "0555 000 00 00"},
    fact_id=uuid.UUID(int=3),
)
HOURS = Fact(
    "hours.weekly",
    "weekly_hours",
    {
        "mon": [["07:00", "23:00"]],
        "tue": [["07:00", "23:00"]],
        "wed": [["07:00", "23:00"]],
        "thu": [["07:00", "23:00"]],
        "fri": [["07:00", "23:00"]],
        "sat": [["09:00", "21:00"]],
        "sun": [],
        "exceptions": [],
    },
    fact_id=uuid.UUID(int=4),
)
FACTS = [MONTHLY, REFORMER, PHONE, HOURS]


def test_a_placeholder_is_replaced_by_the_formatted_value_with_its_span() -> None:
    result = render("Aylık üyelik {{fact:pricing.membership_monthly}} dir.", FACTS, "tr")
    assert result.ok
    assert result.text == "Aylık üyelik 6.000 ₺ / ay dir."
    (span,) = result.spans
    assert result.text[span.start : span.end] == "6.000 ₺ / ay"
    assert (span.key, span.version, span.fact_id) == (MONTHLY.key, 3, MONTHLY.fact_id)
    assert result.used == ((MONTHLY.fact_id, 3),)
    assert result.used_keys == (MONTHLY.key,)


def test_the_same_template_renders_in_the_target_locale() -> None:
    template = "Monthly: {{fact:pricing.membership_monthly}}"
    assert render(template, FACTS, "en").text == "Monthly: TRY 6,000 / month"
    assert render(template, FACTS, "tr").text == "Monthly: 6.000 ₺ / ay"


def test_several_placeholders_have_correct_non_overlapping_spans() -> None:
    template = "{{fact:pricing.membership_monthly}} veya {{fact:pricing.reformer_8_sessions}}!"
    result = render(template, FACTS, "tr")
    assert result.text == "6.000 ₺ / ay veya 4.800 ₺ / paket!"
    shown = [result.text[s.start : s.end] for s in result.spans]
    assert shown == ["6.000 ₺ / ay", "4.800 ₺ / paket"]
    assert result.spans[0].end <= result.spans[1].start


def test_a_repeated_key_is_used_once_but_spanned_twice() -> None:
    result = render("{{fact:contact.phone}} / {{fact:contact.phone}}", FACTS, "tr")
    assert result.text == "0555 000 00 00 / 0555 000 00 00"
    assert len(result.spans) == 2 and len(result.used) == 1


def test_weekly_hours_render_grouped() -> None:
    result = render("Saatlerimiz: {{fact:hours.weekly}}", FACTS, "tr")
    assert result.text == "Saatlerimiz: Pzt–Cum 07:00–23:00, Cmt 09:00–21:00, Paz kapalı"


def test_the_short_format_drops_unit_and_conditions() -> None:
    result = render("{{fact:pricing.membership_monthly|short}}", FACTS, "tr")
    assert result.text == "6.000 ₺"


def test_an_unknown_key_is_fact_not_usable_and_nothing_is_rendered() -> None:
    result = render("Fiyat {{fact:pricing.unknown}} ve {{fact:contact.phone}}", FACTS, "tr")
    assert not result.ok
    assert [(e.code, e.key) for e in result.errors] == [(FACT_NOT_USABLE, "pricing.unknown")]
    assert result.text == "" and result.spans == () and result.used == ()  # no partial text


def test_a_fact_that_is_not_in_the_usable_list_is_not_rendered() -> None:
    # The caller passes usable facts only: an unverified/contested fact is simply absent.
    result = render("{{fact:pricing.membership_monthly}}", [REFORMER], "tr")
    assert not result.ok and result.errors[0].code == FACT_NOT_USABLE


@pytest.mark.parametrize(
    "template",
    [
        "{{fact:}}",
        "{{fact:Pricing.Monthly}}",
        "{{fact:nodot}}",
        "{{ fact : pricing.membership_monthly }}",
        "{{fact:pricing.membership_monthly",
        "pricing.membership_monthly}}",
        "{{pricing.membership_monthly}}",
    ],
)
def test_malformed_placeholders_never_leak_into_the_text(template: str) -> None:
    result = render(template, FACTS, "tr")
    assert not result.ok
    assert result.errors[0].code == PLACEHOLDER_INVALID and result.text == ""


def test_an_unknown_format_is_an_error() -> None:
    result = render("{{fact:pricing.membership_monthly|long}}", FACTS, "tr")
    assert [e.code for e in result.errors] == [PLACEHOLDER_INVALID]


def test_text_without_placeholders_is_returned_unchanged() -> None:
    result = render("Merhaba! Nasıl yardımcı olabilirim?", FACTS, "tr")
    assert result.ok and result.text == "Merhaba! Nasıl yardımcı olabilirim?"
    assert result.spans == () and result.used == ()


def test_placeholder_keys_lists_first_appearance_order_without_duplicates() -> None:
    template = "{{fact:b.x}} {{fact:a.y|short}} {{fact:b.x}}"
    assert placeholder_keys(template) == ["b.x", "a.y"]
