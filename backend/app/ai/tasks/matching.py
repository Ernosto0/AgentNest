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


_PRICE_STOP_WORD_TEXT = (
    "fiyat fiyati fiyata fiyatlar fiyatlari fiyatlarimiz fiyatlariniz fiyatini "
    "ucret ucreti ucretler ucretleri ucretimiz ucretiniz "
    "nedir ne kadar kac kaca kacadir "
    "tl try lira eur euro usd dolar dollars "
    "price prices pricing cost costs costing fee fees rate rates "
    "how much is are the a an your what about options "
    "bilgi bilgisi almak istiyorum verebilir misiniz alabilir miyim "
    "paylas paylasir paylasin paylasiniz share tell me "
    "duyur duyuru duyurusu duyurur musunuz announce announcement "
    "hakkinda ogrenebilir ogrenmek var mi mu "
    "information info please can you give would like to know "
    "paket paketi paketini package packages "
    "merhaba selam gunaydin iyi gunler aksamlar hello hi hey good morning evening thanks "
    "tesekkurler tesekkur ederim lutfen bir one acaba bana bize"
)
PRICE_STOP_WORDS = frozenset(_PRICE_STOP_WORD_TEXT.split())


def _word_match(w1: str, w2: str) -> bool:
    if w1 == w2:
        return True
    return len(w1) >= 4 and len(w2) >= 4 and (w1.startswith(w2) or w2.startswith(w1))


def match_price_facts[E: Labelled](text: str, entries: Sequence[E]) -> tuple[bool, list[E]]:
    """Match entries for a pricing question or objective.

    Returns (is_specific, matches):
    - is_specific: True if the query named specific product words (beyond generic price words).
    - matches: The matched entries, sorted with best matches first.
    """
    q_tokens = tokens(text) - PRICE_STOP_WORDS
    if not q_tokens:
        return False, list(entries)

    q_digits = {w for w in q_tokens if any(ch.isdigit() for ch in w)}

    scored: list[tuple[float, E]] = []
    for entry in entries:
        l_tokens = tokens(entry.label) - PRICE_STOP_WORDS
        k_tokens = (
            tokens(getattr(entry, "key", "").removeprefix("pricing.")) - PRICE_STOP_WORDS
            if hasattr(entry, "key")
            else set()
        )
        cand_tokens = l_tokens | k_tokens
        if not cand_tokens:
            continue
        digits = {w for w in cand_tokens if any(ch.isdigit() for ch in w)}
        if q_digits != digits:
            continue

        matched_q = {qw for qw in q_tokens if any(_word_match(qw, cw) for cw in cand_tokens)}
        if len(matched_q) != len(q_tokens):
            continue

        matched_c = {cw for cw in cand_tokens if any(_word_match(qw, cw) for qw in q_tokens)}
        score = len(matched_c) / len(cand_tokens)
        scored.append((score, entry))

    if not scored:
        return True, []

    scored.sort(key=lambda item: item[0], reverse=True)
    best_score = scored[0][0]
    best_entries = [entry for score, entry in scored if score == best_score]
    return True, best_entries


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
