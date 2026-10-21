"""Deterministic resolution of an interpretation (agent-runtime.md §3, workflows.md §B).

The model's output is a *proposal*. Everything here is plain code: the referenced fact must
exist in the workspace catalog (else the closest keys are offered), the value is **re-parsed**
from the text the owner typed with the locale-aware parser and compared with the model's reading
(a disagreement becomes a question, never a guess), and the result is one of a few outcomes
that the service turns into state. No database, no clock, no LLM: all inputs are passed in.
"""

import difflib
import re
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Literal
from zoneinfo import ZoneInfo

from app.ai.schemas import (
    Clarify,
    CommandInterpretation,
    ContentCancelScheduled,
    ContentCreateDraft,
    ContentRef,
    NormalizedBoolean,
    NormalizedMoney,
    NormalizedValue,
    QueryActivitySummary,
    QueryContentStatus,
    QueryExplainFailure,
    QueryFact,
    QueryPendingApprovals,
    Unsupported,
    UpdateBrandVoice,
    UpdateFact,
)
from app.commands.results import CommandResult
from app.core.errors import AppError
from app.core.i18n import format_local_slot
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
    kind: Literal["fact", "value", "content"]
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
    payload: dict[str, Any]  # hashed into the approval
    summary: dict[str, Any]  # shown on the confirmation card
    # The fact whose impact the card previews; ``None`` for commands that change no fact.
    fact_id: uuid.UUID | None = None


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


# --- content references ---------------------------------------------------------------------

CANCEL_FILTER_STATUSES = ("pending_approval", "scheduled", "retry_scheduled", "on_hold")
CANCELLABLE_STATUSES = frozenset({"draft", *CANCEL_FILTER_STATUSES})  # content/transitions.py
FAILURE_STATUSES = ("failed", "on_hold", "retry_scheduled")
STATUS_QUERY_STATUSES = (
    "draft",
    "pending_approval",
    "scheduled",
    "publishing",
    "retry_scheduled",
    "on_hold",
    "published",
    "rejected",
    "failed",
)  # everything but ``cancelled``
MAX_CONTENT_OPTIONS = 5
LATEST_FAILURE = "latest_failure"
_WORD = re.compile(r"[a-z0-9]{3,}")


@dataclass(frozen=True)
class ContentSnapshot:
    """A content item as the resolver needs it (the model never sees ids)."""

    id: uuid.UUID
    title: str
    content_type: str
    status: str
    version: int
    scheduled_at: datetime | None
    updated_at: datetime
    last_error_code: str | None = None
    hold_reason: str | None = None
    is_simulated: bool = False


@dataclass(frozen=True)
class ReplyFailureSnapshot:
    """A reply (``send_reply`` operation) that ended ``failed``, for ``latest_failure``."""

    id: uuid.UUID
    completed_at: datetime
    error_code: str | None = None
    is_simulated: bool = False


@dataclass(frozen=True)
class ContentContext:
    """What a content reference is resolved against: the candidates, the aliases the model
    was shown (alias -> item id) and the workspace timezone (INV-19).

    ``latest_failure`` looks at the content items in trouble and at ``reply_failures`` and takes
    the newest of them; with a ``failure_cutoff`` only those since then (H6: the last 7 days)."""

    items: Sequence[ContentSnapshot]
    aliases: Mapping[str, uuid.UUID]
    timezone: str
    reply_failures: Sequence[ReplyFailureSnapshot] = ()
    failure_cutoff: datetime | None = None


def _sort_key(item: ContentSnapshot) -> tuple[bool, datetime, str]:
    return (item.scheduled_at is None, item.scheduled_at or item.updated_at, str(item.id))


def _local_day(item: ContentSnapshot, tz: ZoneInfo) -> date | None:
    return item.scheduled_at.astimezone(tz).date() if item.scheduled_at else None


def _words(text: str) -> set[str]:
    return set(_WORD.findall(fold(text)))


def _described(item: ContentSnapshot, description: str) -> bool:
    """A loose match of the owner's few words against the title: every word of the
    description is a word of the title or shares its first five letters (Turkish suffixes)."""
    wanted = _words(description)
    if not wanted:
        return False
    title = _words(item.title)
    return all(any(t[:5] == w[:5] for t in title) for w in wanted)


def _find_content(
    ref: ContentRef, content: ContentContext, statuses: Sequence[str]
) -> tuple[list[ContentSnapshot], bool]:
    """The items ``ref`` may mean, soonest first, and whether the alias named one directly.

    An alias the model was shown is the owner's pick and skips the filters. Otherwise the
    candidates are narrowed by local date (workspace timezone), type and the status set of the
    command; the description only narrows, it never empties a result by itself."""
    alias = (ref.alias or "").strip().upper()
    if alias:
        wanted_id = content.aliases.get(alias)
        found = next((i for i in content.items if i.id == wanted_id), None)
        if found is not None:
            return [found], True
    description = (ref.description or "").strip()
    if alias and not (ref.local_date or ref.content_type or description):
        return [], False  # an alias that names nothing, and nothing else to go by
    candidates = [item for item in content.items if item.status in statuses]
    if ref.local_date:
        try:
            wanted_day = date.fromisoformat(ref.local_date.strip())
        except ValueError:
            return [], False
        tz = ZoneInfo(content.timezone)
        candidates = [i for i in candidates if _local_day(i, tz) == wanted_day]
    if ref.content_type:
        candidates = [i for i in candidates if i.content_type == ref.content_type]
    if description and len(candidates) > 1:
        narrowed = [i for i in candidates if _described(i, description)]
        candidates = narrowed or candidates
    return sorted(candidates, key=_sort_key), False


def _slot(item: ContentSnapshot, content: ContentContext, locale: str) -> str | None:
    if item.scheduled_at is None:
        return None
    return format_local_slot(item.scheduled_at, content.timezone, locale)


def content_link(content_id: uuid.UUID | str) -> dict[str, Any]:
    """A result link to one content item (structured, no frontend route)."""
    return {"target": "content", "id": str(content_id)}


def _not_found(description: str | None) -> Rejected:
    return Rejected(
        "REFERENCE_NOT_FOUND",
        CommandResult(
            "command.reference_not_found",
            {"description": (description or "").strip()[:MAX_REASON_CHARS] or None},
            [{"target": "content"}],
            error_code="REFERENCE_NOT_FOUND",
        ),
    )


def _content_choice(
    intent: str, matches: Sequence[ContentSnapshot], content: ContentContext, locale: str
) -> NeedsClarification:
    options = []
    for index, item in enumerate(matches[:MAX_CONTENT_OPTIONS], start=1):
        slot = _slot(item, content, locale)
        options.append(
            ClarifyOption(
                id=str(index),
                label=f"{item.title} · {slot}" if slot else item.title,
                value={"content_id": str(item.id)},
            )
        )
    return NeedsClarification(
        kind="content",
        question_key="command.clarify.which_content",
        params={"count": len(matches)},
        options=tuple(options),
        pending={"intent": intent},
    )


def _cancel_outcome(item: ContentSnapshot, content: ContentContext, locale: str) -> Outcome:
    if item.status not in CANCELLABLE_STATUSES:
        return Rejected(
            "CONFLICT_STATE",
            CommandResult(
                "command.content_not_cancellable",
                {"title": item.title, "status": item.status},
                [content_link(item.id)],
                error_code="CONFLICT_STATE",
            ),
        )
    return Confirm(
        command_type="content.cancel_scheduled",
        action="command.cancel_content",
        payload={"content_id": str(item.id), "content_version": item.version},
        summary={
            "label": item.title,
            "content_type": item.content_type,
            "status": item.status,
            "when": _slot(item, content, locale),
            "content_id": str(item.id),
        },
    )


def _content_outcome(
    intent: str, item: ContentSnapshot, content: ContentContext, locale: str
) -> Outcome:
    if intent == "content.cancel_scheduled":
        return _cancel_outcome(item, content, locale)
    return Execute(intent, {"content_id": str(item.id)})


def resolve_content_ref(
    intent: str,
    ref: ContentRef | Literal["latest_failure"],
    content: ContentContext | None,
    *,
    user_locale: str,
) -> Outcome:
    """Turn a content reference into one item (then the command's own outcome), a question
    (several candidates) or ``REFERENCE_NOT_FOUND`` (none). Never guesses (agent-runtime.md §3)."""
    context = content or ContentContext((), {}, "UTC")
    if not isinstance(ref, ContentRef):  # "latest_failure"
        cutoff = context.failure_cutoff
        failures = [
            i
            for i in context.items
            if i.status in FAILURE_STATUSES and (cutoff is None or i.updated_at >= cutoff)
        ]
        replies = [r for r in context.reply_failures if cutoff is None or r.completed_at >= cutoff]
        latest = max(failures, key=lambda i: (i.updated_at, str(i.id)), default=None)
        latest_reply = max(replies, key=lambda r: (r.completed_at, str(r.id)), default=None)
        if latest is not None and (
            latest_reply is None or latest.updated_at >= latest_reply.completed_at
        ):
            return Execute(intent, {"content_id": str(latest.id)})
        if latest_reply is not None:
            return Execute(intent, {"operation_id": str(latest_reply.id)})
        return Completed(CommandResult("command.no_failure", {}, [{"target": "content"}]))
    if intent == "content.cancel_scheduled":
        statuses: Sequence[str] = CANCEL_FILTER_STATUSES
    elif intent == "query.explain_failure":
        statuses = FAILURE_STATUSES
    else:
        statuses = STATUS_QUERY_STATUSES
    matches, _direct = _find_content(ref, context, statuses)
    if not matches:
        return _not_found(ref.description)
    if len(matches) > 1:
        return _content_choice(intent, matches, context, user_locale)
    return _content_outcome(intent, matches[0], context, user_locale)


def resolve_create_draft(interpretation: ContentCreateDraft) -> Outcome:
    objective = interpretation.objective.strip()
    if not objective:
        return Rejected(
            "VALIDATION_FAILED",
            CommandResult("command.draft_unreadable", {}, error_code="VALIDATION_FAILED"),
        )
    return Execute(
        "content.create_draft",
        {
            "content_type": interpretation.content_type,
            "objective": objective,
            "notes": (interpretation.notes or "").strip() or None,
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
    content: ContentContext | None = None,
) -> Outcome:
    """Turn the model's proposal into an outcome. Anything not in the registry is
    ``unsupported``; there is no branch here that can approve, publish or send."""
    match interpretation:
        case Unsupported():
            return UnsupportedOutcome(interpretation.reason)
        case QueryContentStatus():
            return resolve_content_ref(
                "query.content_status", interpretation.content_ref, content, user_locale=user_locale
            )
        case QueryExplainFailure():
            return resolve_content_ref(
                "query.explain_failure",
                interpretation.content_ref,
                content,
                user_locale=user_locale,
            )
        case ContentCancelScheduled():
            return resolve_content_ref(
                "content.cancel_scheduled",
                interpretation.content_ref,
                content,
                user_locale=user_locale,
            )
        case ContentCreateDraft():
            return resolve_create_draft(interpretation)
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
    content: ContentContext | None = None,
) -> Outcome | None:
    """Continue after the owner picked ``option_id``. ``None`` if it is not one of the
    options that were offered (a client cannot choose something we never asked about)."""
    options = {o["id"]: o for o in clarification.get("options", [])}
    chosen = options.get(option_id)
    if chosen is None:
        return None
    pending = clarification.get("pending", {})
    if clarification.get("kind") == "content":
        context = content or ContentContext((), {}, "UTC")
        wanted = (chosen.get("value") or {}).get("content_id")
        item = next((i for i in context.items if str(i.id) == wanted), None)
        if item is None:  # gone since the question was asked
            return _not_found(None)
        return _content_outcome(str(pending.get("intent", "")), item, context, user_locale)
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
