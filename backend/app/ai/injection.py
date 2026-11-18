"""Deterministic prompt-injection heuristics (agent-runtime.md §7, INV-03).

A match is a **signal** that escalates (``injection_suspected``). Containment does not depend
on it: tasks have no tools, critical values come only from placeholders, and approvals are
required by default. Patterns are Turkish and English, plus Russian, German and Arabic (F-11),
and are matched on a Turkish-aware case-folded, diacritic-insensitive form so ``ÖNCEKİ``,
``onceki`` and ``önceki`` all match. The Russian, German and Arabic patterns run on the
reply-language fold (``knowledge.claims.fold``: umlauts, ``ё``, Arabic alef forms) with
direction marks, zero-width characters and Arabic vocalisation removed.
"""

import re

from app.knowledge.claims import fold, strip_directional_marks
from app.knowledge.parsing import ascii_fold

# (code, pattern) on ascii_fold(text): lower case, no Turkish diacritics.
_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = tuple(
    (code, re.compile(pattern))
    for code, pattern in (
        (
            "ignore_previous_en",
            r"\bignore\s+(all\s+|any\s+|the\s+)?(previous|prior|above|earlier)\b",
        ),
        (
            "disregard_en",
            r"\b(disregard|forget)\s+(all\s+|any\s+|the\s+)?(previous|prior|above|your)\b",
        ),
        (
            "ignore_previous_tr",
            r"\b(onceki|yukaridaki|tum)\s+(tum\s+)?(talimat|komut|kural|yonerge)",
        ),
        ("forget_tr", r"\b(talimat|kural|yonerge)\w*\s+(unut|yoksay|dikkate\s+alma)"),
        ("system_prompt", r"\bsystem\s*prompt\b|\bsistem\s*(istem|mesaj|prompt)"),
        ("you_are_now", r"\byou\s+are\s+now\b|\bartik\s+sen\b|\bsen\s+artik\b"),
        (
            "developer_mode",
            r"\bdeveloper\s+mode\b|\bgelistirici\s+modu\b|\bjailbreak\b|\bdan\s+mode\b",
        ),
        ("role_marker", r"^\s*(system|assistant|developer)\s*:|<\s*/?\s*(system|assistant)\s*>"),
        ("placeholder_smuggling", r"\{\{\s*fact\s*:"),
        (
            "reveal_instructions",
            r"\b(reveal|show|print|repeat)\b.{0,30}\b(instructions|prompt|rules)\b",
        ),
    )
)

# (code, pattern) on fold(strip_directional_marks(text)): Russian, German and Arabic.
_REPLY_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = tuple(
    (code, re.compile(pattern))
    for code, pattern in (
        (
            "ignore_previous_ru",
            r"\b(?:игнорируй|игнорировать|забудь|забыть|не\s+учитывай)\s+"
            r"(?:все\s+|любые\s+|свои\s+)?"
            r"(?:предыдущ|прежн|прошл|выше|инструкци|правил|указани)",
        ),
        (
            "previous_instructions_ru",
            r"\b(?:предыдущ|прежн)\w*\s+(?:инструкци|указани|правил|команд)",
        ),
        ("system_prompt_ru", r"\bсистемн\w*\s+(?:промпт|подсказк|инструкци|сообщени)"),
        ("you_are_now_ru", r"\bтеперь\s+ты\b|\bты\s+теперь\b"),
        ("developer_mode_ru", r"\bрежим\s+разработчика\b|\bджейлбрейк\b"),
        (
            "reveal_instructions_ru",
            r"\b(?:покажи|раскрой|выведи|повтори|напиши)\b.{0,30}\b(?:инструкци|промпт|правил)",
        ),
        (
            "ignore_previous_de",
            r"\b(?:ignorier\w*|vergiss|vergessen\s+sie|missachte)\s+"
            r"(?:alle\s+|deine\s+|die\s+|ihre\s+|samtliche\s+)?"
            r"(?:vorherig|bisherig|fruher|obig|anweisung|instruktion|regeln|vorgaben)",
        ),
        (
            "previous_instructions_de",
            r"\b(?:vorherig|bisherig|fruher)\w*\s+(?:anweisung|instruktion|regel)",
        ),
        ("system_prompt_de", r"\bsystem\s*-?\s*(?:prompt|anweisung|nachricht)"),
        ("you_are_now_de", r"\bdu\s+bist\s+(?:jetzt|nun|ab\s+sofort)\b"),
        ("developer_mode_de", r"\bentwickler\s*-?\s*modus\b|\bjailbreak\b"),
        (
            "reveal_instructions_de",
            r"\b(?:zeig|zeige|nenne|verrate|gib|wiederhole)\b.{0,30}"
            r"\b(?:anweisung|prompt|regeln)",
        ),
        (
            "ignore_previous_ar",
            r"(?:تجاهل|تجاهلي|انس|انسي|اهمل)\s+(?:كل\s+|جميع\s+)?"
            r"(?:ال)?(?:تعليمات|اوامر|قواعد|ارشادات|سابق)",
        ),
        ("previous_instructions_ar", r"(?:ال)?(?:تعليمات|اوامر|قواعد)\s+(?:ال)?سابق"),
        ("system_prompt_ar", r"(?:موجه|تعليمات|رسالة|امر)\s+النظام|\bsystem\s*prompt\b"),
        ("you_are_now_ar", r"\bانت\s+الان\b|\bالان\s+انت\b"),
        ("developer_mode_ar", r"\bوضع\s+(?:ال)?(?:مطور|مبرمج)\b"),
        (
            "reveal_instructions_ar",
            r"(?:اظهر|اعرض|اكشف|اطبع|كرر)\S*\s.{0,30}(?:تعليمات|قواعد|الموجه)",
        ),
    )
)

# Unusually long input that is mostly markup is a signal too.
_MARKUP_RATIO = 0.3
_MARKUP_MIN_CHARS = 400


def detect_injection(text: str) -> list[str]:
    """Return the codes of the heuristics that match ``text`` (empty when none do)."""
    # Direction marks and zero-width characters inside a phrase must not hide it.
    plain = strip_directional_marks(text)
    folded = ascii_fold(plain)
    hits = [code for code, pattern in _PATTERNS if pattern.search(folded)]
    reply_folded = fold(plain)
    hits += [code for code, pattern in _REPLY_PATTERNS if pattern.search(reply_folded)]
    if len(text) >= _MARKUP_MIN_CHARS:
        markup = sum(text.count(ch) for ch in "<>{}[]|`")
        if markup / len(text) >= _MARKUP_RATIO:
            hits.append("markup_heavy")
    return hits


def neutralise_untrusted(text: str) -> str:
    """Make third-party text safe to place inside a labelled data section.

    Angle brackets are replaced so the text cannot close a section or open a fake one, and
    ``{{fact:`` is broken so a template token cannot be smuggled into model output.
    """
    return text.replace("<", "‹").replace(">", "›").replace("{{", "{ {").replace("}}", "} }")
