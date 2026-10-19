"""Reply-language detection (workflows.md §C step 3): deterministic, no model involved.

The language of the reply is decided here and handed to the model, which may not switch
(agent-runtime.md §4). Turkish and English are recognised by their stop words and, for
Turkish, its distinctive letters. A few other languages and every non-Latin script are
recognised only so that they can be told apart: they are *unsupported* and the conversation
goes to a person (rule R4) instead of being answered in the wrong language.
"""

import re
import unicodedata
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass

from app.knowledge.parsing import tr_casefold

_STOP_WORDS: dict[str, frozenset[str]] = {
    "tr": frozenset(
        [
            "ve",
            "bir",
            "bu",
            "ne",
            "mi",
            "mı",
            "mu",
            "mü",
            "kaç",
            "var",
            "yok",
            "için",
            "nasıl",
            "merhaba",
            "selam",
            "günaydın",
            "fiyat",
            "fiyatı",
            "fiyatlar",
            "ücret",
            "ücreti",
            "saat",
            "saatleri",
            "nedir",
            "nerede",
            "adres",
            "telefon",
            "numara",
            "rezervasyon",
            "randevu",
            "üyelik",
            "aylık",
            "ders",
            "dersler",
            "teşekkürler",
            "teşekkür",
            "lütfen",
            "evet",
            "hayır",
            "olur",
            "peki",
            "çok",
            "ama",
            "ile",
            "bana",
            "size",
            "ben",
            "siz",
            "sen",
            "mısınız",
            "misiniz",
            "musunuz",
            "var",
            "mıdır",
            "acaba",
            "gibi",
            "kadar",
            "daha",
        ]
    ),
    "en": frozenset(
        [
            "the",
            "is",
            "are",
            "what",
            "how",
            "much",
            "do",
            "does",
            "you",
            "your",
            "hello",
            "hi",
            "hey",
            "price",
            "prices",
            "open",
            "close",
            "hours",
            "where",
            "can",
            "i",
            "we",
            "please",
            "thanks",
            "thank",
            "class",
            "classes",
            "membership",
            "monthly",
            "book",
            "booking",
            "and",
            "with",
            "have",
            "there",
            "it",
            "this",
            "that",
            "would",
            "like",
            "want",
            "need",
            "any",
            "about",
        ]
    ),
    "de": frozenset(
        [
            "der",
            "die",
            "das",
            "und",
            "ist",
            "ich",
            "nicht",
            "wie",
            "viel",
            "kostet",
            "hallo",
            "preis",
            "bitte",
            "danke",
            "haben",
            "sie",
            "wir",
            "mit",
            "für",
            "ein",
            "eine",
            "was",
            "wann",
            "wo",
        ]
    ),
    "fr": frozenset(
        [
            "le",
            "la",
            "les",
            "est",
            "vous",
            "je",
            "combien",
            "prix",
            "bonjour",
            "merci",
            "pour",
            "avec",
            "une",
            "des",
            "du",
            "quel",
            "quelle",
            "où",
            "horaires",
        ]
    ),
    "es": frozenset(
        [
            "el",
            "los",
            "las",
            "es",
            "usted",
            "cuánto",
            "cuanto",
            "cuesta",
            "precio",
            "hola",
            "gracias",
            "por",
            "favor",
            "una",
            "para",
            "con",
            "qué",
            "cuál",
            "dónde",
            "horario",
        ]
    ),
    "it": frozenset(
        ["ciao", "quanto", "costa", "prezzo", "grazie", "buongiorno", "favore", "il", "lo", "che"]
    ),
    "pt": frozenset(["olá", "obrigado", "quanto", "custa", "preço", "você", "uma"]),
}
# Letters that point to Turkish (ç, ö, ü are shared with German and French).
_TURKISH_LETTERS = set("ğışĞİŞ")
_WORD = re.compile(r"[^\W\d_]+")
_NON_LATIN = ("CYRILLIC", "ARABIC", "HEBREW", "GREEK", "CJK", "HIRAGANA", "KATAKANA", "HANGUL")
_NON_LATIN_MORE = ("DEVANAGARI", "THAI", "ARMENIAN", "GEORGIAN", "BENGALI", "TAMIL")

UNSUPPORTED = "other"


def _script_is_foreign(letter: str) -> bool:
    name = unicodedata.name(letter, "")
    return name.startswith(_NON_LATIN + _NON_LATIN_MORE)


def detect_language(text: str) -> str | None:
    """``"tr"``, ``"en"``, ``"other"`` (recognised but unsupported), or ``None`` when the text
    gives no evidence (emoji, numbers, "ok")."""
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return None
    foreign = sum(1 for c in letters if _script_is_foreign(c))
    if foreign * 2 >= len(letters):
        return UNSUPPORTED
    scores: Counter[str] = Counter()
    scores["tr"] += 2 * sum(1 for c in text if c in _TURKISH_LETTERS)
    for word in _WORD.findall(tr_casefold(text)):
        for language, words in _STOP_WORDS.items():
            if word in words:
                scores[language] += 1
    ranked = scores.most_common(2)
    if not ranked:
        return None
    best, best_score = ranked[0]
    runner_up = ranked[1][1] if len(ranked) > 1 else 0
    if best_score - runner_up < 1:
        return None
    return best if best in ("tr", "en") else UNSUPPORTED


@dataclass(frozen=True)
class ReplyLanguage:
    """``code`` is the language to answer in, or ``None`` when it is unsupported."""

    code: str | None
    detected: str | None  # what the text looked like: tr | en | other | None (no evidence)

    @property
    def supported(self) -> bool:
        return self.code is not None


def choose_reply_language(
    customer_texts_newest_first: Sequence[str],
    *,
    default_locale: str,
    reply_languages: Sequence[str],
) -> ReplyLanguage:
    """The first message with evidence decides (the newest wins); with no evidence at all the
    workspace default is used. A language the business does not answer in is unsupported."""
    detected: str | None = None
    for text in customer_texts_newest_first:
        detected = detect_language(text)
        if detected is not None:
            break
    if detected is None:
        fallback = default_locale if default_locale in reply_languages else None
        if fallback is None and reply_languages:
            fallback = reply_languages[0]
        return ReplyLanguage(fallback, None)
    if detected == UNSUPPORTED or detected not in reply_languages:
        return ReplyLanguage(None, detected)
    return ReplyLanguage(detected, detected)
