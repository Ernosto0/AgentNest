"""Task ``interpret_command`` (agent-runtime.md §3): task definition plus its fake provider.

The real provider maps free text to one command through the model. The fake is a regex grammar
for the documented demo phrases in Turkish and English, so the demo and CI need no credentials
and the whole pipeline (resolution, confirmation, approval, execution) is exercised for real.
Its grammar is deliberately narrow: anything it does not recognise becomes ``unsupported``.
"""

import re
from datetime import date, datetime, timedelta
from typing import Any

from app.ai.prompt import data_section, json_section
from app.ai.runner import TaskDefinition
from app.ai.schemas import (
    MAX_CATALOG_FACTS,
    MAX_COMMAND_CHARS,
    MAX_CONTENT_REF_TEXT_CHARS,
    MAX_NOTES_CHARS,
    MAX_OBJECTIVE_CHARS,
    Clarify,
    ContentCancelScheduled,
    ContentCreateDraft,
    ContentKind,
    ContentRef,
    FactCatalogEntry,
    InterpretCommandInput,
    InterpretCommandOutput,
    NormalizedMoney,
    NormalizedText,
    QueryActivitySummary,
    QueryContentStatus,
    QueryExplainFailure,
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
ALIAS = re.compile(r"C\d{1,3}")
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
            json_section("content_catalog", [c.model_dump() for c in task_input.content_catalog]),
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
    if isinstance(inner, ContentCreateDraft):
        if len(inner.objective) > MAX_OBJECTIVE_CHARS:
            problems.append("objective is too long")
        if inner.notes is not None and len(inner.notes) > MAX_NOTES_CHARS:
            problems.append("notes is too long")
    ref = getattr(inner, "content_ref", None)
    if isinstance(ref, ContentRef):
        problems.extend(_ref_problems(task_input, ref))
    return problems


def _ref_problems(task_input: InterpretCommandInput, ref: ContentRef) -> list[str]:
    """A content reference must be well formed; whether it names anything is code's call."""
    problems: list[str] = []
    if ref.alias is not None and not ALIAS.fullmatch(ref.alias.strip().upper()):
        problems.append("alias must look like C1")
    if ref.local_date is not None:
        try:
            date.fromisoformat(ref.local_date.strip())
        except ValueError:
            problems.append("local_date must be an ISO date (YYYY-MM-DD)")
    if ref.description is not None and len(ref.description) > MAX_CONTENT_REF_TEXT_CHARS:
        problems.append("description is too long")
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


# --- content phrases (tr and en) ------------------------------------------------------------
# Applied to folded text (lower case, no diacritics): "yarınki postu iptal et" is
# "yarinki postu iptal et".

_STORY_WORDS = r"story\w*|stories|hikaye\w*"
_FEED_WORDS = r"post\w*|gonderi\w*"
_OTHER_WORDS = r"paylasim\w*|yayin\w*|icerik\w*|content"
_CONTENT_NOUN = re.compile(rf"\b(?:{_STORY_WORDS}|{_FEED_WORDS}|{_OTHER_WORDS})")
_STORY = re.compile(rf"\b(?:{_STORY_WORDS})")
_FEED = re.compile(rf"\b(?:{_FEED_WORDS})")
_CANCEL_WORDS = re.compile(r"\b(?:iptal\w*|cancel\w*|vazgec\w*|kaldir\w*|call\s+off)")
_STATUS_WORDS = re.compile(
    r"\b(?:durum\w*|status|yayinlandi\s+mi|yayinlanmis\s+mi|hazir\s+mi|ne\s+oldu|is\s+it\s+(?:published|"
    r"scheduled|ready)|where\s+is)"
)
_EXPLAIN_WORDS = re.compile(
    r"\b(?:hata\w*|basarisiz\w*|sorun\w*|ne\s+ters|neden\s+(?:yayinlanmadi|paylasilmadi|"
    r"olmadi)|errors?|fail(?:ed|ure|ures)?|went\s+wrong|why\s+(?:did|was|is|has)\b.{0,40}"
    r"(?:fail|not\s+(?:published|posted|go)|n.t\s+(?:publish|post|go)))"
)
_LATEST = re.compile(r"\b(?:son|sonuncu|en\s+son|last|latest|most\s+recent|recent)\b")
_DRAFT_VERBS = re.compile(
    r"\b(?:hazirla\w*|olustur\w*|yaz\b|yazar\w*|taslak\w*|draft\w*|prepar\w*|creat\w*|writ\w*|"
    r"mak(?:e|ing))"
)
_PUBLISH_VERBS = re.compile(r"\b(?:yayinla\w*|yayimla\w*|publish\w*|go\s+live|post\s+it)\b")
_ALIAS_IN_TEXT = re.compile(r"\bc(\d{1,3})\b")
_DAYS = (
    ("pazartesi", 0), ("monday", 0), ("sali", 1), ("tuesday", 1), ("carsamba", 2),
    ("wednesday", 2), ("persembe", 3), ("thursday", 3), ("cumartesi", 5), ("saturday", 5),
    ("cuma", 4), ("friday", 4), ("pazar", 6), ("sunday", 6),
)  # fmt: skip
_STOPWORDS = frozenset(
    [
        "the",
        "and",
        "for",
        "bir",
        "icin",
        "ile",
        "bu",
        "su",
        "post",
        "story",
        "hikaye",
        "gonderi",
        "paylasim",
        "iptal",
        "cancel",
        "yarin",
        "bugun",
        "yarinki",
        "bugunku",
        "durum",
        "status",
        "hazirla",
        "olustur",
        "yayin",
        "icerik",
        "content",
        "tomorrow",
        "today",
        "what",
        "whats",
        "tell",
        "about",
        "with",
    ]
)


def _today(task_input: InterpretCommandInput) -> date:
    return datetime.fromisoformat(task_input.now_local).date()


def _mentioned_date(folded: str, today: date) -> date | None:
    """The day the owner named: today, tomorrow, yesterday or the next such weekday."""
    if re.search(r"\b(?:yarinki|yarin|tomorrow)", folded):
        return today + timedelta(days=1)
    if re.search(r"\b(?:bugunku|bugun|today)", folded):
        return today
    if re.search(r"\b(?:dunku|dun|yesterday)\b", folded):
        return today - timedelta(days=1)
    for name, weekday in _DAYS:
        if re.search(rf"\b{name}", folded):
            return today + timedelta(days=(weekday - today.weekday()) % 7)
    return None


def _title_hint(folded: str, task_input: InterpretCommandInput) -> str | None:
    """Words of the text that also appear in a catalog title (the owner's own words for it)."""
    words = {w for w in re.findall(r"[a-z0-9]{4,}", folded) if w not in _STOPWORDS}
    shared: list[str] = []
    for entry in task_input.content_catalog:
        title = set(re.findall(r"[a-z0-9]{4,}", fold(entry.title)))
        for word in sorted(words):
            if any(t[:5] == word[:5] for t in title) and word not in shared:
                shared.append(word)
    return " ".join(shared) or None


def _content_ref(task_input: InterpretCommandInput, folded: str) -> ContentRef:
    alias = None
    found = _ALIAS_IN_TEXT.search(folded)
    if found:
        candidate = f"C{int(found.group(1))}"
        if any(e.ref_id == candidate for e in task_input.content_catalog):
            alias = candidate
    day = _mentioned_date(folded, _today(task_input))
    content_type: ContentKind | None = (
        "story_image" if _STORY.search(folded) else "feed_image" if _FEED.search(folded) else None
    )
    return ContentRef(
        alias=alias,
        description=_title_hint(folded, task_input),
        local_date=day.isoformat() if day else None,
        content_type=content_type,
    )


def _draft_objective(text: str) -> str:
    """The subject of a "prepare a story about X" request, else the whole sentence."""
    cleaned = " ".join(text.split()).strip(" .!?")
    noun = r"(?:story|stories|hikaye\w*|hikâye\w*|post|gönderi\w*|gonderi\w*|paylaşım\w*)"
    turkish = re.match(
        rf"(?i)^(?P<subject>.+?)\s+(?:için|icin)\s+(?:bir\s+)?(?:\w+\s+)?{noun}\b.*$", cleaned
    )
    if turkish:
        return turkish.group("subject").strip()
    english = re.match(
        rf"(?i)^.*?\b{noun}\s+(?:about|for|on|announcing|promoting)\s+(?P<subject>.+)$", cleaned
    )
    if english:
        return english.group("subject").strip()
    return cleaned


def _interpret_content(
    task_input: InterpretCommandInput, folded: str
) -> InterpretCommandOutput | None:
    """The content commands, or ``None`` when the text is about something else."""
    noun = _CONTENT_NOUN.search(folded)
    has_amount = bool(AMOUNT.search(folded))
    if noun and _CANCEL_WORDS.search(folded):
        ref = _content_ref(task_input, folded)
        return InterpretCommandOutput(
            interpretation=ContentCancelScheduled(type="content.cancel_scheduled", content_ref=ref)
        )
    if _EXPLAIN_WORDS.search(folded) and not has_amount:
        ref = _content_ref(task_input, folded)
        pointed = ref.alias or ref.local_date or ref.content_type
        if _LATEST.search(folded) or not pointed:
            return InterpretCommandOutput(
                interpretation=QueryExplainFailure(
                    type="query.explain_failure", content_ref="latest_failure"
                )
            )
        return InterpretCommandOutput(
            interpretation=QueryExplainFailure(type="query.explain_failure", content_ref=ref)
        )
    if noun and _STATUS_WORDS.search(folded):
        return InterpretCommandOutput(
            interpretation=QueryContentStatus(
                type="query.content_status", content_ref=_content_ref(task_input, folded)
            )
        )
    if (
        (_STORY.search(folded) or _FEED.search(folded) or "paylasim" in folded)
        and _DRAFT_VERBS.search(folded)
        and not _PUBLISH_VERBS.search(folded)
    ):
        kind: ContentKind = "story_image" if _STORY.search(folded) else "feed_image"
        return InterpretCommandOutput(
            interpretation=ContentCreateDraft(
                type="content.create_draft",
                content_type=kind,
                objective=_draft_objective(task_input.text)[:MAX_OBJECTIVE_CHARS],
                notes=None,
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
    content = _interpret_content(task_input, folded)
    if content is not None:  # before the publish words: "yayını iptal et" is a cancel
        return content
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
