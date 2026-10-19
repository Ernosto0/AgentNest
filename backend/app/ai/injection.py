"""Deterministic prompt-injection heuristics (agent-runtime.md §7, INV-03).

A match is a **signal** that escalates (``injection_suspected``). Containment does not depend
on it: tasks have no tools, critical values come only from placeholders, and approvals are
required by default. Patterns are Turkish and English and are matched on a Turkish-aware
case-folded, diacritic-insensitive form so ``ÖNCEKİ``, ``onceki`` and ``önceki`` all match.
"""

import re

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

# Unusually long input that is mostly markup is a signal too.
_MARKUP_RATIO = 0.3
_MARKUP_MIN_CHARS = 400


def detect_injection(text: str) -> list[str]:
    """Return the codes of the heuristics that match ``text`` (empty when none do)."""
    folded = ascii_fold(text)
    hits = [code for code, pattern in _PATTERNS if pattern.search(folded)]
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
