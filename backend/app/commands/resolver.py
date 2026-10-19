"""Deterministic resolution of an interpretation (agent-runtime.md §3, workflows.md §B).

The model's output is a *proposal*. Everything here is plain code: the referenced fact must
exist in the workspace catalog (else the closest keys are offered), the value is **re-parsed**
from the text the owner typed with the locale-aware parser and compared with the model's reading
(a disagreement becomes a question, never a guess), and the result is one of a few outcomes
that the service turns into state. No database, no clock, no LLM: all inputs are passed in.
"""

import difflib
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any, Literal

from app.ai.schemas import (
    Clarify,
    CommandInterpretation,
    NormalizedBoolean,
    NormalizedMoney,
    NormalizedValue,
    QueryActivitySummary,
    QueryFact,
    QueryPendingApprovals,
    Unsupported,
    UpdateBrandVoice,
    UpdateFact,
)
from app.commands.results import CommandResult
from app.core.errors import AppError
from app.knowledge.claims import fold
from app.knowledge.formatting import format_money_amount, format_value
from app.knowledge.parsing import (
    Money,
    ParseAmbiguity,
    ParseError,
    normalize_for_match,
    parse_money,
    parse_phone,
)
from app.knowledge.values import validate_value, values_equal

BRAND_VOICE_KEY = "brand.voice_guidelines"
MAX_SIMILAR = 3
MIN_SIMILARITY = 0.3
MAX_BRAND_VOICE_CHARS = 2000
MAX_REASON_CHARS = 200
_TRUE_WORDS = {"evet", "var", "acik", "yes", "true", "on", "open"}
_FALSE_WORDS = {"hayir", "yok", "kapali", "no", "false", "off", "closed"}


@dataclass(frozen=True)
class FactSnapshot:
    """A live fact as the resolver needs it."""

    id: uuid.UUID
    key: str
    label: dict[str, str]
    category: str
    value_type: str
    value: dict[str, Any]
    status: str
    version: int
    allowed_values: tuple[str, ...] = ()

    def display_label(self, locale: str) -> str:
        return self.label.get(locale) or self.label.get("tr") or self.label.get("en") or self.key


# --- outcomes -------------------------------------------------------------------------------


@dataclass(frozen=True)
class ClarifyOption:
    id: str
    label: str
    value: dict[str, Any] | None = None  # kept server-side, never sent to the client


@dataclass(frozen=True)
class NeedsClarification:
    kind: Literal["fact", "value"]
    question_key: str
    params: dict[str, Any]
    options: tuple[ClarifyOption, ...]
    # What to resume with once the owner picks an option.
    pending: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class UnsupportedOutcome:
    reason: str


@dataclass(frozen=True)
class Rejected:
    """A permanent failure with a message for the owner."""

    error_code: str
    result: CommandResult


@dataclass(frozen=True)
class Completed:
    """Nothing to do (e.g. the value is already what the owner asked for)."""

    result: CommandResult


@dataclass(frozen=True)
class Execute:
    """A read-only command: run its executor now."""

    command_type: str
    resolution: dict[str, Any]


@dataclass(frozen=True)
class Confirm:
    """A state-changing command: ask the owner to confirm exactly ``payload``."""

    command_type: str
    action: str  # approval action
    fact_id: uuid.UUID
    payload: dict[str, Any]  # hashed into the approval
    summary: dict[str, Any]  # shown on the confirmation card


Outcome = NeedsClarification | UnsupportedOutcome | Rejected | Completed | Execute | Confirm


# --- helpers --------------------------------------------------------------------------------


def _by_key(facts: Sequence[FactSnapshot], key: str) -> FactSnapshot | None:
    return next((f for f in facts if f.key == key), None)


def similar_facts(
    key: str, facts: Sequence[FactSnapshot], *, locale: str, limit: int = MAX_SIMILAR
) -> list[FactSnapshot]:
    """The facts whose key or label look most like ``key`` (an unknown key from the model)."""
    wanted = normalize_for_match(key.replace(".", " ").replace("_", " "))
    scored: list[tuple[float, FactSnapshot]] = []
    for fact in facts:
        candidates = (
            normalize_for_match(fact.key.replace(".", " ").replace("_", " ")),
            normalize_for_match(fact.display_label(locale)),
        )
        score = max(difflib.SequenceMatcher(None, wanted, c).ratio() for c in candidates)
        if score >= MIN_SIMILARITY:
            scored.append((score, fact))
    scored.sort(key=lambda item: (-item[0], item[1].key))
    return [fact for _, fact in scored[:limit]]


def _fact_options(
    facts: Sequence[FactSnapshot], *, locale: str, workspace_locale: str
) -> tuple[ClarifyOption, ...]:
    return tuple(
        ClarifyOption(
            id=fact.key,
            label=f"{fact.display_label(locale)} · "
            f"{format_value(fact.value_type, fact.value, locale, workspace_locale)}",
        )
        for fact in facts
    )


def _fact_question(
    candidates: Sequence[FactSnapshot],
    *,
    intent: str,
    raw_value_text: str | None,
    locale: str,
    workspace_locale: str,
) -> Outcome:
    if not candidates:
        return UnsupportedOutcome("other")
    return NeedsClarification(
        kind="fact",
        question_key="command.clarify.which_fact",
        params={"raw": raw_value_text},
        options=_fact_options(candidates, locale=locale, workspace_locale=workspace_locale),
        pending={"intent": intent, "raw_value_text": raw_value_text},
    )


def _unreadable(fact: FactSnapshot, raw: str, locale: str) -> Rejected:
    return Rejected(
        "VALIDATION_FAILED",
        CommandResult(
            "command.value_unreadable",
            {"raw": raw, "label": fact.display_label(locale)},
            error_code="VALIDATION_FAILED",
        ),
    )


def _model_money(value: NormalizedValue | None) -> tuple[Decimal, str] | None:
    if not isinstance(value, NormalizedMoney):
        return None
    try:
        return Decimal(value.amount), value.currency.upper()
    except InvalidOperation:
        return None


def _money_option(index: int, amount: Decimal, currency: str, locale: str) -> ClarifyOption:
    return ClarifyOption(
        id=str(index),
        label=format_money_amount(amount, currency, locale),
        value={"amount": f"{amount:.2f}", "currency": currency},
    )


def _typed_value(
    fact: FactSnapshot, raw: str, model_value: NormalizedValue | None, workspace_locale: str
) -> dict[str, Any] | None:
    """The new canonical value for the non-money types the commands support, or ``None`` for
    types that are better edited in the app (hours, address, lists). May raise ``ParseError``
    or ``AppError(VALIDATION_FAILED)``."""
    text = raw.strip()
    language = "en" if workspace_locale == "en" else "tr"
    match fact.value_type:
        case "phone":
            return validate_value("phone", {"e164": parse_phone(text)})
        case "text":
            return validate_value("text", {"text": text})
        case "localized_text":
            return validate_value("localized_text", {**fact.value, language: text})
        case "email":
            return validate_value("email", {"email": text.lower()})
        case "url":
            return validate_value("url", {"url": text})
        case "boolean":
            if isinstance(model_value, NormalizedBoolean):
                return validate_value("boolean", {"value": model_value.value})
            word = fold(text)
            if word in _TRUE_WORDS or word in _FALSE_WORDS:
                return validate_value("boolean", {"value": word in _TRUE_WORDS})
            raise ParseError("invalid_boolean")
        case "enum":
            allowed = fact.allowed_values or None
            return validate_value(
                "enum", {"value": fold(text).replace(" ", "_")}, allowed_values=allowed
            )
    return None


# --- the update command ---------------------------------------------------------------------


def resolve_update_fact(
    fact_key: str,
    raw_value_text: str,
    model_value: NormalizedValue | None,
    facts: Sequence[FactSnapshot],
    *,
    user_locale: str,
    workspace_locale: str,
    currency: str,
    reason: str | None = None,
    chosen_money: dict[str, Any] | None = None,
) -> Outcome:
    """Resolve "set ``fact_key`` to ``raw_value_text``" into a confirmation (or a question).

    ``chosen_money`` is the owner's pick after a value question: it replaces re-parsing, so a
    clarified value is never asked about twice.
    """
    fact = _by_key(facts, fact_key)
    if fact is None:
        return _fact_question(
            similar_facts(fact_key, facts, locale=user_locale),
            intent="knowledge.update_fact",
            raw_value_text=raw_value_text,
            locale=user_locale,
            workspace_locale=workspace_locale,
        )
    label = fact.display_label(user_locale)
    raw = raw_value_text.strip()
    if not raw and chosen_money is None:
        return _unreadable(fact, raw_value_text, user_locale)

    new_value: dict[str, Any] | None
    try:
        if fact.value_type == "money":
            if chosen_money is not None:
                amount, cur = Decimal(chosen_money["amount"]), chosen_money["currency"]
            else:
                parsed = parse_money(raw, user_locale, currency)
                if isinstance(parsed, ParseAmbiguity):  # e.g. "7.000" in an English workspace
                    return NeedsClarification(
                        kind="value",
                        question_key="command.clarify.which_value",
                        params={"raw": raw, "label": label},
                        options=tuple(
                            _money_option(i, m.amount, m.currency, user_locale)
                            for i, m in enumerate(parsed.alternatives)
                        ),
                        pending={"fact_key": fact_key, "raw_value_text": raw, "reason": reason},
                    )
                money: Money = parsed
                amount, cur = money.amount, money.currency
                reading = _model_money(model_value)
                if reading is not None and reading != (amount, cur):
                    # The code and the model read the same text differently: ask, never guess.
                    options = [_money_option(0, amount, cur, user_locale)]
                    options.append(_money_option(1, reading[0], reading[1], user_locale))
                    return NeedsClarification(
                        kind="value",
                        question_key="command.clarify.which_value",
                        params={"raw": raw, "label": label},
                        options=tuple(options),
                        pending={"fact_key": fact_key, "raw_value_text": raw, "reason": reason},
                    )
            new_value = validate_value(
                "money",
                {**fact.value, "amount": f"{amount:.2f}", "currency": cur},
                default_currency=currency,
            )
        else:
            new_value = _typed_value(fact, raw, model_value, workspace_locale)
    except (ParseError, AppError):
        return _unreadable(fact, raw_value_text, user_locale)
    if new_value is None:
        return UnsupportedOutcome("other")  # hours, address, lists: edit them in the app

    display_old = format_value(fact.value_type, fact.value, user_locale, workspace_locale)
    display_new = format_value(fact.value_type, new_value, user_locale, workspace_locale)
    if fact.status == "verified" and values_equal(fact.value_type, fact.value, new_value):
        return Completed(
            CommandResult(
                "command.fact_unchanged",
                {"label": label, "display": display_old},
                [{"target": "knowledge", "category": fact.category, "key": fact.key}],
            )
        )
    return Confirm(
        command_type="knowledge.update_fact",
        action="command.update_fact",
        fact_id=fact.id,
        payload={
            "fact_id": str(fact.id),
            "from_version": fact.version,
            "new_value": new_value,
            "reason": (reason or "").strip()[:MAX_REASON_CHARS] or None,
        },
        summary={
            "label": label,
            "key": fact.key,
            "category": fact.category,
            "old_formatted": display_old,
            "new_formatted": display_new,
        },
    )


def resolve_brand_voice(
    instruction: str,
    proposed_guidelines: str,
    facts: Sequence[FactSnapshot],
    *,
    user_locale: str,
    workspace_locale: str,
) -> Outcome:
    fact = _by_key(facts, BRAND_VOICE_KEY)
    if fact is None:
        return Rejected(
            "NOT_FOUND", CommandResult("command.brand_voice_missing", error_code="NOT_FOUND")
        )
    text = proposed_guidelines.strip()
    if not text or len(text) > MAX_BRAND_VOICE_CHARS:
        return _unreadable(fact, instruction, user_locale)
    language = "en" if workspace_locale == "en" else "tr"
    try:
        new_value = validate_value("localized_text", {**fact.value, language: text})
    except AppError:
        return _unreadable(fact, instruction, user_locale)
    label = fact.display_label(user_locale)
    old = format_value(fact.value_type, fact.value, user_locale, workspace_locale)
    new = format_value(fact.value_type, new_value, user_locale, workspace_locale)
    if values_equal("localized_text", fact.value, new_value) and fact.status == "verified":
        return Completed(
            CommandResult(
                "command.fact_unchanged",
                {"label": label, "display": old},
                [{"target": "knowledge", "category": fact.category, "key": fact.key}],
            )
        )
    return Confirm(
        command_type="knowledge.update_brand_voice",
        action="command.update_brand_voice",
        fact_id=fact.id,
        payload={
            "fact_id": str(fact.id),
            "from_version": fact.version,
            "new_value": new_value,
            "reason": instruction.strip()[:MAX_REASON_CHARS] or None,
        },
        summary={
            "label": label,
            "key": fact.key,
            "category": fact.category,
            "old_formatted": old,
            "new_formatted": new,
        },
    )


# --- entry points ---------------------------------------------------------------------------


def resolve(
    interpretation: CommandInterpretation,
    facts: Sequence[FactSnapshot],
    *,
    user_locale: str,
    workspace_locale: str,
    currency: str,
) -> Outcome:
    """Turn the model's proposal into an outcome. Anything not in the registry is
    ``unsupported``; there is no branch here that can approve, publish or send."""
    match interpretation:
        case Unsupported():
            return UnsupportedOutcome(interpretation.reason)
        case QueryPendingApprovals():
            return Execute("query.pending_approvals", {})
        case QueryActivitySummary():
            return Execute("query.activity_summary", {"period": interpretation.period})
        case QueryFact():
            fact = _by_key(facts, interpretation.fact_key)
            if fact is None:
                return _fact_question(
                    similar_facts(interpretation.fact_key, facts, locale=user_locale),
                    intent="query.fact",
                    raw_value_text=None,
                    locale=user_locale,
                    workspace_locale=workspace_locale,
                )
            return Execute("query.fact", {"fact_key": fact.key, "fact_id": str(fact.id)})
        case UpdateFact():
            return resolve_update_fact(
                interpretation.fact_key,
                interpretation.raw_value_text,
                interpretation.normalized_value,
                facts,
                currency=currency,
                reason=interpretation.reason,
                user_locale=user_locale,
                workspace_locale=workspace_locale,
            )
        case UpdateBrandVoice():
            return resolve_brand_voice(
                interpretation.instruction,
                interpretation.proposed_guidelines,
                facts,
                user_locale=user_locale,
                workspace_locale=workspace_locale,
            )
        case Clarify():
            return _resolve_model_clarification(
                interpretation,
                facts,
                currency=currency,
                user_locale=user_locale,
                workspace_locale=workspace_locale,
            )
    return UnsupportedOutcome("other")  # unreachable for a validated union


def _resolve_model_clarification(
    clarify: Clarify,
    facts: Sequence[FactSnapshot],
    *,
    user_locale: str,
    workspace_locale: str,
    currency: str,
) -> Outcome:
    seen: dict[str, FactSnapshot] = {}
    for key in clarify.candidate_fact_keys:
        found = _by_key(facts, key)
        if found is not None:
            seen.setdefault(found.key, found)
    candidates = list(seen.values())
    if len(candidates) == 1:  # nothing to ask: continue with the only candidate
        return _continue_with_fact(
            candidates[0].key,
            clarify.intent,
            clarify.raw_value_text,
            facts,
            user_locale=user_locale,
            workspace_locale=workspace_locale,
            currency=currency,
        )
    return _fact_question(
        candidates,
        intent=clarify.intent,
        raw_value_text=clarify.raw_value_text,
        locale=user_locale,
        workspace_locale=workspace_locale,
    )


def _continue_with_fact(
    fact_key: str,
    intent: str,
    raw_value_text: str | None,
    facts: Sequence[FactSnapshot],
    *,
    user_locale: str,
    workspace_locale: str,
    currency: str,
) -> Outcome:
    if intent == "query.fact":
        fact = _by_key(facts, fact_key)
        if fact is None:
            return UnsupportedOutcome("other")
        return Execute("query.fact", {"fact_key": fact.key, "fact_id": str(fact.id)})
    if intent == "knowledge.update_fact" and raw_value_text:
        return resolve_update_fact(
            fact_key,
            raw_value_text,
            None,
            facts,
            user_locale=user_locale,
            workspace_locale=workspace_locale,
            currency=currency,
        )
    return UnsupportedOutcome("other")


def resolve_choice(
    clarification: dict[str, Any],
    option_id: str,
    facts: Sequence[FactSnapshot],
    *,
    user_locale: str,
    workspace_locale: str,
    currency: str,
) -> Outcome | None:
    """Continue after the owner picked ``option_id``. ``None`` if it is not one of the
    options that were offered (a client cannot choose something we never asked about)."""
    options = {o["id"]: o for o in clarification.get("options", [])}
    chosen = options.get(option_id)
    if chosen is None:
        return None
    pending = clarification.get("pending", {})
    if clarification.get("kind") == "fact":
        return _continue_with_fact(
            chosen["id"],
            str(pending.get("intent", "")),
            pending.get("raw_value_text"),
            facts,
            user_locale=user_locale,
            workspace_locale=workspace_locale,
            currency=currency,
        )
    if clarification.get("kind") == "value" and chosen.get("value"):
        return resolve_update_fact(
            str(pending["fact_key"]),
            str(pending["raw_value_text"]),
            None,
            facts,
            user_locale=user_locale,
            workspace_locale=workspace_locale,
            currency=currency,
            reason=pending.get("reason"),
            chosen_money=chosen["value"],
        )
    return None
