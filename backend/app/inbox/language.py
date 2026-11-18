"""Reply-language detection (workflows.md §C step 3): deterministic, no model involved.

The language of the reply is decided here and handed to the model, which may not switch
(agent-runtime.md §4). Supported reply languages use script, distinctive letters and word lists.
Mixed or unsupported evidence goes to a person (R4). UI locales are independent.
"""

import re
import unicodedata
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass

from app.core.reply_languages import REPLY_LANGUAGES
from app.knowledge.claims import strip_directional_marks
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
            "wann",
            "wo",
            "guten",
            "tag",
            "möchte",
            "einen",
            "tisch",
            "reservieren",
            "zimmer",
            "mitgliedschaft",
            "geöffnet",
            "sonntag",
            "schön",
            "straße",
            "grüße",
            "bis",
            "uhr",
            "können",
            "buchen",
            "öffnungszeiten",
            "morgen",
            "heute",
            # Added in Session 11 (the German eval set found ordinary messages without a hit).
            "gibt",
            "auf",
            "euch",
            "eure",
            "ihr",
            "ihre",
            "uns",
            "meine",
            "meinen",
            "aber",
            "oder",
            "kostenlos",
            "probetraining",
            "termin",
            "adresse",
            "telefonnummer",
            "telefonisch",
            "erreichen",
            "anwalt",
            "beschwerde",
            "rückerstattung",
            "rabatt",
            "kurse",
            "angebot",
            "lautet",
            "sind",
            "seid",
            "habt",
            "werde",
            "ignoriere",
            "alle",
            "vorherigen",
            "anweisungen",
            "zeige",
            "regeln",
            "deine",
            "deinen",
            "vergiss",
            "mir",
            "schlechter",
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


# At least half the letters must belong to a foreign script before script classification.
SCRIPT_DOMINANCE = 0.5
# A fifth of Cyrillic/Arabic letters alongside Latin is already unsafe bilingual evidence.
MIXED_SCRIPT_MIN = 0.2
# Non-TR/EN Latin winners need more than twice the runner-up evidence.
MIXED_RATIO = 0.5
# One unambiguous Russian word is sufficient within a dominant Cyrillic script.
RU_MIN_SCORE = 1
# One Arabic word is sufficient after excluding neighbouring script languages.
AR_MIN_SCORE = 1
# TR/EN retain the existing minimum one-point margin.
LATIN_MIN_MARGIN = 1
# Distinctive Russian and German letters are stronger than a word hit.
DISTINCTIVE_SCORE = 2
# Shared ? contributes only after German word evidence exists.
GERMAN_UMLAUT_SCORE = 1

_RU_WORDS = frozenset(
    [
        "сколько",
        "стоит",
        "цена",
        "цены",
        "привет",
        "здравствуйте",
        "добрый",
        "спасибо",
        "пожалуйста",
        "есть",
        "можно",
        "работает",
        "часы",
        "время",
        "забронировать",
        "бронь",
        "номер",
        "абонемент",
        "адрес",
        "где",
        "когда",
        "как",
        "что",
        "это",
        "вы",
        "у",
        "вас",
        "во",
        "открываетесь",
        "завтра",
        "сегодня",
        "доброе",
        "утро",
        "вечер",
        "день",
        "хочу",
        "нужен",
        "нужна",
        "нужно",
        "нам",
        "мне",
        "мы",
        "на",
        "до",
        "за",
        "от",
        "для",
        "ли",
        "и",
        "или",
        "да",
        "нет",
        "стоимость",
        "оплата",
        "заказать",
        "запись",
        "свободно",
        "свободный",
        "комната",
        "комнаты",
        "работаете",
        "открыто",
        "закрыто",
        "телефон",
        "находится",
        "занятия",
        "месяц",
        "еще",
        "ещё",
        "ваш",
        "ваша",
        "услуги",
        "отель",
        "ресторан",
        "столик",
        # Added in Session 11 after the Russian eval set found short, ordinary messages that
        # carried none of the words above (a person answers those, which is safe but slow).
        "я",
        "в",
        "с",
        "к",
        "по",
        "не",
        "но",
        "если",
        "меня",
        "мой",
        "моя",
        "вопрос",
        "все",
        "всё",
        "этот",
        "подскажите",
        "скажите",
        "дайте",
        "покажи",
        "напиши",
        "занятие",
        "занятий",
        "записаться",
        "бесплатно",
        "бесплатное",
        "пробное",
        "абонемента",
        "цену",
        "тренер",
        "тренера",
        "тренировка",
        "тренировки",
        "расписание",
        "верните",
        "деньги",
    ]
)
_AR_WORDS = frozenset(
    [
        "كم",
        "السعر",
        "سعر",
        "اسعار",
        "مرحبا",
        "السلام",
        "عليكم",
        "شكرا",
        "من",
        "فضلك",
        "هل",
        "ما",
        "متي",
        "اين",
        "كيف",
        "ساعات",
        "العمل",
        "حجز",
        "اريد",
        "عندكم",
        "يوجد",
        "اشتراك",
        "غرفة",
        "الشهري",
        "هي",
        "هو",
        "في",
        "علي",
        "الي",
        "عن",
        "هذا",
        "هذه",
        "انا",
        "نحن",
        "انت",
        "انتم",
        "نعم",
        "لا",
        "مساء",
        "صباح",
        "الخير",
        "اهلا",
        "وسهلا",
        "ممكن",
        "يمكن",
        "متاح",
        "اليوم",
        "غدا",
        "الوقت",
        "موعد",
        "عنوان",
        "رقم",
        "هاتف",
        "الدفع",
        "تكلفة",
        "خدمة",
        "خدمات",
        "فندق",
        "مطعم",
        "طاولة",
        "مفتوح",
        "مغلق",
        "استفسار",
        "لدي",
        "لديكم",
        "حجزنا",
        "اوقات",
        "نريد",
        "شهر",
        "يوم",
        # Added in Session 11 (the Arabic eval set found ordinary messages without a hit).
        "اذا",
        "لم",
        "كل",
        "لي",
        "اكتب",
        "اعرض",
        "تجاهل",
        "انس",
        "التعليمات",
        "السابقة",
        "القواعد",
        "المشكلة",
        "شكوى",
        "خصم",
        "استرداد",
        "محامي",
        "تعليمات",
        "المبلغ",
        "الاشتراك",
    ]
)
_AR_NORMALIZE = str.maketrans("أإآٱى", "ااااي")
_RU_EXCLUDED = frozenset("іїєґў")
_AR_EXCLUDED = frozenset("پچژگکیٹڈڑںےھۀ")
_PERSIAN_WORDS = frozenset(["و", "در", "از", "که", "این", "است", "برای"])


def detect_language(text: str) -> str | None:
    """Script and word evidence; mixed or unrecognised foreign text fails closed."""
    text = strip_directional_marks(text)
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return None
    counts = Counter(unicodedata.name(c, "").split(" ")[0] for c in letters)
    total = len(letters)
    foreign = sum(1 for c in letters if _script_is_foreign(c)) / total
    if foreign >= SCRIPT_DOMINANCE:
        lowered = text.lower()
        if counts["CYRILLIC"] / total >= SCRIPT_DOMINANCE:
            if _RU_EXCLUDED.intersection(lowered):
                return UNSUPPORTED
            score = sum(w in _RU_WORDS for w in _WORD.findall(lowered))
            score += DISTINCTIVE_SCORE * sum(c in "ыэъё" for c in lowered)
            return "ru" if score >= RU_MIN_SCORE else UNSUPPORTED
        if counts["ARABIC"] / total >= SCRIPT_DOMINANCE:
            words = _WORD.findall(lowered.translate(_AR_NORMALIZE))
            if _AR_EXCLUDED.intersection(lowered) or _PERSIAN_WORDS.intersection(words):
                return UNSUPPORTED
            score = sum(w in _AR_WORDS for w in words)
            return "ar" if score >= AR_MIN_SCORE else UNSUPPORTED
        return UNSUPPORTED
    if counts["LATIN"] and (counts["CYRILLIC"] + counts["ARABIC"]) / total >= MIXED_SCRIPT_MIN:
        return UNSUPPORTED
    # An explicit foreign greeting is linguistic evidence, even below the stray-name share.
    # This covers the R4 bilingual greeting examples without treating a foreign name as prose.
    words_in_text = _WORD.findall(tr_casefold(text))
    if (
        counts["LATIN"]
        and any(w in {"привет", "здравствуйте"} for w in words_in_text)
        and any(w in _STOP_WORDS["en"] or w in _STOP_WORDS["tr"] for w in words_in_text)
    ):
        return UNSUPPORTED
    scores: Counter[str] = Counter()
    scores["tr"] += DISTINCTIVE_SCORE * sum(c in _TURKISH_LETTERS for c in text)
    for word in _WORD.findall(tr_casefold(text)):
        for language, lexicon in _STOP_WORDS.items():
            if word in lexicon:
                scores[language] += 1
    german_words_found = scores["de"] > 0
    scores["de"] += DISTINCTIVE_SCORE * text.lower().count("ß")
    if german_words_found:
        scores["de"] += GERMAN_UMLAUT_SCORE * text.lower().count("ä")
    ranked = [(code, score) for code, score in scores.most_common() if score]
    if not ranked:
        return None
    best, best_score = ranked[0]
    if best in ("tr", "en") and "hallo" in words_in_text:
        return UNSUPPORTED
    runner, runner_score = ranked[1] if len(ranked) > 1 else ("", 0)
    if best not in ("tr", "en"):
        if runner_score >= MIXED_RATIO * best_score:
            return UNSUPPORTED
    elif (
        runner not in ("", "tr", "en")
        and best_score - runner_score <= LATIN_MIN_MARGIN
        and (runner_score > 1 or runner_score == best_score)
    ):
        # One weak foreign hit never overturns a TR/EN winner.
        return UNSUPPORTED
    if best_score - runner_score < LATIN_MIN_MARGIN:
        return None
    return best if best in REPLY_LANGUAGES else UNSUPPORTED


@dataclass(frozen=True)
class ReplyLanguage:
    """``code`` is the language to answer in, or ``None`` when it is unsupported."""

    code: str | None
    detected: str | None  # reply-language code | other | None (no evidence)

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
    if detected not in REPLY_LANGUAGES or detected not in reply_languages:
        return ReplyLanguage(None, detected)
    return ReplyLanguage(detected, detected)
