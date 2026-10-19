"""Task ``interpret_command`` (agent-runtime.md §3): task definition plus its fake provider.

The real provider maps free text to one command through the model. The fake is a regex grammar
for the documented demo phrases in Turkish and English, so the demo and CI need no credentials
and the whole pipeline (resolution, confirmation, approval, execution) is exercised for real.
Its grammar is deliberately narrow: anything it does not recognise becomes ``unsupported``.
"""

import re
from typing import Any

from app.ai.prompt import data_section, json_section
from app.ai.runner import TaskDefinition
from app.ai.schemas import (
    MAX_CATALOG_FACTS,
    MAX_COMMAND_CHARS,
    Clarify,
    FactCatalogEntry,
    InterpretCommandInput,
    InterpretCommandOutput,
    NormalizedMoney,
    NormalizedText,
    QueryActivitySummary,
    QueryFact,
    QueryPendingApprovals,
    Unsupported,
    UnsupportedReason,
    UpdateBrandVoice,
    UpdateFact,
)
from app.ai.tasks.matching import AMOUNT, CURRENCY_MARK, PHONE, amount_text, match_facts
from app.integrations.llm.base import LLMMessage
from app.integrations.llm.fake import fake_implementation
from app.knowledge.claims import fold
from app.knowledge.parsing import Money, ParseAmbiguity, ParseError, parse_money

TASK = "interpret_command"
MAX_RAW_VALUE_CHARS = 200
MAX_GUIDELINES_CHARS = 2000
MAX_CANDIDATES = 10


def build_messages(task_input: InterpretCommandInput) -> list[LLMMessage]:
    """Stable, cacheable data first (registry, facts); the owner's text last, as data."""
    parameters = {
        "user_locale": task_input.user_locale,
        "workspace_locale": task_input.workspace_locale,
        "timezone": task_input.timezone,
        "now_local": task_input.now_local,
        "currency": task_input.currency,
    }
    body = "\n\n".join(
        [
            json_section("command_registry", [e.model_dump() for e in task_input.registry]),
            json_section("business_facts", [f.model_dump() for f in task_input.fact_catalog]),
            json_section("task_parameters", parameters),
            data_section("owner_command", task_input.text),
        ]
    )
    return [LLMMessage("user", body)]


def post_validate(task_input: InterpretCommandInput, output: InterpretCommandOutput) -> list[str]:
    """Size limits that the strict provider schema cannot express."""
    inner = output.interpretation
    problems: list[str] = []
    if isinstance(inner, UpdateFact) and len(inner.raw_value_text) > MAX_RAW_VALUE_CHARS:
        problems.append("raw_value_text is too long")
    if (
        isinstance(inner, UpdateBrandVoice)
        and len(inner.proposed_guidelines) > MAX_GUIDELINES_CHARS
    ):
        problems.append("proposed_guidelines is too long")
    if isinstance(inner, Clarify) and len(inner.candidate_fact_keys) > MAX_CANDIDATES:
        problems.append("too many candidate_fact_keys")
    return problems


def snapshot(task_input: InterpretCommandInput) -> dict[str, Any]:
    return task_input.model_dump(mode="json")


INTERPRET_COMMAND: TaskDefinition[InterpretCommandInput, InterpretCommandOutput] = TaskDefinition(
    name=TASK,
    output_schema=InterpretCommandOutput,
    max_output_tokens=800,
    timeout_s=30,
    build_messages=build_messages,
    post_validate=post_validate,
    snapshot=snapshot,
)

# Input limits (agent-runtime.md §2); enforced by the command service before the call.
__all__ = ["INTERPRET_COMMAND", "MAX_CATALOG_FACTS", "MAX_COMMAND_CHARS", "TASK"]

# --- the fake -------------------------------------------------------------------------------

_PRICE_WORDS = re.compile(r"\b(fiyat\w*|ucret\w*|tutar\w*|price\w*|cost\w*|tarife\w*)\b")
_UPDATE_WORDS = re.compile(
    r"\b(artik|simdi|oldu|olsun|olacak|yap|yapin|guncelle\w*|degistir\w*|is now|now|"
    r"update|change|set|make|becomes?|raise|lower)\b"
)
_QUERY_WORDS = re.compile(
    r"\b(kac|ne kadar|nedir|nelerdir|how much|what is|what's|whats|tell me)\b"
)

_PENDING = re.compile(
    r"bekleyen\s+onay|onay\s+bekleyen|onay\w*\s+bekle|pending\s+approval|"
    r"approvals?\s+(?:pending|waiting)|waiting\s+for\s+(?:my\s+)?approval|needs?\s+approval"
)
_UNSUPPORTED: tuple[tuple[UnsupportedReason, re.Pattern[str]], ...] = (
    ("publish", re.compile(r"yayin\w*|yayim\w*|paylas\w*|publish\w*|go\s+live|post\s+it\b")),
    (
        "send_message",
        re.compile(
            r"(mesaj|message|dm).{0,25}(gonder|send|yaz|reply)|(gonder|send).{0,25}(mesaj|message|dm)"
            r"|yanitla|reply\s+to"
        ),
    ),
    (
        "approve",
        re.compile(r"\bonayla\w*|\bonayliyorum|\bapprove\w*|\breject\w*|\breddet\w*|onay\s+ver"),
    ),
    (
        "manage_account",
        re.compile(
            r"\bbaglan\w*|\bbagla\b|\bdisconnect\w*|\bconnect\w*|hesab\w*\s+(?:ekle|kaldir|bagla)"
        ),
    ),
    ("members", re.compile(r"uye\s+ekle|\bekip\b|\bdavet\b|\binvite\b|\bmembers?\b|\byetki\w*")),
    (
        "settings",
        re.compile(
            r"otomasyon|automation|automatic\s+repl\w*|auto[\s-]*repl\w*|politika"
            r"|\bpolic(?:y|ies)\b"
        ),
    ),
)
_BRAND = re.compile(
    r"\b(ton\w*|uslup\w*|brand\s+voice|voice|tone|samimi\w*|resmi\w*|formal\w*|casual|friendl\w*|"
    r"kisa\w*|short\w*)\b"
)
_ACTIVITY_TOPIC = re.compile(
    r"\b(ozet\w*|neler|ne\s+oldu|ne\s+yapildi|aktivite\w*|activity|summary|what\s+happened|"
    r"happened|how\s+many|kac\s+mesaj)\b"
)
_PERIODS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "last_7_days",
        re.compile(
            r"son\s*7\s*gun|last\s*7\s*days|last\s+week|bu\s+hafta|this\s+week|gecen\s+hafta"
        ),
    ),
    ("yesterday", re.compile(r"\bdun\b|\byesterday\b")),
    ("today", re.compile(r"\bbugun\b|\btoday\b")),
)

_BRAND_LINES = {
    "warm": {"tr": "Daha samimi ve sıcak bir ton kullan.", "en": "Use a warmer, friendlier tone."},
    "formal": {
        "tr": "Daha resmi ve saygılı bir ton kullan.",
        "en": "Use a more formal, respectful tone.",
    },
    "short": {"tr": "Yanıtları daha kısa tut.", "en": "Keep replies shorter."},
}


def _money_reading(raw: str, user_locale: str, currency: str) -> NormalizedMoney | None:
    try:
        parsed = parse_money(raw, user_locale, currency)
    except ParseError:
        return None
    money: Money = parsed.alternatives[0] if isinstance(parsed, ParseAmbiguity) else parsed
    return NormalizedMoney(kind="money", amount=str(money.amount), currency=money.currency)


def _unsupported(reason: UnsupportedReason) -> InterpretCommandOutput:
    return InterpretCommandOutput(interpretation=Unsupported(type="unsupported", reason=reason))


def _interpret_update(
    task_input: InterpretCommandInput, folded: str, matches: list[FactCatalogEntry]
) -> InterpretCommandOutput | None:
    catalog = task_input.fact_catalog
    raw = amount_text(task_input.text)
    money_facts = [f for f in catalog if f.value_type == "money"]
    if raw is not None and (_UPDATE_WORDS.search(folded) or CURRENCY_MARK.search(fold(raw))):
        targets = [f for f in matches if f.value_type == "money"]
        if len(targets) == 1:
            return InterpretCommandOutput(
                interpretation=UpdateFact(
                    type="knowledge.update_fact",
                    fact_key=targets[0].key,
                    raw_value_text=raw,
                    normalized_value=_money_reading(
                        raw, task_input.user_locale, task_input.currency
                    ),
                    reason=None,
                )
            )
        if not targets and (_PRICE_WORDS.search(folded) or not matches) and money_facts:
            # "the price is now 7000": which price? Offer the verified prices (else all).
            pricing = [f for f in money_facts if f.category == "pricing"] or money_facts
            verified = [f for f in pricing if f.status == "verified"] or pricing
            return InterpretCommandOutput(
                interpretation=Clarify(
                    type="clarify",
                    intent="knowledge.update_fact",
                    candidate_fact_keys=[f.key for f in verified][:MAX_CANDIDATES],
                    raw_value_text=raw,
                )
            )
        if len(targets) > 1:
            return InterpretCommandOutput(
                interpretation=Clarify(
                    type="clarify",
                    intent="knowledge.update_fact",
                    candidate_fact_keys=[f.key for f in targets][:MAX_CANDIDATES],
                    raw_value_text=raw,
                )
            )
    phone = PHONE.search(task_input.text)
    if phone and _UPDATE_WORDS.search(folded):
        targets = [f for f in matches if f.value_type == "phone"]
        if len(targets) == 1:
            value = phone.group().strip()
            return InterpretCommandOutput(
                interpretation=UpdateFact(
                    type="knowledge.update_fact",
                    fact_key=targets[0].key,
                    raw_value_text=value,
                    normalized_value=NormalizedText(kind="text", text=value),
                    reason=None,
                )
            )
    return None


@fake_implementation(TASK)
def fake_interpret_command(
    task_input: InterpretCommandInput, schema: Any = None
) -> InterpretCommandOutput:
    """Deterministic grammar for the demo phrases (tr and en)."""
    text = task_input.text
    folded = fold(text)

    if _PENDING.search(folded):
        return InterpretCommandOutput(
            interpretation=QueryPendingApprovals(type="query.pending_approvals")
        )
    for reason, pattern in _UNSUPPORTED:
        if pattern.search(folded):
            return _unsupported(reason)

    matches = match_facts(text, task_input.fact_catalog)

    if _BRAND.search(folded) and not AMOUNT.search(folded):
        brand = next(
            (f for f in task_input.fact_catalog if f.key == "brand.voice_guidelines"), None
        )
        if brand is not None:
            kind = (
                "formal"
                if re.search(r"resmi|formal", folded)
                else "short"
                if re.search(r"kisa|short", folded)
                else "warm"
            )
            line = _BRAND_LINES[kind][
                task_input.workspace_locale if task_input.workspace_locale in ("tr", "en") else "tr"
            ]
            current = brand.current_value_display.strip()
            return InterpretCommandOutput(
                interpretation=UpdateBrandVoice(
                    type="knowledge.update_brand_voice",
                    instruction=text.strip()[:300],
                    proposed_guidelines=f"{current} {line}".strip(),
                )
            )

    activity = _ACTIVITY_TOPIC.search(folded)
    if activity:
        for period, pattern in _PERIODS:
            if pattern.search(folded):
                return InterpretCommandOutput(
                    interpretation=QueryActivitySummary(
                        type="query.activity_summary",
                        period=period,
                    )
                )
        return InterpretCommandOutput(
            interpretation=QueryActivitySummary(type="query.activity_summary", period="today")
        )

    update = _interpret_update(task_input, folded, matches)
    if update is not None:
        return update

    if matches and (_QUERY_WORDS.search(folded) or not AMOUNT.search(folded)):
        if len(matches) == 1:
            return InterpretCommandOutput(
                interpretation=QueryFact(type="query.fact", fact_key=matches[0].key)
            )
        return InterpretCommandOutput(
            interpretation=Clarify(
                type="clarify",
                intent="query.fact",
                candidate_fact_keys=[f.key for f in matches][:MAX_CANDIDATES],
                raw_value_text=None,
            )
        )
    return _unsupported("other")
