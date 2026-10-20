"""Action classes and the facts each reply intent needs (ADR-014, agent-runtime.md §4)."""

from collections.abc import Collection
from typing import NamedTuple

REPLY_ACTION_CLASSES = (
    "reply.hours",
    "reply.location_contact",
    "reply.pricing",
    "reply.services",
    "reply.booking",
    "reply.promotions",
    "reply.general_faq",
)
ACTION_CLASSES = (*REPLY_ACTION_CLASSES, "content.publish")
MODES = ("auto", "approval", "off")
DEFAULT_MODE = "approval"

_INTENT_CLASS = {
    "pricing": "reply.pricing",
    "hours": "reply.hours",
    "location_contact": "reply.location_contact",
    "services": "reply.services",
    "booking": "reply.booking",
    "promotions": "reply.promotions",
    "faq": "reply.general_faq",
    "greeting": "reply.general_faq",
}
# Intents that always go to a person: there is no automation level for them.
ALWAYS_HUMAN_INTENTS = frozenset({"complaint", "refund_request", "discount_request", "sensitive"})


def intent_action_class(intent: str | None) -> str | None:
    """The automation class of an intent, or ``None`` for intents that are always human."""
    return _INTENT_CLASS.get(intent) if intent else None


def _any_prefix(keys: Collection[str], *prefixes: str) -> bool:
    return any(key.startswith(prefixes) for key in keys)


# The fact keys that belong to an intent (see ``required_facts_usable``).
_FAMILIES = {
    "pricing": ("pricing.", "policy.price_answer_text"),
    "hours": ("hours.",),
    "location_contact": ("location.", "contact."),
    "services": ("service.",),
    "booking": ("booking.",),
    "promotions": ("promotion.",),
    "faq": ("faq.",),
}


def required_facts_usable(
    intent: str | None,
    usable_keys: Collection[str],
    *,
    price_disclosure: str,
    approved_answer_used: bool,
    model_can_answer: bool = True,
    unusable_keys: Collection[str] = (),
) -> bool:
    """Rule R8: is a fact the intent needs usable (verified, in window, uncontested)?

    An approved answer carries its own content (rendered and validated like any reply), so it
    satisfies any intent. Intents without requirements (greeting, the always-human ones) pass.
    When the model could not answer and a fact of the intent's kind exists but is *not usable*,
    that is the reason (the information is there, just not verified), not "no such fact".
    """
    if approved_answer_used or intent is None:
        return True
    if not _present(intent, usable_keys, price_disclosure):
        return False
    family = _FAMILIES.get(intent)
    return not (family and not model_can_answer and _any_prefix(unusable_keys, *family))


def _present(intent: str, usable_keys: Collection[str], price_disclosure: str) -> bool:
    if intent == "pricing":
        if price_disclosure == "do_not_share":
            return "policy.price_answer_text" in usable_keys
        return _any_prefix(usable_keys, "pricing.")
    if intent == "hours":
        return "hours.weekly" in usable_keys
    if intent == "location_contact":
        return _any_prefix(usable_keys, "location.", "contact.")
    if intent == "services":
        return _any_prefix(usable_keys, "service.")
    if intent == "booking":
        return "booking.instructions" in usable_keys
    if intent == "promotions":
        return _any_prefix(usable_keys, "promotion.")
    if intent == "faq":
        return _any_prefix(usable_keys, "faq.")
    return True


_FACT_PREFIX_CLASS = (
    ("pricing.", "reply.pricing"),
    ("hours.", "reply.hours"),
    ("location.", "reply.location_contact"),
    ("contact.", "reply.location_contact"),
    ("service.", "reply.services"),
    ("booking.", "reply.booking"),
    ("promotion.", "reply.promotions"),
    ("faq.", "reply.general_faq"),
)
_STRICTNESS = {"auto": 0, "approval": 1, "off": 2}


def fact_action_class(key: str) -> str | None:
    """The action class a fact belongs to, by what it says (``pricing.*`` is pricing)."""
    for prefix, action_class in _FACT_PREFIX_CLASS:
        if key.startswith(prefix):
            return action_class
    return None


class EffectiveMode(NamedTuple):
    mode: str
    # The class whose mode won: the intent's own class on a tie, else the strictest fact class.
    action_class: str | None


def effective_mode(
    modes: dict[str, str], intent: str | None, used_fact_keys: Collection[str]
) -> EffectiveMode:
    """The strictest mode among the intent's class and the classes of the facts the reply
    actually quotes, with the class that decided it. The intent is the model's label; the facts
    are what the reply says, so a price question labelled "faq" still needs the pricing policy
    (INV-04). On a tie the intent's own class wins, so the class differs from the intent's only
    when a quoted fact made the reply stricter."""
    intent_class = intent_action_class(intent)
    fact_classes = sorted({c for k in used_fact_keys if (c := fact_action_class(k)) is not None})
    candidates = [c for c in dict.fromkeys([intent_class, *fact_classes]) if c is not None]
    if not candidates:
        return EffectiveMode(DEFAULT_MODE, None)
    winner = candidates[0]
    for candidate in candidates[1:]:
        if (
            _STRICTNESS[modes.get(candidate, DEFAULT_MODE)]
            > _STRICTNESS[modes.get(winner, DEFAULT_MODE)]
        ):
            winner = candidate
    return EffectiveMode(modes.get(winner, DEFAULT_MODE), winner)
