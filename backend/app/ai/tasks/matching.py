"""Text matching shared by the fake task implementations (deterministic, tr and en)."""

import re
from collections.abc import Sequence
from typing import Protocol

from app.knowledge.claims import fold


class Labelled(Protocol):
    @property
    def label(self) -> str: ...


AMOUNT = re.compile(
    r"(?<![\w.,])(?:[₺€$]\s*)?\d+(?:[.,\s]\d+)*"
    r"(?:\s*(?:bin|k|milyon|thousand|million)(?![a-z]))?"
    r"(?:\s*(?:₺|€|\$|tl|try|lira|eur|euro|usd|dolar|dollars?)(?![a-z]))?"
)
CURRENCY_MARK = re.compile(r"[₺€$]|(?<![a-z])(?:tl|try|lira|eur|euro|usd|dolar|dollars?)(?![a-z])")
PHONE = re.compile(r"\+?\d[\d\s().-]{8,}\d")
EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")


def tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", fold(text)))


def match_facts[E: Labelled](text: str, entries: Sequence[E]) -> list[E]:
    """The best-matching entries by label words: most matched words first, then the larger
    share of the label. Returns every entry tied for the best score (empty if none matches)."""
    words = tokens(text)
    scored: list[tuple[tuple[int, float], E]] = []
    for entry in entries:
        label = tokens(entry.label)
        matched = len(label & words)
        if matched:
            scored.append(((matched, matched / len(label)), entry))
    if not scored:
        return []
    best = max(score for score, _ in scored)
    return [entry for score, entry in scored if score == best]


def amount_text(text: str) -> str | None:
    """The amount as typed: the last one, preferring ones with a currency mark."""
    folded = fold(text)
    found = [m for m in AMOUNT.finditer(folded) if m.group().strip()]
    if not found:
        return None
    with_currency = [m for m in found if CURRENCY_MARK.search(m.group())]
    chosen = (with_currency or found)[-1]
    return text[chosen.start() : chosen.end()].strip()
