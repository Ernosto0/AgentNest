"""Deterministic escalation signals (workflows.md §C.1, rules R5 and R6).

The model's own flags and these keyword flags are **unioned**: no model output can remove a
reason (INV-04). Matching is on folded text (case and diacritics) with word starts, so Turkish
suffixes are covered ("iade", "iadesi", "iade etmek") without matching inside other words.
"""

import re

from app.knowledge.claims import fold
from app.knowledge.parsing import tr_casefold

# flag -> regex over folded text
_PATTERNS: dict[str, re.Pattern[str]] = {
    "complaint": re.compile(
        r"\bsikayet|\brezalet|\bberbat|memnun degil|memnuniyetsiz|\bkaba|\bsaygisiz|kotu hizmet"
        r"|\bcomplain|\bterrible|\bawful|\brude\b|unacceptable|disgusting|\bscam\b|dolandir"
    ),
    "refund": re.compile(
        r"\biade|paramin? geri|para iadesi|geri odeme|\brefund|money back|chargeback"
    ),
    "discount": re.compile(
        r"\bindirim|ucuz yap|pazarlik|\bkupon|kampanya kodu|\bdiscount|\bcoupon|cheaper|promo code"
    ),
    "legal": re.compile(
        r"\bavukat|\bdava\b|\bdavac|mahkeme|\bhukuk|tuketici hakem|savci|\blawyer|\blawsuit"
        r"|legal action|\bsue\b|\bcourt\b"
    ),
    "health_safety": re.compile(
        r"sakatlan|yaralan|\bkaza\b|ambulans|hastane|\binjur|\baccident|\bhospital|emergency|\bacil\b"
    ),
    "abusive": re.compile(
        r"\baptal|\bsalak|\bgerizekali|\bkufur|\bidiot|\bstupid|shut up|\bfuck|\bbitch"
    ),
    "personal_data": re.compile(
        r"tc kimlik|kimlik numara|kredi kart|\biban\b|kart numara|card number|credit card"
        r"|passport|social security|pasaport"
    ),
}


def keyword_flags(text: str) -> set[str]:
    """The flags the customer's words raise on their own."""
    folded = fold(text)
    return {flag for flag, pattern in _PATTERNS.items() if pattern.search(folded)}


def matches_escalation_keywords(text: str, keywords: list[str]) -> bool:
    """The workspace's own words (fact ``escalation.keywords``), matched as substrings of the
    Turkish-case-folded text so that suffixes still match ("avukat" in "avukatıma")."""
    haystack = tr_casefold(text)
    return any(tr_casefold(k).strip() and tr_casefold(k).strip() in haystack for k in keywords)
