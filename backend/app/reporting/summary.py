"""The templated, localised summary of a report (plan H4).

No language model (INV-08): one line per non-zero metric, from the catalog key
``report.summary.<section>.<metric>``, grouped under ``report.section.<section>``. A section whose
values are all zero (or null) is left out; when every section is, the text is
``report.summary.empty``. The lines are label-and-number sentences, so they read correctly for 1
and for many in both languages (the catalogs have no plural forms).
"""

from collections.abc import Collection, Mapping
from dataclasses import dataclass
from typing import Any

from babel.numbers import format_decimal

from app.core.i18n import normalize_locale, t
from app.reporting.definitions import DEFINITIONS, SECTIONS

_BABEL_LOCALES = {"tr": "tr_TR", "en": "en"}


@dataclass(frozen=True)
class SummarySection:
    section: str
    title: str
    lines: list[str]


@dataclass(frozen=True)
class Summary:
    empty: bool
    text: str
    sections: list[SummarySection]


def _number(value: int | float, locale: str) -> str:
    return format_decimal(value, locale=_BABEL_LOCALES[locale], format="#,##0.##")


def _number_or_none(value: Any) -> int | float | None:
    """The value when it is a non-zero number (zero and null are left out of the summary)."""
    if isinstance(value, int | float) and not isinstance(value, bool) and value != 0:
        return value
    return None


def build_summary(
    metrics: Mapping[str, Mapping[str, Any]], visible: Collection[str], locale: str | None
) -> Summary:
    """The summary of the stored ``metrics`` limited to the ``visible`` keys."""
    language = normalize_locale(locale)
    lines: dict[str, list[str]] = {section: [] for section in SECTIONS}
    for definition in DEFINITIONS:
        entry = metrics.get(definition.key)
        if definition.key not in visible or entry is None:
            continue
        value = _number_or_none(entry.get("value"))
        if value is None:
            continue
        lines[definition.section].append(
            t(
                f"report.summary.{definition.section}.{definition.key}",
                language,
                count=_number(value, language),
                value=_number(value, language),
            )
        )
    sections = [
        SummarySection(section, t(f"report.section.{section}", language), lines[section])
        for section in SECTIONS
        if lines[section]
    ]
    if not sections:
        return Summary(True, t("report.summary.empty", language), [])
    text = "\n\n".join(f"{s.title}\n" + "\n".join(s.lines) for s in sections)
    return Summary(False, text, sections)
