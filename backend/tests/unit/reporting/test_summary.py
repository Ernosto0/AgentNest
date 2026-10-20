"""The templated summary (plan H4) and the catalog texts it depends on."""

from typing import Any

import pytest

from app.core.i18n import catalog_keys, t
from app.reporting.definitions import DEFINITIONS, INBOX_KEYS, KEYS, SECTIONS
from app.reporting.summary import build_summary


def metrics(**values: Any) -> dict[str, dict[str, Any]]:
    """Every key present, zero unless given."""
    return {key: {"value": values.get(key, 0)} for key in KEYS}


@pytest.mark.parametrize("locale", ["tr", "en"])
def test_every_metric_and_section_has_text_in_both_languages(locale: str) -> None:
    keys = catalog_keys(locale)
    for definition in DEFINITIONS:
        assert f"report.summary.{definition.section}.{definition.key}" in keys, definition.key
    for section in SECTIONS:
        assert f"report.section.{section}" in keys
    assert "report.summary.empty" in keys


def test_the_two_catalogs_have_the_same_report_keys() -> None:
    def report_keys(locale: str) -> set[str]:
        return {
            k
            for k in catalog_keys(locale)
            if k.startswith(("report.", "operation.", "command.reply", "command.activity"))
        }

    assert report_keys("tr") == report_keys("en")


def test_zero_and_null_values_are_left_out_and_empty_sections_vanish() -> None:
    values = metrics(inbound_messages=3, content_published=1)
    values["median_first_response_minutes"] = {"value": None}
    summary = build_summary(values, KEYS, "en")
    assert summary.empty is False
    assert [s.section for s in summary.sections] == ["messages", "content"]
    assert summary.sections[0].lines == ["Messages received: 3"]
    assert summary.sections[1].lines == ["Posts published: 1"]
    assert "Approvals" not in summary.text and "Problems" not in summary.text


def test_everything_zero_gives_the_empty_text() -> None:
    summary = build_summary(metrics(), KEYS, "en")
    assert summary.empty and summary.sections == []
    assert summary.text == t("report.summary.empty", "en")
    assert build_summary(metrics(), KEYS, "tr").text == "Bu gün için kayıtlı bir hareket yok."


def test_only_visible_keys_count() -> None:
    values = metrics(inbound_messages=2, pending_approvals_now=5, integration_errors=1)
    staff = build_summary(values, INBOX_KEYS, "en")
    assert [s.section for s in staff.sections] == ["messages"]
    nothing = build_summary(values, [], "en")
    assert nothing.empty


def test_a_missing_key_in_an_older_stored_report_is_skipped() -> None:
    summary = build_summary({"inbound_messages": {"value": 4}}, KEYS, "tr")
    assert summary.sections[0].lines == ["Gelen mesajlar: 4"]


def test_numbers_are_formatted_for_the_language() -> None:
    values = metrics(inbound_messages=1234, median_first_response_minutes=6.5)
    tr = build_summary(values, KEYS, "tr").sections[0].lines
    en = build_summary(values, KEYS, "en").sections[0].lines
    assert "Gelen mesajlar: 1.234" in tr and "Medyan ilk yanıt süresi: 6,5 dk" in tr
    assert "Messages received: 1,234" in en and "Median first response time: 6.5 min" in en


def test_an_unsupported_locale_falls_back_to_turkish() -> None:
    summary = build_summary(metrics(inbound_messages=1), KEYS, "de")
    assert summary.sections[0].title == "Mesajlar"


def test_the_text_lists_each_section_under_its_title() -> None:
    summary = build_summary(metrics(inbound_messages=1, fact_changes=2), KEYS, "en")
    assert summary.text == (
        "Messages\nMessages received: 1\n\nInformation changes\nInformation changes: 2"
    )
