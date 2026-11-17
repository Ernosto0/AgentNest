"""Deterministic price-card resolution: only the catalog supplies values."""

from collections.abc import Sequence

from app.commands.resolver import (
    Confirm,
    FactSnapshot,
    NeedsClarification,
    Outcome,
    Rejected,
    _fact_options,
    similar_facts,
)
from app.commands.results import CommandResult
from app.knowledge.formatting import format_value


def resolve_price_card(
    key: str,
    format: str | None,
    facts: Sequence[FactSnapshot],
    user_locale: str,
    workspace_locale: str,
) -> Outcome:
    fact = next((f for f in facts if f.key == key), None)
    if fact is None:
        money = [f for f in facts if f.value_type == "money"]
        candidates = (
            similar_facts(key, money, locale=user_locale, limit=len(money)) if key else money
        )
        candidates.sort(key=lambda f: f.status != "verified")
        candidates = candidates[:3]
        if not candidates:
            return Rejected(
                "NOT_FOUND", CommandResult("command.price_card_no_price", error_code="NOT_FOUND")
            )
        return NeedsClarification(
            "fact",
            "command.clarify.which_fact",
            {},
            _fact_options(candidates, locale=user_locale, workspace_locale=workspace_locale),
            {"intent": "content.make_price_card", "format": format},
        )
    label = fact.display_label(user_locale)
    if fact.value_type != "money":
        return Rejected(
            "TEMPLATE_FACT_TYPE_MISMATCH",
            CommandResult(
                "command.price_card_not_a_price",
                {"label": label},
                error_code="TEMPLATE_FACT_TYPE_MISMATCH",
            ),
        )
    if fact.status != "verified":
        return Rejected(
            "TEMPLATE_FACT_NOT_USABLE",
            CommandResult(
                "command.price_card_fact_unusable",
                {"label": label},
                error_code="TEMPLATE_FACT_NOT_USABLE",
            ),
        )
    format = format or "story"
    language = "en" if workspace_locale == "en" else "tr"
    return Confirm(
        "content.make_price_card",
        "command.make_price_card",
        {
            "fact_id": str(fact.id),
            "fact_key": fact.key,
            "fact_version": fact.version,
            "format": format,
            "language": language,
        },
        {
            "label": label,
            "key": fact.key,
            "price_formatted": format_value("money", fact.value, language),
            "format": format,
            "content_type": "story_image" if format == "story" else "feed_image",
            "template": "price_card",
            "is_simulated": False,
        },
    )
