"""Deterministic basic-versus-complex reply policy matrix for Account Agent (INV-04).

Enforces the authoritative policy matrix:
- Greetings, verified hours, location/contact, service descriptions:
  Automatic only when owner grants automatic mode AND all existing checks pass.
- Standard verified price question:
  Automatic only when price disclosure is allowed, surface is private, and price is verified.
- Mixed topics or unclear request; missing/stale/conflicting info:
  Requires approval/clarification; never guess a business value.
- Custom quote, exception, discount or negotiation:
  Owner approval/input required.
- Complaint, refund, legal/health-safety, abusive, suspected injection:
  Preserves human-handoff or block rule; approval cannot bypass a blocked action.
- Voice-derived reply:
  Approval required under the transcript rule.
- Mutations (calendar, publishing, destructive moderation):
  Retain separately configured action authority; pilot mutations require approval.

Topic rules restrict, never broaden: a reply can be automatic ONLY when the owner grant
is automatic AND the server-side deterministic classification admits it as basic.
"""

from __future__ import annotations

import re
from collections.abc import Collection
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from app.agent.delegation import ActionRule, Decision
from app.ai.injection import detect_injection
from app.inbox.escalation import keyword_flags, matches_escalation_keywords
from app.knowledge.claims import fold, strip_directional_marks
from app.knowledge.render import placeholder_keys


class Topic(StrEnum):
    GREETING = "greeting"
    HOURS = "hours"
    LOCATION_CONTACT = "location_contact"
    SERVICES = "services"
    PRICING = "pricing"
    CUSTOM_QUOTE_DISCOUNT = "custom_quote_discount"
    BOOKING_MUTATION = "booking_mutation"
    COMPLAINT = "complaint"
    REFUND = "refund"
    LEGAL = "legal"
    HEALTH_SAFETY = "health_safety"
    ABUSIVE = "abusive"
    PERSONAL_DATA = "personal_data"
    INJECTION = "injection"
    UNKNOWN = "unknown"


class Complexity(StrEnum):
    BASIC = "basic"
    COMPLEX = "complex"
    BLOCKED = "blocked"


# Pilot mutation actions that must propose approval rather than auto-executing
MUTATION_ACTIONS: frozenset[str] = frozenset(
    {
        "calendar.book",
        "calendar.reschedule",
        "calendar.cancel",
        "content.publish",
        "comment.delete",
        "comment.hide",
    }
)

# Standard basic FAQ fact key prefixes
_FACT_TOPIC_MAP: tuple[tuple[str, Topic], ...] = (
    ("hours.", Topic.HOURS),
    ("location.", Topic.LOCATION_CONTACT),
    ("contact.", Topic.LOCATION_CONTACT),
    ("service.", Topic.SERVICES),
    ("pricing.", Topic.PRICING),
    ("policy.price_answer_text", Topic.PRICING),
)

# Multilingual regex patterns for customer inbound text (TR, EN, DE, RU, AR)
# Evaluated on folded text (length-preserving fold + stripped directional marks).
_TOPIC_PATTERNS: dict[Topic, re.Pattern[str]] = {
    Topic.GREETING: re.compile(
        r"\b(?:merhaba|selam|gunaydin|iyi gunler|iyi aksamlar|iyi geceler|kolay gelsin"
        r"|hello|hi|hey|good morning|good afternoon|good evening"
        r"|hallo|guten tag|guten morgen|guten abend|servus|gruss gott"
        r"|привет|здравствуйте|добрый день|доброе утро|добрый вечер)\b"
        r"|(?:مرحبا|اهلا|السلام عليكم|صباح الخير|مساء الخير)"
    ),
    Topic.HOURS: re.compile(
        r"\b(?:calisma saat\w*|saatler\w*|kacta ac\w*|kacta kapan\w*|kaca kadar"
        r"|acik misiniz|mesai|pazar acik|hafta sonu acik|hangi saatler"
        r"|hours|opening hours|operating hours|open hours|business hours"
        r"|what time.*(?:open|close)|are you open|closing time|opening time"
        r"|offnungszeiten|wann offen|offnen|schliesen|arbeitszeiten"
        r"|часы работы|график работы|время работы|режим работы|когда открыто"
        r"|до скольки|со скольки|вы открыты)\b"
        r"|(?:ساعات العمل|اوقات العمل|متى تفتحون|متى تغلقون|هل انتم مفتوحون|مواعيد العمل|وقت العمل)"
    ),
    Topic.LOCATION_CONTACT: re.compile(
        r"\b(?:adres\w*|neredesiniz|nerede|konum\w*|harita\w*|telefon\w*|numara\w*"
        r"|iletisim\w*|ulasim\w*|yol tarifi|nasil gelebilirim"
        r"|address\w*|location\w*|where are you|where located|where is|phone\w*"
        r"|telephone\w*|contact\w*|directions|how to reach|map"
        r"|adresse\w*|standort\w*|wo sind sie|wo befindet|telefon\w*|kontakt\w*"
        r"|anfahrt\w*|wegbeschreibung"
        r"|адрес\w*|где вы находитесь|где находитесь|где вы|локация\w*|телефон\w*"
        r"|контакты|как добраться|номер телефона)\b"
        r"|(?:عنوان|اين موقعكم|اين انتم|موقع|هاتف|رقم الهاتف|اتصال|تواصل|كيف اصل|مكانكم)"
    ),
    Topic.SERVICES: re.compile(
        r"\b(?:hizmet\w*|neler yapiyorsunuz|ne yapiyorsunuz|menude ne var|menunuz"
        r"|hangi hizmetler|hizmet veriyor"
        r"|service\w*|what do you offer|what do you do|menu|offerings|what kind of service"
        r"|dienstleistung\w*|was bieten sie an|angebot|menue"
        r"|услуг\w*|какие услуги|что вы предлагаете|что делаете|меню|список услуг)\b"
        r"|(?:خدمات|خدمة|ما هي الخدمات|ماذا تقدمون|قائمة|ما هي قائمة)"
    ),
    Topic.PRICING: re.compile(
        r"\b(?:fiyat\w*|ucret\w*|kac para|kac tl|ne kadar|tarifesi|tarife"
        r"|price\w*|pricing|cost\w*|how much|rates?|fees?"
        r"|preis\w*|kost\w*|wie viel|gebuhren"
        r"|цен\w*|стоимост\w*|сколько сто[ия]т\w*|прайс\w*)\b"
        r"|(?:(?<!مرحبا\s)بكم|سعر|اسعار|كم السعر|تكلفة|كم يكلف|كم ثمن)"
    ),
    Topic.CUSTOM_QUOTE_DISCOUNT: re.compile(
        r"\b(?:teklif\w*|ozel teklif|ozel fiyat|toplu fiyat|fiyatta anlas\w*|bir seyler yap\w*"
        r"|ogrenci indirim\w*|pazarlik\w*|ozel indirim\w*|istisna\w*|anlasma|pazarlik payi"
        r"|butceme gore|quote\w*|custom quote|deal\w*|bargain\w*|negotiat\w*|bulk price"
        r"|special price|special discount|exception\w*|best price|can you lower"
        r"|lower the price|budget|angebot\w*|sonderpreis\w*|verhandel\w*|mengenrabatt\w*"
        r"|spezialangebot\w*|ausnahme\w*|nachlass\w*|индивидуальный расчет"
        r"|договориться о цене|специальная цена|торг\w*|оптовая цена"
        r"|уступите|исключение\w*|дешевле|сделайте скидку)\b"
        r"|(?:عرض خاص|سعر خاص|تفاوض|هل يمكن تخفيض|استثناء|سعر اقل)"
    ),
    Topic.BOOKING_MUTATION: re.compile(
        r"\b(?:randevu\w*|rezervasyon\w*|iptal\w*|ertele\w*|degistir\w*|saat degis\w*"
        r"|book\w*|appointment\w*|reservation\w*|reschedule\w*|schedule\w*|cancel\w*"
        r"|termin\w*|buchen|buchung\w*|reservierung\w*|verschieben|absagen|stornieren"
        r"|запис\w*|забронир\w*|бронирован\w*|отмен\w*|перенес\w*|перенести|отменить|записаться)\b"
        r"|(?:حجز|موعد|الغاء|تأجيل|تغيير الموعد)"
    ),
    Topic.COMPLAINT: re.compile(
        r"\b(?:жалов\w*|ужасн\w*\s+сервис|плохой\s+сервис|beschwer\w*|schlechter\s+service)\b"
    ),
}

_MIXED_SERVICES_AND_PRICES = re.compile(
    r"\b(?:hizmet\w*\s+ve\s+fiyat\w*|services?\s+and\s+pric\w*"
    r"|dienstleistung\w*\s+und\s+preis\w*|services?\s+und\s+preis\w*"
    r"|услуг\w*\s+и\s+цен\w*)\b"
    r"|(?:خدمات\s*و\s*اسعار|خدمات\s*و\s*سعر)"
)


@dataclass(frozen=True)
class PolicyClassification:
    topics: tuple[str, ...]
    primary_topic: str
    complexity: Complexity
    reason: str
    inbound_flags: tuple[str, ...]
    injection_patterns: tuple[str, ...]
    fact_categories: tuple[str, ...]
    is_mixed: bool
    is_basic: bool
    requires_human: bool
    is_blocked: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "topics": list(self.topics),
            "primary_topic": self.primary_topic,
            "complexity": self.complexity.value,
            "reason": self.reason,
            "inbound_flags": list(self.inbound_flags),
            "injection_patterns": list(self.injection_patterns),
            "fact_categories": list(self.fact_categories),
            "is_mixed": self.is_mixed,
            "is_basic": self.is_basic,
            "requires_human": self.requires_human,
            "is_blocked": self.is_blocked,
        }


def fact_topic(fact_key: str) -> Topic | None:
    """Map a business fact key to its canonical topic category."""
    for prefix, topic in _FACT_TOPIC_MAP:
        if fact_key.startswith(prefix):
            return topic
    return None


def detect_inbound_topics(
    text: str | None,
    workspace_escalation_keywords: list[str] | None = None,
) -> tuple[set[Topic], set[str], list[str]]:
    """Detect topics, keyword flags, and injection patterns from customer inbound text."""
    if not text or not text.strip():
        return set(), set(), []

    # 1. Prompt Injection Heuristics
    injection_hits = detect_injection(text)

    # 2. Escalation signals (keyword flags + workspace keywords)
    flags = keyword_flags(text)
    if workspace_escalation_keywords and matches_escalation_keywords(
        text, workspace_escalation_keywords
    ):
        flags.add("workspace_escalation_keyword")

    # 3. Topic pattern matching over folded text
    folded = fold(strip_directional_marks(text))
    matched_topics: set[Topic] = set()

    for topic, pattern in _TOPIC_PATTERNS.items():
        if pattern.search(folded):
            matched_topics.add(topic)

    # Escalation flags enrich topics
    if "discount" in flags:
        matched_topics.add(Topic.CUSTOM_QUOTE_DISCOUNT)
    if "complaint" in flags:
        matched_topics.add(Topic.COMPLAINT)
    if "refund" in flags:
        matched_topics.add(Topic.REFUND)
    if "legal" in flags:
        matched_topics.add(Topic.LEGAL)
    if "health_safety" in flags:
        matched_topics.add(Topic.HEALTH_SAFETY)
    if "abusive" in flags:
        matched_topics.add(Topic.ABUSIVE)
    if "personal_data" in flags:
        matched_topics.add(Topic.PERSONAL_DATA)
    if injection_hits:
        matched_topics.add(Topic.INJECTION)

    return matched_topics, flags, injection_hits


def classify_request(
    *,
    action_type: str,
    surface: str,
    inbound_text: str | None = None,
    template: str | None = None,
    used_fact_keys: Collection[str] = (),
    owner_answer: bool = False,
    customer_clarification: bool = False,
    prices_shared: bool = False,
    recent_transcript: bool = False,
    image_injection: bool = False,
    workspace_escalation_keywords: list[str] | None = None,
) -> PolicyClassification:
    """Classify an agent proposed action against the basic-versus-complex policy matrix."""
    # 1. Deterministic Injection Refusal (INV-03)
    inbound_topics, flags, injection_hits = detect_inbound_topics(
        inbound_text, workspace_escalation_keywords
    )
    if image_injection or injection_hits:
        return PolicyClassification(
            topics=(Topic.INJECTION.value,),
            primary_topic=Topic.INJECTION.value,
            complexity=Complexity.BLOCKED,
            reason="injection_suspected",
            inbound_flags=tuple(sorted(flags)),
            injection_patterns=tuple(sorted(injection_hits)),
            fact_categories=(),
            is_mixed=False,
            is_basic=False,
            requires_human=True,
            is_blocked=True,
        )

    # 2. Deterministic Escalation Signals (INV-04)
    escalation_order = (
        ("complaint", Topic.COMPLAINT, "escalation_complaint"),
        ("refund", Topic.REFUND, "escalation_refund"),
        ("legal", Topic.LEGAL, "escalation_legal"),
        ("health_safety", Topic.HEALTH_SAFETY, "escalation_health_safety"),
        ("abusive", Topic.ABUSIVE, "escalation_abusive"),
        ("personal_data", Topic.PERSONAL_DATA, "escalation_personal_data"),
        ("workspace_escalation_keyword", Topic.COMPLAINT, "escalation_workspace_keyword"),
    )
    for flag, topic_enum, reason_code in escalation_order:
        if flag in flags or topic_enum in inbound_topics:
            return PolicyClassification(
                topics=tuple(sorted({t.value for t in inbound_topics})),
                primary_topic=topic_enum.value,
                complexity=Complexity.BLOCKED,
                reason=reason_code,
                inbound_flags=tuple(sorted(flags)),
                injection_patterns=(),
                fact_categories=(),
                is_mixed=len(inbound_topics) > 1,
                is_basic=False,
                requires_human=True,
                is_blocked=True,
            )

    # 3. Voice Transcript Presence (Rule F-03)
    if recent_transcript:
        return PolicyClassification(
            topics=tuple(sorted({t.value for t in inbound_topics})),
            primary_topic="voice_transcript",
            complexity=Complexity.COMPLEX,
            reason="voice_transcript_requires_approval",
            inbound_flags=tuple(sorted(flags)),
            injection_patterns=(),
            fact_categories=(),
            is_mixed=False,
            is_basic=False,
            requires_human=True,
            is_blocked=False,
        )

    # 4. Pilot Mutations (Calendar, Publication, Destructive Moderation)
    if action_type in MUTATION_ACTIONS:
        mutation_topics = {t.value for t in inbound_topics} | {Topic.BOOKING_MUTATION.value}
        return PolicyClassification(
            topics=tuple(sorted(mutation_topics)),
            primary_topic=Topic.BOOKING_MUTATION.value,
            complexity=Complexity.COMPLEX,
            reason="pilot_mutation_requires_approval",
            inbound_flags=tuple(sorted(flags)),
            injection_patterns=(),
            fact_categories=(),
            is_mixed=False,
            is_basic=False,
            requires_human=True,
            is_blocked=False,
        )

    # Extract fact topics from used facts or template placeholders
    fact_keys = set(used_fact_keys)
    if template:
        fact_keys.update(placeholder_keys(template))
    fact_topics = {t for k in fact_keys if (t := fact_topic(k)) is not None}
    fact_categories_list = tuple(sorted({t.value for t in fact_topics}))

    # 5. Custom Quote, Discount or Negotiation
    if Topic.CUSTOM_QUOTE_DISCOUNT in inbound_topics:
        return PolicyClassification(
            topics=tuple(sorted({t.value for t in inbound_topics})),
            primary_topic=Topic.CUSTOM_QUOTE_DISCOUNT.value,
            complexity=Complexity.COMPLEX,
            reason="complex_discount_or_negotiation",
            inbound_flags=tuple(sorted(flags)),
            injection_patterns=(),
            fact_categories=fact_categories_list,
            is_mixed=len(inbound_topics) > 1,
            is_basic=False,
            requires_human=True,
            is_blocked=False,
        )

    # 6. Customer Clarification / Owner Answer Proposal Handling
    if customer_clarification:
        return PolicyClassification(
            topics=("clarification",),
            primary_topic="clarification",
            complexity=Complexity.COMPLEX,
            reason="customer_clarification_requires_approval",
            inbound_flags=tuple(sorted(flags)),
            injection_patterns=(),
            fact_categories=fact_categories_list,
            is_mixed=False,
            is_basic=False,
            requires_human=True,
            is_blocked=False,
        )

    if owner_answer:
        # Owner answers are owner-provided input for a complex request
        return PolicyClassification(
            topics=("owner_answer",),
            primary_topic="owner_answer",
            complexity=Complexity.COMPLEX,
            reason="owner_answer_requires_approval",
            inbound_flags=tuple(sorted(flags)),
            injection_patterns=(),
            fact_categories=fact_categories_list,
            is_mixed=False,
            is_basic=False,
            requires_human=True,
            is_blocked=False,
        )

    # 7. Check for Substantive Topics & Mixed Topics
    substantive_topics = set(inbound_topics - {Topic.GREETING})
    has_greeting = Topic.GREETING in inbound_topics

    # Resolve "price of a service" question (e.g. "Was kostet dieser Service?")
    # vs distinct "services and prices" question
    if Topic.PRICING in substantive_topics and Topic.SERVICES in substantive_topics:
        folded_text = fold(strip_directional_marks(inbound_text or ""))
        if not _MIXED_SERVICES_AND_PRICES.search(folded_text):
            substantive_topics.discard(Topic.SERVICES)

    if len(substantive_topics) > 1:
        return PolicyClassification(
            topics=tuple(sorted({t.value for t in inbound_topics})),
            primary_topic="mixed",
            complexity=Complexity.COMPLEX,
            reason="mixed_topics",
            inbound_flags=tuple(sorted(flags)),
            injection_patterns=(),
            fact_categories=fact_categories_list,
            is_mixed=True,
            is_basic=False,
            requires_human=True,
            is_blocked=False,
        )

    # If fact topics conflict with detected substantive inbound topic
    if substantive_topics and fact_topics and not (substantive_topics & fact_topics):
        return PolicyClassification(
            topics=tuple(sorted({t.value for t in (inbound_topics | fact_topics)})),
            primary_topic="conflicting",
            complexity=Complexity.COMPLEX,
            reason="conflicting_topics_and_facts",
            inbound_flags=tuple(sorted(flags)),
            injection_patterns=(),
            fact_categories=fact_categories_list,
            is_mixed=True,
            is_basic=False,
            requires_human=True,
            is_blocked=False,
        )

    # Determine resolved topic
    resolved_topic: Topic | None = None
    if substantive_topics:
        resolved_topic = next(iter(substantive_topics))
    elif fact_topics:
        resolved_topic = next(iter(fact_topics))
    elif has_greeting:
        resolved_topic = Topic.GREETING

    # 8. Unclear or Unrecognized Request
    if resolved_topic is None:
        return PolicyClassification(
            topics=(),
            primary_topic=Topic.UNKNOWN.value,
            complexity=Complexity.COMPLEX,
            reason="unclear_or_unrecognized_request",
            inbound_flags=tuple(sorted(flags)),
            injection_patterns=(),
            fact_categories=fact_categories_list,
            is_mixed=False,
            is_basic=False,
            requires_human=True,
            is_blocked=False,
        )

    # 9. Pricing Evaluation (Standard Verified Price Question)
    if resolved_topic == Topic.PRICING or Topic.PRICING in fact_topics:
        # Public comments must NEVER disclose prices
        if surface == "comment" and action_type == "comment.reply":
            return PolicyClassification(
                topics=(Topic.PRICING.value,),
                primary_topic=Topic.PRICING.value,
                complexity=Complexity.COMPLEX,
                reason="price_disclosure_forbidden_in_public",
                inbound_flags=tuple(sorted(flags)),
                injection_patterns=(),
                fact_categories=fact_categories_list,
                is_mixed=False,
                is_basic=False,
                requires_human=True,
                is_blocked=False,
            )
        # Price disclosure permission check
        if not prices_shared:
            return PolicyClassification(
                topics=(Topic.PRICING.value,),
                primary_topic=Topic.PRICING.value,
                complexity=Complexity.COMPLEX,
                reason="price_disclosure_not_allowed",
                inbound_flags=tuple(sorted(flags)),
                injection_patterns=(),
                fact_categories=fact_categories_list,
                is_mixed=False,
                is_basic=False,
                requires_human=True,
                is_blocked=False,
            )
        # Price disclosure allowed, private surface, verified facts
        return PolicyClassification(
            topics=(Topic.PRICING.value,),
            primary_topic=Topic.PRICING.value,
            complexity=Complexity.BASIC,
            reason="basic_verified_pricing",
            inbound_flags=tuple(sorted(flags)),
            injection_patterns=(),
            fact_categories=fact_categories_list,
            is_mixed=False,
            is_basic=True,
            requires_human=False,
            is_blocked=False,
        )

    # 10. Standard Basic FAQ Topics
    basic_topic_reasons = {
        Topic.GREETING: "basic_greeting",
        Topic.HOURS: "basic_verified_hours",
        Topic.LOCATION_CONTACT: "basic_verified_location_contact",
        Topic.SERVICES: "basic_verified_services",
    }
    if resolved_topic in basic_topic_reasons:
        topics_set = {resolved_topic.value}
        if has_greeting:
            topics_set.add(Topic.GREETING.value)
        return PolicyClassification(
            topics=tuple(sorted(topics_set)),
            primary_topic=resolved_topic.value,
            complexity=Complexity.BASIC,
            reason=basic_topic_reasons[resolved_topic],
            inbound_flags=tuple(sorted(flags)),
            injection_patterns=(),
            fact_categories=fact_categories_list,
            is_mixed=False,
            is_basic=True,
            requires_human=False,
            is_blocked=False,
        )

    # 11. Booking Mutations / Enquiries
    if resolved_topic == Topic.BOOKING_MUTATION or Topic.BOOKING_MUTATION in inbound_topics:
        return PolicyClassification(
            topics=tuple(sorted({t.value for t in inbound_topics})),
            primary_topic=Topic.BOOKING_MUTATION.value,
            complexity=Complexity.COMPLEX,
            reason="booking_enquiry_requires_approval",
            inbound_flags=tuple(sorted(flags)),
            injection_patterns=(),
            fact_categories=fact_categories_list,
            is_mixed=len(inbound_topics) > 1,
            is_basic=False,
            requires_human=True,
            is_blocked=False,
        )

    # Fallback to Complex
    return PolicyClassification(
        topics=(resolved_topic.value,),
        primary_topic=resolved_topic.value,
        complexity=Complexity.COMPLEX,
        reason=f"complex_topic_{resolved_topic.value}",
        inbound_flags=tuple(sorted(flags)),
        injection_patterns=(),
        fact_categories=fact_categories_list,
        is_mixed=False,
        is_basic=False,
        requires_human=True,
        is_blocked=False,
    )


def evaluate_action_policy(
    rule: ActionRule,
    classification: PolicyClassification,
    *,
    base_decision: Decision,
) -> Decision:
    """Apply the basic-versus-complex policy matrix to a proposed action decision.

    Core Invariant (INV-04):
    Topic rules restrict, never broaden.
    A reply is 'automatic' ONLY when base decision is 'automatic' AND topic is 'basic'.
    If base decision is 'automatic' and topic is 'complex', it is restricted to 'ask'.
    If classification is 'blocked', action is blocked regardless of delegation.
    """
    if classification.is_blocked:
        return Decision("blocked", classification.reason)

    if base_decision.kind not in ("automatic", "ask"):
        return base_decision

    # If owner delegation is 'ask', it stays 'ask' (topic rule never broadens to automatic)
    if base_decision.kind == "ask":
        return base_decision

    # Base decision is 'automatic'
    if classification.is_basic:
        return Decision("automatic", classification.reason)

    # Topic is complex, mixed, unclear, or requires human review -> restrict to 'ask'
    return Decision("ask", classification.reason)
