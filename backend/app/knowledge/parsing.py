"""Locale-aware parsing of user-entered values (ADR-016, business-knowledge.md §2).

Money notation is the main risk (``7.000`` is 7000 in Turkish and 7 in English), so
``parse_money`` returns a ``ParseAmbiguity`` with the plausible readings whenever the notation
is foreign to the locale. Callers must then ask the user to confirm; they never guess.
"""

import re
import unicodedata
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

from app.knowledge.values import WEEKDAYS, validate_value

CENTS = Decimal("0.01")


class ParseError(ValueError):
    """The text cannot be read as the requested value. ``code`` is a stable machine code."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class Money:
    amount: Decimal
    currency: str


@dataclass(frozen=True)
class ParseAmbiguity:
    """More than one plausible reading (or a notation foreign to the locale): confirm first."""

    alternatives: tuple[Money, ...]
    reason: str


# --- Turkish-aware text helpers -----------------------------------------------------------


def tr_casefold(text: str) -> str:
    """Lowercase with Turkish dotted/dotless I rules (``I``→``ı``, ``İ``→``i``).

    Never use plain ``.lower()`` on Turkish text for matching (ADR-016).
    """
    return unicodedata.normalize("NFC", text).replace("İ", "i").replace("I", "ı").lower()


_ASCII_MAP = str.maketrans("çğıöşüâîû", "cgiosuaiu")


def ascii_fold(text: str) -> str:
    """Case- and diacritic-insensitive form for loose token matching (LİRA, LIRA, lıra)."""
    folded = unicodedata.normalize("NFC", text).replace("İ", "i").replace("I", "i").lower()
    return folded.translate(_ASCII_MAP)


def normalize_for_match(text: str) -> str:
    """Key for comparing user-typed labels: Turkish case folding and collapsed whitespace."""
    return re.sub(r"\s+", " ", tr_casefold(text)).strip()


# --- money --------------------------------------------------------------------------------

_CURRENCY_TOKENS: dict[str, str] = {
    "₺": "TRY",
    "tl": "TRY",
    "try": "TRY",
    "lira": "TRY",
    "turk lirasi": "TRY",
    "€": "EUR",
    "eur": "EUR",
    "euro": "EUR",
    "$": "USD",
    "usd": "USD",
    "dolar": "USD",
    "dollar": "USD",
    "dollars": "USD",
    "£": "GBP",
    "gbp": "GBP",
    "sterlin": "GBP",
}
_MULTIPLIERS: dict[str, int] = {
    "bin": 1000,
    "k": 1000,
    "thousand": 1000,
    "milyon": 1_000_000,
    "million": 1_000_000,
}
_GROUPING = {"tr": ".", "en": ","}
_DECIMAL = {"tr": ",", "en": "."}
_NUMBER_RE = re.compile(r"^\d[\d.,\s]*$")


def _split_tokens(text: str, default_currency: str) -> tuple[str, str, int]:
    """Return (number text, currency, multiplier) after removing currency/multiplier words."""
    work = ascii_fold(text.replace(" ", " ")).strip()
    currency = default_currency
    # Longest tokens first so "turk lirasi" wins over "lira".
    for token in sorted(_CURRENCY_TOKENS, key=len, reverse=True):
        pattern = (
            re.escape(token)
            if not token.isalpha() and len(token) == 1
            else rf"(?<![a-z]){re.escape(token)}(?![a-z])"
        )
        if re.search(pattern, work):
            currency = _CURRENCY_TOKENS[token]
            work = re.sub(pattern, " ", work, count=1)
            break
    multiplier = 1
    for word, factor in _MULTIPLIERS.items():
        pattern = rf"(?<![a-z]){word}(?![a-z])" if len(word) > 1 else r"(?<=\d)k(?![a-z])"
        if re.search(pattern, work):
            multiplier = factor
            work = re.sub(pattern, " ", work, count=1)
            break
    return work.strip(), currency, multiplier


def _only_groups_of_three(digits: list[str]) -> bool:
    head, *rest = digits
    return 1 <= len(head) <= 3 and head != "0" and all(len(group) == 3 for group in rest)


def _quantize(value: Decimal) -> Decimal:
    if value != value.quantize(CENTS):
        raise ParseError("too_many_decimals")
    return value.quantize(CENTS)


def _read_number(number: str, locale: str) -> tuple[list[Decimal], str | None]:
    """Possible numeric readings of ``number`` (most plausible first) and an ambiguity reason."""
    # "7 000" style space grouping
    if re.search(r"\d\s+\d", number):
        compact = re.sub(r"(?<=\d)\s+(?=\d{3}(?!\d))", "", number)
        if re.search(r"\d\s+\d", compact):
            raise ParseError("invalid_number")
        number = compact
    number = number.replace(" ", "")
    if not number or not _NUMBER_RE.match(number):
        raise ParseError("invalid_number")

    dots, commas = number.count("."), number.count(",")
    if dots == 0 and commas == 0:
        return [Decimal(number)], None

    if dots and commas:  # the last separator is the decimal one, the other must group
        decimal_sep = "." if number.rfind(".") > number.rfind(",") else ","
        group_sep = "," if decimal_sep == "." else "."
        integer, _, fraction = number.rpartition(decimal_sep)
        groups = integer.split(group_sep)
        if group_sep in fraction or decimal_sep in integer or not _only_groups_of_three(groups):
            raise ParseError("invalid_number")
        if not fraction or len(fraction) > 2:
            raise ParseError("too_many_decimals" if fraction else "invalid_number")
        return [Decimal("".join(groups) + "." + fraction)], None

    separator = "." if dots else ","
    parts = number.split(separator)
    if len(parts) > 2:  # repeated separator: can only be grouping
        if not _only_groups_of_three(parts):
            raise ParseError("invalid_number")
        return [Decimal("".join(parts))], None

    integer, fraction = parts
    if not fraction:
        raise ParseError("invalid_number")
    if len(fraction) in (1, 2):  # cannot be grouping
        return [Decimal(f"{integer}.{fraction}")], None
    if len(fraction) > 3 or integer == "0":
        raise ParseError("too_many_decimals")
    # exactly three digits after a single separator: grouping or a 3-decimal fraction
    grouped = Decimal(integer + fraction) if _only_groups_of_three([integer, fraction]) else None
    if grouped is None:
        raise ParseError("too_many_decimals")
    if separator == _GROUPING[locale]:
        return [grouped], None
    decimal_reading = Decimal(f"{integer}.{fraction}")
    readings = [grouped]
    if decimal_reading == decimal_reading.quantize(CENTS):
        readings.append(decimal_reading)
    return readings, "foreign_notation"


def parse_money(text: str, locale: str, default_currency: str) -> Money | ParseAmbiguity:
    """Parse ``text`` ("7.000 TL", "7 bin", "€1,200", "7,5 bin") for ``locale`` (tr|en).

    Raises ``ParseError`` when the text is not an amount. Returns ``ParseAmbiguity`` when the
    notation is foreign to the locale (e.g. ``7.000`` in an English workspace).
    """
    if locale not in _GROUPING:
        raise ParseError("unsupported_locale")
    number, currency, multiplier = _split_tokens(text, default_currency)
    if not number:
        raise ParseError("invalid_number")
    readings, reason = _read_number(number, locale)
    try:
        amounts = [_quantize(reading * multiplier) for reading in readings]
    except InvalidOperation as exc:
        raise ParseError("invalid_number") from exc
    money = tuple(Money(amount, currency) for amount in amounts)
    if reason is not None:
        return ParseAmbiguity(alternatives=money, reason=reason)
    return money[0]


# --- phone --------------------------------------------------------------------------------

_E164_DIGITS = re.compile(r"^\+[1-9]\d{7,14}$")


def parse_phone(text: str) -> str:
    """Normalise a phone number to E.164. Turkish national formats are understood."""
    raw = text.strip()
    if not raw:
        raise ParseError("invalid_phone")
    plus = raw.startswith("+")
    digits = re.sub(r"\D", "", raw)
    if plus:
        candidate = "+" + digits
    elif digits.startswith("00"):
        candidate = "+" + digits[2:]
    elif digits.startswith("90") and len(digits) == 12:
        candidate = "+" + digits
    elif digits.startswith("0") and len(digits) == 11:
        candidate = "+90" + digits[1:]
    elif len(digits) == 10 and digits[0] != "0":
        candidate = "+90" + digits
    else:
        raise ParseError("invalid_phone")
    if not _E164_DIGITS.match(candidate):
        raise ParseError("invalid_phone")
    if candidate.startswith("+90") and (len(candidate) != 13 or candidate[3] not in "23458"):
        raise ParseError("invalid_phone")
    return candidate


# --- weekly hours -------------------------------------------------------------------------


def hours_from_editor(
    rows: list[dict[str, Any]], exceptions: list[dict[str, Any]] | None = None
) -> dict[str, Any]:
    """Build a canonical ``weekly_hours`` value from the editor model.

    ``rows`` are ``{"days": ["mon", "tue"], "ranges": [["07:00", "23:00"]]}``; a row with no
    ranges means closed. A day may appear in one row only; days in no row are closed.
    """
    value: dict[str, Any] = {day: [] for day in WEEKDAYS}
    seen: set[str] = set()
    for row in rows:
        days = row.get("days", [])
        for day in days:
            if day not in WEEKDAYS:
                raise ParseError("unknown_day")
            if day in seen:
                raise ParseError("duplicate_day")
            seen.add(day)
            value[day] = [tuple(pair) for pair in row.get("ranges", [])]
    value["exceptions"] = exceptions or []
    return validate_value("weekly_hours", value)
