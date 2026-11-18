"""Deterministic escalation signals (workflows.md §C.1, rules R5 and R6).

The model's own flags and these keyword flags are **unioned**: no model output can remove a
reason (INV-04). Matching is on folded text (case and diacritics) with word starts, so Turkish
suffixes are covered ("iade", "iadesi", "iade etmek") without matching inside other words.
"""

import re

from app.knowledge.claims import fold, strip_directional_marks
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
        (
            r"sakatlan|yaralan|\bkaza\b|ambulans|hastane|\binjur|\baccident|\bhospital"
            r"|emergency|\bacil\b"
        ),
    ),
    "abusive": re.compile(
        r"\baptal|\bsalak|\bgerizekali|\bkufur|\bidiot|\bstupid|shut up|\bfuck|\bbitch"
    ),
    "personal_data": re.compile(
        r"tc kimlik|kimlik numara|kredi kart|\biban\b|kart numara|card number|credit card"
        r"|passport|social security|pasaport"
    ),
}


# Unicode word starts after the shared length-preserving fold.
_REPLY_PATTERNS = {
    "complaint": (
        r"beschwerde|beschweren|schlechter service|жалоб|плохой сервис"
        r"|недоволен|شكوي|شكوى|خدمة سيئة|غير راض"
    ),
    "refund": (
        r"erstattung|ruckerstattung|geld zuruck|возврат|верните деньги"
        r"|вернуть деньги|استرداد|اريد اموالي|اعادة المال"
    ),
    "discount": r"rabatt|ermasigung|скидк|дешевле|خصم|تخفيض",
    "legal": r"anwalt|klage|verklag|юрист|адвокат|суд|محامي|دعوي|دعوى|مقاضاة",
    "health_safety": (
        r"unfall|krankenhaus|notfall|травм|больниц|скорая|حادث|مستشفي|(?:بال|ال)?طوارئ"
    ),
    "abusive": r"arschloch|scheis|dummkopf|идиот|дурак|заткнись|احمق|غبي|اخرس",
    "personal_data": (
        r"kreditkarte|reisepass|kartennummer|кредитн|паспорт"
        r"|номер карты|بطاقة ائتمان|جواز سفر|رقم البطاقة"
    ),
}
# Arabic attaches particles to the next word ("بمحامي" = with a lawyer, "للاسترداد" = for a
# refund): one conjunction/preposition letter and the article may precede a keyword.
_AR_PROCLITICS = r"(?:[وفبلك]?(?:ال)?|لل)"
for _flag, _pattern in _REPLY_PATTERNS.items():
    _PATTERNS[_flag] = re.compile(
        _PATTERNS[_flag].pattern + r"|(?<![^\W\d_])" + _AR_PROCLITICS + "(?:" + _pattern + ")"
    )


def keyword_flags(text: str) -> set[str]:
    """The flags the customer's words raise on their own."""
    folded = fold(strip_directional_marks(text))
    return {flag for flag, pattern in _PATTERNS.items() if pattern.search(folded)}


def matches_escalation_keywords(text: str, keywords: list[str]) -> bool:
    """The workspace's own words (fact ``escalation.keywords``), matched as substrings of the
    Turkish-case-folded text so that suffixes still match ("avukat" in "avukatıma")."""
    haystack = tr_casefold(text)
    return any(tr_casefold(k).strip() and tr_casefold(k).strip() in haystack for k in keywords)
