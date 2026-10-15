"""Rendering of fact values for people (ADR-016): Babel number/date/weekday formatting.

Money is assembled from Babel's number and symbol data instead of a CLDR currency pattern,
so the output is exactly the documented form regardless of CLDR currency-spacing rules:
``6.000 ₺`` (tr), ``€1,200`` and ``TRY 6,000`` (en). Whole amounts have no decimals.
"""

from datetime import date
from decimal import Decimal
from typing import Any

from babel import Locale
from babel.dates import format_date
from babel.numbers import format_decimal, get_currency_symbol

from app.core.i18n import DEFAULT_LOCALE, normalize_locale, t
from app.knowledge.values import WEEKDAYS

_BABEL = {"tr": "tr_TR", "en": "en"}
RANGE_DASH = "–"


def _babel(locale: str) -> str:
    return _BABEL[normalize_locale(locale)]


def format_money_amount(amount: Decimal, currency: str, locale: str) -> str:
    """``6000.00`` TRY -> ``6.000 ₺`` (tr); ``1200`` EUR -> ``€1,200`` (en)."""
    loc = normalize_locale(locale)
    whole = amount == amount.to_integral_value()
    number = format_decimal(
        amount,
        format="#,##0" if whole else "#,##0.00",
        locale=_babel(loc),
        decimal_quantization=False,
    )
    symbol = get_currency_symbol(currency, locale=_babel(loc))
    if loc == "tr":
        return f"{number} {symbol}"
    return f"{symbol}{number}" if len(symbol) == 1 else f"{symbol} {number}"


def _localized(value: dict[str, Any] | None, locale: str, fallback: str) -> str:
    if not value:
        return ""
    for candidate in (normalize_locale(locale), fallback, "tr", "en"):
        text = value.get(candidate)
        if text:
            return str(text)
    return ""


def format_money(value: dict[str, Any], locale: str, fallback_locale: str = DEFAULT_LOCALE) -> str:
    text = format_money_amount(Decimal(str(value["amount"])), value["currency"], locale)
    unit = value.get("unit")
    if unit:
        text += f" / {t(f'knowledge.unit.{unit}', locale)}"
    conditions = _localized(value.get("conditions"), locale, fallback_locale)
    if conditions:
        text += f" ({conditions})"
    return text


def _ranges_text(ranges: list[list[str]] | list[tuple[str, str]]) -> str:
    return " & ".join(f"{opens}{RANGE_DASH}{closes}" for opens, closes in ranges)


def format_weekly_hours(
    value: dict[str, Any], locale: str, fallback_locale: str = DEFAULT_LOCALE
) -> str:
    """Group consecutive days with the same hours: ``Pzt–Cum 07:00–23:00, Cmt …, Paz kapalı``."""
    loc = normalize_locale(locale)
    names = Locale.parse(_babel(loc)).days["format"]["abbreviated"]  # index 0 = Monday
    closed = t("knowledge.hours.closed", loc)
    runs: list[tuple[int, int, list[list[str]]]] = []
    for index, day in enumerate(WEEKDAYS):
        ranges = [list(pair) for pair in value.get(day, [])]
        if runs and runs[-1][2] == ranges and runs[-1][1] == index - 1:
            runs[-1] = (runs[-1][0], index, ranges)
        else:
            runs.append((index, index, ranges))
    parts: list[str] = []
    for first, last, ranges in runs:
        label = names[first] if first == last else f"{names[first]}{RANGE_DASH}{names[last]}"
        parts.append(f"{label} {_ranges_text(ranges) if ranges else closed}")
    text = ", ".join(parts)
    exceptions = []
    for exception in value.get("exceptions", []):
        when = format_date(date.fromisoformat(exception["date"]), "d MMM", locale=_babel(loc))
        what = closed if exception.get("closed", True) else _ranges_text(exception["ranges"])
        note = _localized(exception.get("note"), loc, fallback_locale)
        exceptions.append(f"{when}: {what}" + (f" ({note})" if note else ""))
    if exceptions:
        text += " · " + ", ".join(exceptions)
    return text


def format_address(value: dict[str, Any]) -> str:
    place = f"{value['district']} / {value['city']}" if value.get("district") else value["city"]
    return ", ".join([*value["lines"], place])


def format_value(
    value_type: str,
    value: dict[str, Any],
    locale: str,
    fallback_locale: str = DEFAULT_LOCALE,
) -> str:
    """Human-readable form of a canonical value in ``locale``."""
    loc = normalize_locale(locale)
    match value_type:
        case "money":
            return format_money(value, loc, fallback_locale)
        case "weekly_hours":
            return format_weekly_hours(value, loc, fallback_locale)
        case "text":
            return str(value["text"])
        case "localized_text":
            return _localized(value, loc, fallback_locale)
        case "phone":
            return str(value.get("display") or value["e164"])
        case "email":
            return str(value["email"])
        case "address":
            return format_address(value)
        case "url":
            return str(value["url"])
        case "boolean":
            return t(f"knowledge.bool.{str(bool(value['value'])).lower()}", loc)
        case "enum":
            key = f"knowledge.enum.{value['value']}"
            label = t(key, loc)
            return str(value["value"]) if label == key else label
        case "string_list":
            return ", ".join(value["items"])
    raise ValueError(f"unknown value_type {value_type}")
