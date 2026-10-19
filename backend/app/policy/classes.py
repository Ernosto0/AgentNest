"""Action classes and the facts each reply intent needs (ADR-014, agent-runtime.md §4)."""

from collections.abc import Collection

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


def required_facts_usable(
    intent: str | None,
    usable_keys: Collection[str],
    *,
    price_disclosure: str,
    approved_answer_used: bool,
) -> bool:
    """Rule R8: is a fact the intent needs usable (verified, in window, uncontested)?

    An approved answer carries its own content (rendered and validated like any reply), so it
    satisfies any intent. Intents without requirements (greeting, the always-human ones) pass.
    """
    if approved_answer_used or intent is None:
        return True
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


def effective_mode(
    modes: dict[str, str], intent: str | None, used_fact_keys: Collection[str]
) -> str:
    """The strictest mode among the intent's class and the classes of the facts the reply
    actually quotes. The intent is the model's label; the facts are what the reply says, so a
    price question labelled "faq" still needs the pricing policy (INV-04)."""
    classes = {intent_action_class(intent), *(fact_action_class(k) for k in used_fact_keys)}
    classes.discard(None)
    if not classes:
        return DEFAULT_MODE
    return max((modes.get(c, DEFAULT_MODE) for c in classes if c), key=_STRICTNESS.__getitem__)
