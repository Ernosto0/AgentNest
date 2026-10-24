"""Task ``draft_reply`` (agent-runtime.md §4): task definition plus its deterministic fake.

The model classifies the customer's unanswered messages and PROPOSES a reply template made of
free text and ``{{fact:key}}`` placeholders. It never sends, never sees other customers, and
cannot loosen anything: flags and ``needs_human`` only escalate (INV-04). Every value in the
reply comes from a placeholder that code renders from verified facts and then checks with the
claim validator (INV-02).

The fake recognises tr and en keywords and answers from the facts it is given, so the whole
pipeline runs offline in the demo, in CI and in the evals.
"""

import re
from collections.abc import Sequence
from typing import Any

from app.ai.prompt import json_section, untrusted_section
from app.ai.runner import TaskDefinition
from app.ai.schemas import (
    MAX_TEMPLATE_BYTES,
    DraftApprovedAnswer,
    DraftFact,
    DraftReplyInput,
    ReplyProposal,
)
from app.ai.tasks.matching import match_facts, match_price_facts, tokens
from app.integrations.llm.base import LLMMessage
from app.integrations.llm.fake import fake_implementation
from app.knowledge.claims import fold
from app.knowledge.render import placeholder_keys

TASK = "draft_reply"
LANGUAGES = ("tr", "en")


def build_messages(task_input: DraftReplyInput) -> list[LLMMessage]:
    parameters = {
        "reply_language": task_input.reply_language,
        "price_disclosure": task_input.price_disclosure,
    }
    sections = [
        json_section("task_parameters", parameters),
        json_section("business_facts", [f.model_dump() for f in task_input.facts]),
        json_section("approved_answers", [a.model_dump() for a in task_input.approved_answers]),
        json_section("brand_voice", {"guidelines": task_input.brand_voice or ""}),
    ]
    if task_input.validator_feedback:
        sections.append(json_section("validator_feedback", task_input.validator_feedback))
    conversation = "\n".join(f"{m.role}: {m.text}" for m in task_input.conversation)
    sections.append(untrusted_section("untrusted_customer_messages", conversation))
    return [LLMMessage("user", "\n\n".join(sections))]


def post_validate(task_input: DraftReplyInput, output: ReplyProposal) -> list[str]:
    """Structure only. Which facts a template uses is checked by the renderer, which gives a
    wrong key one regeneration with feedback and the reason ``FACT_NOT_USABLE``."""
    problems: list[str] = []
    if output.language != task_input.reply_language:
        problems.append("language must equal reply_language")
    if output.approved_answer_id is not None and output.approved_answer_id not in {
        a.id for a in task_input.approved_answers
    }:
        problems.append("approved_answer_id is not one of the provided approved answers")
    if output.reply_template is not None:
        if len(output.reply_template.encode("utf-8")) > MAX_TEMPLATE_BYTES:
            problems.append(f"reply_template must be at most {MAX_TEMPLATE_BYTES} bytes")
        if output.approved_answer_id is not None:
            problems.append("reply_template must be empty when approved_answer_id is set")
    return problems


def snapshot(task_input: DraftReplyInput) -> dict[str, Any]:
    """What `agent_runs` keeps: counts and keys, never the customer's words."""
    return {
        "reply_language": task_input.reply_language,
        "price_disclosure": task_input.price_disclosure,
        "fact_keys": [f.key for f in task_input.facts],
        "approved_answer_ids": [a.id for a in task_input.approved_answers],
        "message_count": len(task_input.conversation),
        "regeneration": bool(task_input.validator_feedback),
    }


DRAFT_REPLY: TaskDefinition[DraftReplyInput, ReplyProposal] = TaskDefinition(
    name=TASK,
    prompt_version="v2",  # v2: sector-neutral example key (ADR-023)
    output_schema=ReplyProposal,
    max_output_tokens=800,
    timeout_s=30,
    build_messages=build_messages,
    post_validate=post_validate,
    snapshot=snapshot,
)

# --- the fake -------------------------------------------------------------------------------

COMPLAINT = re.compile(
    r"sikayet|rezalet|berbat|memnun degil|memnuniyetsiz|\bkaba|saygisiz|kotu hizmet"
    r"|complain|terrible|awful|\brude\b|unacceptable|disgusting"
)
REFUND = re.compile(r"\biade|paramin? geri|para iadesi|geri odeme|refund|money back")
DISCOUNT = re.compile(r"indirim|ucuz yap|pazarlik|kupon|discount|coupon|cheaper|promo code")
LEGAL = re.compile(
    r"avukat|\bdava|mahkeme|hukuk|tuketici hakem|lawyer|lawsuit|legal action|\bsue\b"
)
HEALTH = re.compile(r"sakatlan|yaralan|ambulans|hastane|injur|accident|hospital")
PROMOTION = re.compile(r"kampanya|promosyon|deneme|ucretsiz|bedava|\bfree\b|trial|promotion")
PRICING = re.compile(r"fiyat|ucret|ne kadar|kac (?:tl|para|lira)|tarife|\bprice|how much|\bcost")
HOURS = re.compile(
    r"\bsaat|acik mi|kacta|kapanis|acilis|calisma|opening|closing|\bhours\b|what time"
)
LOCATION = re.compile(r"nerede|adres|konum|yol tarifi|\bwhere\b|address|location|directions")
CONTACT = re.compile(r"telefon|numara|iletisim|whatsapp|phone|contact|call you")
BOOKING = re.compile(r"rezervasyon|randevu|kayit ol|nasil kayit|\bbook|reserv|appointment|sign up")
# Sector-neutral words only (ADR-023): a question about a particular service is recognised by
# the labels of the workspace's own ``service.*`` facts instead.
SERVICES = re.compile(
    r"hizmet|\bders|\burun|\bmenu|neler var|satiyor"
    r"|classes|services|products|\boffer|do you have|do you sell"
)
GREETING = re.compile(
    r"^(merhaba|selam|gunaydin|iyi gunler|hello|hi|hey|good (?:morning|evening))\b"
)

TEXT = {
    "tr": {
        "greeting": "Merhaba! Size nasıl yardımcı olabiliriz?",
        "price_one": "Merhaba! {label} ücretimiz {ph}.",
        "price_many": "Merhaba! Ücretlerimiz:\n{lines}",
        "hours": "Çalışma saatlerimiz: {ph}",
        "address": "Adresimiz: {ph}",
        "phone": "Telefon: {ph}",
        "email": "E-posta: {ph}",
        "line": "- {label}: {ph}",
        "plain": "{ph}",
        "services": "Hizmetlerimiz:\n{lines}",
        "promo": "Güncel kampanyamız: {ph}",
    },
    "en": {
        "greeting": "Hello! How can we help you?",
        "price_one": "Hi! Our {label} price is {ph}.",
        "price_many": "Hi! Our prices:\n{lines}",
        "hours": "Our opening hours: {ph}",
        "address": "Our address: {ph}",
        "phone": "Phone: {ph}",
        "email": "Email: {ph}",
        "line": "- {label}: {ph}",
        "plain": "{ph}",
        "services": "Our services:\n{lines}",
        "promo": "Our current offer: {ph}",
    },
}


def _recent_customer_text(task_input: DraftReplyInput) -> str:
    """The customer's messages since the business last wrote."""
    trailing: list[str] = []
    for message in reversed(task_input.conversation):
        if message.role == "business":
            break
        trailing.append(message.text)
    return " ".join(reversed(trailing))


def _by_prefix(facts: Sequence[DraftFact], prefix: str) -> list[DraftFact]:
    return [f for f in facts if f.key.startswith(prefix)]


def _get(facts: Sequence[DraftFact], key: str) -> DraftFact | None:
    return next((f for f in facts if f.key == key), None)


def _match_answer(text: str, answers: Sequence[DraftApprovedAnswer]) -> DraftApprovedAnswer | None:
    words = tokens(text)
    best: tuple[float, DraftApprovedAnswer] | None = None
    for answer in answers:
        for example in answer.example_questions:
            example_words = tokens(example)
            shared = len(words & example_words)
            if not example_words or shared < min(2, len(example_words)):
                continue
            score = shared / len(example_words)
            if score >= 0.6 and (best is None or score > best[0]):
                best = (score, answer)
    return best[1] if best else None


def _proposal(
    task_input: DraftReplyInput,
    intent: str,
    *,
    template: str | None = None,
    flags: Sequence[str] = (),
    can_answer: bool = True,
    needs_human: bool = False,
    approved_answer_id: str | None = None,
) -> ReplyProposal:
    return ReplyProposal.model_validate(
        {
            "intent": intent,
            "flags": list(flags),
            "can_answer": can_answer,
            "needs_human": needs_human,
            "approved_answer_id": approved_answer_id,
            "reply_template": template,
            "used_fact_keys": placeholder_keys(template) if template else [],
            "language": task_input.reply_language,
        }
    )


def _cannot(task_input: DraftReplyInput, intent: str, *, human: bool = False) -> ReplyProposal:
    return _proposal(task_input, intent, can_answer=False, needs_human=human)


def _price_reply(
    task_input: DraftReplyInput, folded: str, strings: dict[str, str]
) -> ReplyProposal:
    facts = task_input.facts
    if task_input.price_disclosure == "do_not_share":
        text_fact = _get(facts, "policy.price_answer_text")
        if text_fact is None:
            return _cannot(task_input, "pricing")
        return _proposal(
            task_input, "pricing", template=strings["plain"].format(ph=text_fact.placeholder)
        )
    prices = _by_prefix(facts, "pricing.")
    if not prices:
        return _cannot(task_input, "pricing")
    # The product is recognised by the labels of the workspace's own prices (ADR-023), so no
    # sector-specific key is ever assumed. Generic price words never select a product.
    is_specific, matched = match_price_facts(folded, prices)
    if is_specific and not matched:
        return _cannot(task_input, "pricing")
    chosen = matched[:3] if is_specific else prices[:3]
    if len(chosen) == 1:
        only = chosen[0]
        return _proposal(
            task_input,
            "pricing",
            template=strings["price_one"].format(label=only.label, ph=only.placeholder),
        )
    lines = "\n".join(strings["line"].format(label=f.label, ph=f.placeholder) for f in chosen)
    return _proposal(task_input, "pricing", template=strings["price_many"].format(lines=lines))


def _contact_reply(
    task_input: DraftReplyInput, folded: str, strings: dict[str, str]
) -> ReplyProposal:
    facts = task_input.facts
    wants_address = bool(LOCATION.search(folded))
    wants_contact = bool(CONTACT.search(folded))
    parts: list[str] = []
    address = _get(facts, "location.address")
    if address and (wants_address or not wants_contact):
        parts.append(strings["address"].format(ph=address.placeholder))
    if wants_contact or not wants_address:
        for key, label_key in (
            ("contact.phone", "phone"),
            ("contact.whatsapp", "phone"),
            ("contact.email", "email"),
        ):
            fact = _get(facts, key)
            if fact:
                parts.append(strings[label_key].format(ph=fact.placeholder))
                break
    if not parts:
        return _cannot(task_input, "location_contact")
    return _proposal(task_input, "location_contact", template="\n".join(parts))


def _list_reply(
    task_input: DraftReplyInput,
    folded: str,
    intent: str,
    prefix: str,
    header: str,
    strings: dict[str, str],
) -> ReplyProposal:
    candidates = _by_prefix(task_input.facts, prefix)
    if not candidates:
        return _cannot(task_input, intent)
    chosen = match_facts(folded, candidates) or candidates[:3]
    lines = "\n".join(strings["line"].format(label=f.label, ph=f.placeholder) for f in chosen[:3])
    return _proposal(task_input, intent, template=strings[header].format(lines=lines))


@fake_implementation(TASK)
def fake_draft_reply(task_input: DraftReplyInput, schema: Any = None) -> ReplyProposal:
    strings = TEXT.get(task_input.reply_language, TEXT["en"])
    text = _recent_customer_text(task_input)
    folded = fold(text)

    flags: list[str] = []
    intent = "other"
    if COMPLAINT.search(folded):
        flags.append("complaint")
        intent = "complaint"
    if REFUND.search(folded):
        flags.append("refund")
        intent = "refund_request"
    if DISCOUNT.search(folded):
        flags.append("discount")
        intent = "discount_request"
    if LEGAL.search(folded):
        flags.append("legal")
        intent = "sensitive"
    if HEALTH.search(folded):
        flags.append("health_safety")
        intent = "sensitive"
    if flags:
        return _proposal(task_input, intent, flags=flags, can_answer=False, needs_human=True)

    answer = _match_answer(text, task_input.approved_answers)
    if answer is not None:
        intent = answer.intent if answer.intent in ("faq", "greeting") else "faq"
        return _proposal(task_input, intent, approved_answer_id=answer.id)

    if PROMOTION.search(folded):
        promos = _by_prefix(task_input.facts, "promotion.")
        if not promos:
            return _cannot(task_input, "promotions")
        return _proposal(
            task_input, "promotions", template=strings["promo"].format(ph=promos[0].placeholder)
        )
    if PRICING.search(folded):
        return _price_reply(task_input, folded, strings)
    if HOURS.search(folded):
        hours = _get(task_input.facts, "hours.weekly")
        if hours is None:
            return _cannot(task_input, "hours")
        return _proposal(
            task_input, "hours", template=strings["hours"].format(ph=hours.placeholder)
        )
    if LOCATION.search(folded) or CONTACT.search(folded):
        return _contact_reply(task_input, folded, strings)
    if BOOKING.search(folded):
        booking = _get(task_input.facts, "booking.instructions")
        if booking is None:
            return _cannot(task_input, "booking")
        return _proposal(
            task_input, "booking", template=strings["plain"].format(ph=booking.placeholder)
        )
    services = _by_prefix(task_input.facts, "service.")
    if SERVICES.search(folded) or match_facts(folded, services):
        return _list_reply(task_input, folded, "services", "service.", "services", strings)
    if GREETING.search(folded) and len(folded.split()) <= 4:
        return _proposal(task_input, "greeting", template=strings["greeting"])
    faqs = _by_prefix(task_input.facts, "faq.")
    matched = match_facts(folded, faqs)
    if matched:
        return _proposal(
            task_input, "faq", template=strings["plain"].format(ph=matched[0].placeholder)
        )
    return _cannot(task_input, "other", human=True)
