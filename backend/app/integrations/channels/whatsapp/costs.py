"""Per-message cost metadata for the delivery ledger (ADR-027, platform-capabilities.md 2.1).

WhatsApp charges per delivered message. The ledger records what we **know when sending**: whether
the message was a template or a session message, its category, and a pricing note. It does **not**
record an amount: no Turkiye rate (currency or figure) was verified from Meta's rate card, the
pricing page names Turkiye as a standalone market without a figure, and an invented number would be
worse than none. ``price_verified`` is therefore always ``False`` here. When Meta's status webhook
later reports a ``pricing`` object it is stored under ``billing`` as Meta sent it (flags and
category, not an amount).

Facts used (Meta pricing page, accessed 2026-11-18): service messages have a free tier of 1,000
delivered messages per business number per month and are charged after it; utility templates sent
inside an open window are charged since 2026-10-01; template and session sends are separate
meters. This is why the channel prefers a session message whenever the window is open.
"""

from __future__ import annotations

from typing import Any

PRICING_NOTE_TEMPLATE = "utility_template_charged_per_delivered_message_tr_rate_unverified"
PRICING_NOTE_SESSION = (
    "service_message_free_tier_1000_per_number_per_month_then_charged_tr_rate_unverified"
)


def cost_metadata(
    mode: str, template_name: str | None, language: str | None, template_category: str | None
) -> dict[str, Any]:
    is_template = mode == "template"
    return {
        "channel": "whatsapp",
        "send_mode": mode,
        "is_template": is_template,
        "category": template_category if is_template else "service",
        "template_name": template_name if is_template else None,
        "template_language": language if is_template else None,
        "pricing_note": PRICING_NOTE_TEMPLATE if is_template else PRICING_NOTE_SESSION,
        "price_verified": False,
        "price_amount": None,
        "currency": None,
    }


def billing_from_pricing(pricing: dict[str, Any]) -> dict[str, Any]:
    """The safe subset of a status webhook's ``pricing`` object (flags and labels only)."""
    safe: dict[str, Any] = {}
    billable = pricing.get("billable")
    if isinstance(billable, bool):
        safe["billable"] = billable
    for key in ("pricing_model", "category", "type"):
        value = pricing.get(key)
        if isinstance(value, str) and len(value) <= 64:
            safe[key] = value
    return safe
