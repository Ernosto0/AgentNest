"""The WhatsApp template registry, the 24-hour window decision and the cost metadata (pure)."""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from app.integrations.channels.whatsapp import templates, window
from app.integrations.channels.whatsapp.costs import billing_from_pricing, cost_metadata
from app.notifications.catalog import CATALOG, WHATSAPP_TYPES

NOW = datetime(2026, 11, 18, 12, 0, tzinfo=UTC)
PLACEHOLDER = re.compile(r"\{\{(\d+)\}\}")
DOC = Path(__file__).resolve().parents[5] / "docs" / "research" / "platform-capabilities.md"


# --- the registry ------------------------------------------------------------------------------


def test_every_whatsapp_type_has_exactly_one_template_and_nothing_else_does() -> None:
    assert set(templates.BY_TYPE) == set(WHATSAPP_TYPES)
    assert len(templates.ALL_TEMPLATES) == len(WHATSAPP_TYPES)
    assert set(CATALOG) >= WHATSAPP_TYPES
    assert len({t.name for t in templates.ALL_TEMPLATES}) == len(templates.ALL_TEMPLATES)


@pytest.mark.parametrize("template", templates.ALL_TEMPLATES, ids=lambda t: t.name)
def test_templates_follow_meta_rules(template: templates.WhatsAppTemplate) -> None:
    assert template.category == "utility"  # never marketing or authentication
    assert re.fullmatch(r"[a-z0-9_]{1,512}", template.name)
    assert re.search(r"_v\d+$", template.name)  # an approved template cannot be edited in place
    assert set(template.bodies) == {"tr", "en"}
    for locale, body in template.bodies.items():
        assert 0 < len(body) <= 1024, locale
        numbers = [int(n) for n in PLACEHOLDER.findall(body)]
        assert numbers == list(range(1, len(template.variables) + 1)), locale
        assert not body.startswith("{{") and not body.rstrip().endswith("}}"), locale
        assert "{{" not in PLACEHOLDER.sub("", body)  # no stray or malformed braces


@pytest.mark.parametrize("template", templates.ALL_TEMPLATES, ids=lambda t: t.name)
def test_variables_are_numbers_or_a_date_never_text(template: templates.WhatsAppTemplate) -> None:
    allowed = {"local_date", "inbound_messages", "replies_sent", "pending_approvals"}
    assert set(template.variables) <= allowed


def test_the_documented_template_names_match_the_registry() -> None:
    text = DOC.read_text(encoding="utf-8")
    for template in templates.ALL_TEMPLATES:
        assert f"`{template.name}`" in text, template.name


def test_rendering_fills_positional_variables_in_both_languages() -> None:
    template = templates.BY_TYPE["report.daily_ready"]
    params = {
        "local_date": "2026-11-18",
        "inbound_messages": 12,
        "replies_sent": 5,
        "pending_approvals": 0,
    }
    tr = templates.variable_values(template, params, "tr")
    en = templates.variable_values(template, params, "en-US")
    assert tr == ["18.11.2026", "12", "5", "0"] and en == ["2026-11-18", "12", "5", "0"]
    assert tr is not None and en is not None
    assert "18.11.2026 tarihi için: 12 yeni mesaj, 5 gönderilen yanıt, 0 bekleyen onay" in (
        template.render("tr", tr)
    )
    assert "daily summary for 2026-11-18: 12 new messages" in template.render("en", en)
    with pytest.raises(ValueError):
        template.render("tr", ["only one"])


@pytest.mark.parametrize(
    "params",
    [
        {},
        {
            "local_date": "not a date",
            "inbound_messages": 1,
            "replies_sent": 1,
            "pending_approvals": 1,
        },
        {
            "local_date": "2026-11-18",
            "inbound_messages": "12",
            "replies_sent": 1,
            "pending_approvals": 1,
        },
        {
            "local_date": "2026-11-18",
            "inbound_messages": -1,
            "replies_sent": 1,
            "pending_approvals": 1,
        },
        {
            "local_date": "2026-11-18",
            "inbound_messages": True,
            "replies_sent": 1,
            "pending_approvals": 1,
        },
        {"local_date": "2026-11-18", "inbound_messages": 1, "replies_sent": 1},
    ],
)
def test_a_missing_or_non_numeric_variable_refuses_to_render(params: dict) -> None:
    assert templates.variable_values(templates.BY_TYPE["report.daily_ready"], params, "tr") is None


def test_a_template_without_variables_never_reads_params() -> None:
    template = templates.BY_TYPE["approval.requested"]
    assert templates.variable_values(template, {"customer_text": "secret"}, "tr") == []
    assert "secret" not in template.render("tr", [])


# --- the window --------------------------------------------------------------------------------

LIMIT = window.WINDOW - window.SAFETY_MARGIN


@pytest.mark.parametrize(
    ("age", "mode"),
    [
        (timedelta(0), "session"),
        (timedelta(hours=3), "session"),
        (LIMIT - timedelta(seconds=1), "session"),  # last second of the usable window
        (LIMIT, "template"),  # the boundary itself is outside
        (LIMIT + timedelta(seconds=1), "template"),
        (window.WINDOW, "template"),
        (timedelta(days=3), "template"),
        (timedelta(seconds=-1), "template"),  # a future timestamp proves nothing
    ],
)
def test_the_send_mode_at_each_boundary(age: timedelta, mode: str) -> None:
    assert window.choose_send_mode(NOW - age, NOW) == mode


def test_no_inbound_message_ever_means_template() -> None:
    assert window.choose_send_mode(None, NOW) == "template"


def test_the_window_is_24_hours_with_a_five_minute_margin() -> None:
    assert timedelta(hours=24) == window.WINDOW
    assert timedelta(minutes=5) == window.SAFETY_MARGIN


# --- cost metadata -----------------------------------------------------------------------------


def test_cost_metadata_never_invents_a_price() -> None:
    template = cost_metadata("template", "agentnest_x_v1", "tr", "utility")
    session = cost_metadata("session", "agentnest_x_v1", "tr", "utility")
    assert template["is_template"] is True and template["category"] == "utility"
    assert template["template_name"] == "agentnest_x_v1"
    assert session["is_template"] is False and session["category"] == "service"
    assert session["template_name"] is None
    for meta in (template, session):
        assert meta["price_verified"] is False
        assert meta["price_amount"] is None and meta["currency"] is None
        assert meta["pricing_note"].endswith("tr_rate_unverified")
    assert template["pricing_note"] != session["pricing_note"]


def test_billing_keeps_only_flags_and_short_labels() -> None:
    assert billing_from_pricing(
        {
            "billable": True,
            "pricing_model": "PMP",
            "category": "utility",
            "type": "regular",
            "amount": 0.5,
            "note": "x",
        }
    ) == {"billable": True, "pricing_model": "PMP", "category": "utility", "type": "regular"}
    assert billing_from_pricing({"billable": "yes", "category": "x" * 100}) == {}
