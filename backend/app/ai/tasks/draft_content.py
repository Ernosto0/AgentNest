"""Task ``draft_content`` (agent-runtime.md §5): task definition plus its deterministic fake.

The model PROPOSES a title, a caption template (feed) or overlay text suggestions (story), the
concept of the picture and hashtags. It never publishes and cannot loosen anything: whatever it
declares in ``commercial_claims`` can only add an issue to the draft, never remove one (INV-04).
Every price, hour, contact, URL or promotion in the text comes from a placeholder that code
renders from verified facts and then checks with the claim validator (INV-02); the owner reviews
the result before anything is submitted.

The fake recognises tr and en keywords in the objective, so the whole pipeline runs offline in
the demo, in CI and in the evals.
"""

import re
from collections.abc import Sequence
from typing import Any

from app.ai.prompt import data_section, json_section
from app.ai.runner import TaskDefinition
from app.ai.schemas import (
    MAX_CAPTION_TEMPLATE_CHARS,
    MAX_HASHTAGS,
    MAX_OVERLAY_SUGGESTIONS,
    MAX_OVERLAY_TEMPLATE_CHARS,
    MAX_TITLE_CHARS,
    MAX_VISUAL_NOTES_CHARS,
    ContentProposal,
    DraftContentInput,
    DraftFact,
)
from app.ai.tasks.matching import match_facts, match_price_facts
from app.integrations.llm.base import LLMMessage
from app.integrations.llm.fake import fake_implementation
from app.knowledge.claims import fold
from app.knowledge.render import placeholder_keys

TASK = "draft_content"
HASHTAG = re.compile(r"#?[^\W\d]+")  # letters only: a digit would be a number the validator flags


def build_messages(task_input: DraftContentInput) -> list[LLMMessage]:
    parameters = {
        "content_type": task_input.content_type,
        "language": task_input.language,
        "caption_max_chars": MAX_CAPTION_TEMPLATE_CHARS,
        "max_hashtags": MAX_HASHTAGS,
    }
    sections = [
        json_section("task_parameters", parameters),
        json_section("business_facts", [f.model_dump() for f in task_input.facts]),
        json_section("brand_voice", {"guidelines": task_input.brand_voice or ""}),
        data_section("owner_objective", task_input.objective),
    ]
    if task_input.notes:
        sections.append(data_section("owner_notes", task_input.notes))
    return [LLMMessage("user", "\n\n".join(sections))]


def clean_hashtag(raw: str) -> str | None:
    """``#Fitness`` and ``fitness`` are the same tag; anything else (spaces, digits) is dropped."""
    tag = raw.strip()
    return tag.lstrip("#") if HASHTAG.fullmatch(tag) else None


def post_validate(task_input: DraftContentInput, output: ContentProposal) -> list[str]:
    """Structure only. Which facts a template uses is checked by the renderer, and whether a
    claim is backed by the code that renders (a claim with no fact is flagged, not refused)."""
    problems: list[str] = []
    if not output.title.strip() or len(output.title) > MAX_TITLE_CHARS:
        problems.append(f"title must be 1 to {MAX_TITLE_CHARS} characters")
    if len(output.visual_notes) > MAX_VISUAL_NOTES_CHARS:
        problems.append(f"visual_notes must be at most {MAX_VISUAL_NOTES_CHARS} characters")
    if task_input.content_type == "feed_image":
        template = output.caption_template
        if template is None or not template.strip():
            problems.append("a feed_image needs a caption_template")
        elif len(template) > MAX_CAPTION_TEMPLATE_CHARS:
            problems.append(f"caption_template must be at most {MAX_CAPTION_TEMPLATE_CHARS} chars")
        if output.overlay_text_suggestions:
            problems.append("overlay_text_suggestions must be empty for a feed_image")
    else:
        if output.caption_template is not None and output.caption_template.strip():
            problems.append("a story_image is published without a caption: caption_template null")
        suggestions = output.overlay_text_suggestions
        if not 1 <= len(suggestions) <= MAX_OVERLAY_SUGGESTIONS:
            problems.append(f"give 1 to {MAX_OVERLAY_SUGGESTIONS} overlay_text_suggestions")
        if any(not s.strip() or len(s) > MAX_OVERLAY_TEMPLATE_CHARS for s in suggestions):
            problems.append(f"each suggestion must be 1 to {MAX_OVERLAY_TEMPLATE_CHARS} chars")
    if len(output.hashtags) > MAX_HASHTAGS:
        problems.append(f"hashtags must have at most {MAX_HASHTAGS} entries")
    offered = {f.key for f in task_input.facts}
    for key in output.used_fact_keys:
        if key not in offered:
            problems.append(f"used_fact_keys: {key} is not one of the provided facts")
    for claim in output.commercial_claims:
        if claim.fact_key is not None and claim.fact_key not in output.used_fact_keys:
            problems.append(f"commercial claim '{claim.claim[:40]}': fact_key is not a used fact")
    return problems


DRAFT_CONTENT: TaskDefinition[DraftContentInput, ContentProposal] = TaskDefinition(
    name=TASK,
    prompt_version="v2",  # v2: sector-neutral example key (ADR-023)
    output_schema=ContentProposal,
    max_output_tokens=1500,
    timeout_s=45,
    build_messages=build_messages,
    post_validate=post_validate,
    # No snapshot of its own: the endpoint stored the redacted brief on the queued run, which
    # the job reads back and the runner keeps (the same arrangement as extract_fact_candidates).
)

# --- the fake -------------------------------------------------------------------------------

PROMOTION = re.compile(r"deneme|trial|kampanya|promosyon|promotion|\bpromo\b")
DISCOUNT = re.compile(
    r"indirim|discount|yuzde\s*\d+|%\s*\d+|\d+\s*%|\bsale\b|bedava|ucretsiz|\bfree\b"
)
AMOUNT = re.compile(r"%\s*\d+|\d+\s*%|yuzde\s*\d+|\d+\s*percent")
PRICING = re.compile(r"fiyat|ucret|uyelik|membership|\bprice|paket|package|aylik|monthly")
HOURS = re.compile(r"\bsaat|acik|calisma|opening|\bhours\b|\bopen\b")

HASHTAGS = {
    "tr": ["yerelişletme", "küçükişletme", "instagram"],
    "en": ["smallbusiness", "shoplocal", "localbusiness"],
}
CALL = {"tr": "Detaylar için bize yazın.", "en": "Message us for details."}
TEXT: dict[str, dict[str, Any]] = {
    "tr": {
        "promo_title": "Kampanya duyurusu",
        "promo_feed": "Özel bir duyurumuz var! {ph}\n{call}",
        "promo_none": "Kampanyalarımız hakkında bilgi almak için bize yazın.",
        "promo_story": ["{ph}", "Detaylar için bize yazın"],
        "discount_title": "İndirim duyurusu",
        "discount_feed": "Hafta sonuna özel {amount} fırsatı!\n{call}",
        "discount_amount": "{amount} indirim",
        "discount_plain": "büyük indirim",
        "discount_story": ["{amount}!", "Fırsatı kaçırmayın"],
        "price_title": "Fiyat bilgisi",
        "price_feed": "{label}: {ph}\nDetaylı bilgi için bize yazın!",
        "price_policy": "Fiyat ve seçeneklerimiz hakkında: {ph}",
        "price_none": "Fiyat seçeneklerimiz için bize yazın.",
        "price_story": ["{label}", "{ph}"],
        "hours_title": "Çalışma saatleri",
        "hours_feed": "Çalışma saatlerimiz: {ph}\nSizi bekliyoruz!",
        "hours_none": "Sizi bekliyoruz! Detaylar için bize yazın.",
        "hours_story": ["Çalışma saatlerimiz için", "bize yazın"],
        "generic_title": "Haftalık paylaşım",
        "generic_feed": "Bu hafta sizi bekliyoruz! {call}",
        "generic_story": ["Bu hafta sizi bekliyoruz", "Bize yazın"],
        "notes": "Sıcak, aydınlık bir kare; {topic} öne çıksın.",
    },
    "en": {
        "promo_title": "Special offer announcement",
        "promo_feed": "Special announcement! {ph}\n{call}",
        "promo_none": "Message us to ask about our offers.",
        "promo_story": ["{ph}", "Message us for details"],
        "discount_title": "Discount announcement",
        "discount_feed": "A weekend special: {amount}!\n{call}",
        "discount_amount": "{amount} discount",
        "discount_plain": "a big discount",
        "discount_story": ["{amount}!", "Don't miss it"],
        "price_title": "Our prices",
        "price_feed": "{label}: {ph}\nMessage us to learn more!",
        "price_policy": "About our pricing options: {ph}",
        "price_none": "Message us about our options.",
        "price_story": ["{label}", "{ph}"],
        "hours_title": "Opening hours",
        "hours_feed": "Our opening hours: {ph}\nSee you there!",
        "hours_none": "See you there! Message us for details.",
        "hours_story": ["Ask us for our hours", "Message us"],
        "generic_title": "Weekly post",
        "generic_feed": "We are looking forward to seeing you this week! {call}",
        "generic_story": ["See you this week", "Message us"],
        "notes": "A warm, bright shot; let {topic} stand out.",
    },
}


def _get(facts: Sequence[DraftFact], key: str) -> DraftFact | None:
    return next((f for f in facts if f.key == key), None)


def _proposal(
    task_input: DraftContentInput,
    title: str,
    topic: str,
    *,
    feed: str | None,
    story: Sequence[str] = (),
    claims: Sequence[dict[str, Any]] = (),
) -> ContentProposal:
    strings = TEXT[_lang(task_input)]
    is_feed = task_input.content_type == "feed_image"
    templates = [feed] if is_feed and feed else list(story)
    used: dict[str, None] = {}
    for template in templates:
        for key in placeholder_keys(template):
            used.setdefault(key)
    return ContentProposal.model_validate(
        {
            "title": title,
            "caption_template": feed if is_feed else None,
            "overlay_text_suggestions": [] if is_feed else list(story),
            "visual_notes": strings["notes"].format(topic=topic),
            "hashtags": HASHTAGS[_lang(task_input)],
            "used_fact_keys": list(used),
            "commercial_claims": list(claims),
        }
    )


def _lang(task_input: DraftContentInput) -> str:
    return task_input.language if task_input.language in TEXT else "en"


@fake_implementation(TASK)
def fake_draft_content(task_input: DraftContentInput, schema: Any = None) -> ContentProposal:
    lang = _lang(task_input)
    strings = TEXT[lang]
    call = CALL[lang]
    facts = task_input.facts
    own_words = f"{task_input.objective} {task_input.notes or ''}"
    folded = fold(own_words)

    if PROMOTION.search(folded):
        promos = [f for f in facts if f.key.startswith("promotion.")]
        if not promos:  # nothing verified to promise: the post makes no promise
            return _proposal(
                task_input,
                strings["promo_title"],
                strings["promo_title"],
                feed=strings["promo_none"],
            )
        promo = (match_facts(folded, promos) or promos)[0]
        return _proposal(
            task_input,
            strings["promo_title"],
            promo.label,
            feed=strings["promo_feed"].format(ph=promo.placeholder, call=call),
            story=[s.format(ph=promo.placeholder) for s in strings["promo_story"]],
            claims=[{"claim": promo.label, "fact_key": promo.key}],
        )

    if DISCOUNT.search(folded):
        # The owner asked for a discount no fact backs. A careless model would write it anyway;
        # the validator and the claim list are what stop it from reaching a customer.
        found = AMOUNT.search(folded)
        amount = own_words[found.start() : found.end()].strip() if found else None
        shown = (
            strings["discount_amount"].format(amount=amount)
            if amount
            else strings["discount_plain"]
        )
        return _proposal(
            task_input,
            strings["discount_title"],
            shown,
            feed=strings["discount_feed"].format(amount=shown, call=call),
            story=[s.format(amount=shown) for s in strings["discount_story"]],
            claims=[{"claim": shown, "fact_key": None}],
        )

    if PRICING.search(folded):
        prices = [f for f in facts if f.key.startswith("pricing.")]
        is_specific, matched = match_price_facts(folded, prices)
        chosen = (
            (matched[0] if matched else None) if is_specific else (prices[0] if prices else None)
        )
        if chosen is not None:
            return _proposal(
                task_input,
                strings["price_title"],
                chosen.label,
                feed=strings["price_feed"].format(label=chosen.label, ph=chosen.placeholder),
                story=[
                    s.format(label=chosen.label, ph=chosen.placeholder)
                    for s in strings["price_story"]
                ],
            )
        policy = _get(facts, "policy.price_answer_text")
        feed = (
            strings["price_policy"].format(ph=policy.placeholder)
            if policy is not None
            else strings["price_none"]
        )
        return _proposal(
            task_input,
            strings["price_title"],
            strings["price_title"],
            feed=feed,
            story=[feed],
        )

    if HOURS.search(folded):
        hours = _get(facts, "hours.weekly")
        if hours is not None:
            return _proposal(
                task_input,
                strings["hours_title"],
                hours.label,
                feed=strings["hours_feed"].format(ph=hours.placeholder),
                story=[s.format(ph=hours.placeholder) for s in strings["hours_story"]],
            )
        return _proposal(
            task_input,
            strings["hours_title"],
            strings["hours_title"],
            feed=strings["hours_none"],
            story=[strings["hours_none"]],
        )

    return _proposal(
        task_input,
        strings["generic_title"],
        strings["generic_title"],
        feed=strings["generic_feed"].format(call=call),
        story=strings["generic_story"],
    )
