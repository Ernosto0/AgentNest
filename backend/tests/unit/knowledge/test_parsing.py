"""Money, phone and hours parsing (P2-01). The money vectors in ``shared/money-cases.json``
are also run by the frontend tests, so the two parsers cannot drift apart."""

import json
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from app.knowledge.parsing import (
    Money,
    ParseAmbiguity,
    ParseError,
    ascii_fold,
    hours_from_editor,
    normalize_for_match,
    parse_money,
    parse_phone,
    tr_casefold,
)

CASES: list[dict[str, Any]] = json.loads(
    (Path(__file__).parents[4] / "shared" / "money-cases.json").read_text(encoding="utf-8")
)


def _money(pair: list[str]) -> Money:
    return Money(Decimal(pair[0]), pair[1])


def test_there_are_at_least_thirty_vectors_in_both_languages() -> None:
    assert len(CASES) >= 30
    assert {case["locale"] for case in CASES} == {"tr", "en"}


@pytest.mark.parametrize("case", CASES, ids=lambda c: f"{c['locale']}:{c['text']!r}")
def test_money_vector(case: dict[str, Any]) -> None:
    if "error" in case:
        with pytest.raises(ParseError) as raised:
            parse_money(case["text"], case["locale"], case["currency"])
        assert raised.value.code == case["error"]
        return
    result = parse_money(case["text"], case["locale"], case["currency"])
    if "ambiguous" in case:
        assert isinstance(result, ParseAmbiguity)
        assert list(result.alternatives) == [_money(pair) for pair in case["ambiguous"]]
    else:
        assert result == _money(case["money"])


def test_unsupported_locale_is_rejected() -> None:
    with pytest.raises(ParseError):
        parse_money("7", "de", "EUR")


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("0555 000 00 00", "+905550000000"),
        ("+90 555 000 00 00", "+905550000000"),
        ("0090 555 000 00 00", "+905550000000"),
        ("905550000000", "+905550000000"),
        ("555 000 00 00", "+905550000000"),
        ("(0212) 000 00 00", "+902120000000"),
        ("+44 20 7946 0958", "+442079460958"),
    ],
)
def test_phone_numbers_normalise_to_e164(text: str, expected: str) -> None:
    assert parse_phone(text) == expected


@pytest.mark.parametrize("text", ["", "abc", "123", "0155 000 00 00", "+90 555 000 00"])
def test_invalid_phone_numbers_are_rejected(text: str) -> None:
    with pytest.raises(ParseError):
        parse_phone(text)


def test_turkish_case_folding_distinguishes_dotted_and_dotless_i() -> None:
    assert tr_casefold("IŞIK") == "ışık"
    assert tr_casefold("İSTANBUL") == "istanbul"
    assert normalize_for_match("  Aylık   ÜYELİK ") == "aylık üyelik"
    assert tr_casefold("I") != tr_casefold("İ")  # plain .lower() would make them equal-ish
    assert ascii_fold("LİRA") == ascii_fold("LIRA") == "lira"


def test_hours_editor_builds_the_canonical_value() -> None:
    value = hours_from_editor(
        [
            {"days": ["mon", "tue", "wed", "thu", "fri"], "ranges": [["07:00", "23:00"]]},
            {"days": ["sat"], "ranges": [["09:00", "21:00"]]},
            {"days": ["sun"], "ranges": []},
        ],
        [{"date": "2026-10-29", "closed": True}],
    )
    assert value["mon"] == [["07:00", "23:00"]]
    assert value["sun"] == []
    assert value["exceptions"] == [{"date": "2026-10-29", "closed": True, "ranges": []}]


def test_hours_editor_rejects_a_day_in_two_rows_and_unknown_days() -> None:
    with pytest.raises(ParseError) as duplicate:
        hours_from_editor([{"days": ["mon"], "ranges": []}, {"days": ["mon"], "ranges": []}])
    assert duplicate.value.code == "duplicate_day"
    with pytest.raises(ParseError):
        hours_from_editor([{"days": ["funday"], "ranges": []}])
