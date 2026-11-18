"""Reply language evidence and explicit R4 boundaries, all offline."""

import pytest
from pydantic import ValidationError

from app.core.reply_languages import REPLY_LANGUAGES, RTL_REPLY_LANGUAGES, is_reply_language
from app.identity.schemas import WorkspacePatch
from app.inbox.language import (
    _STOP_WORDS,
    AR_MIN_SCORE,
    DISTINCTIVE_SCORE,
    GERMAN_UMLAUT_SCORE,
    LATIN_MIN_MARGIN,
    MIXED_RATIO,
    MIXED_SCRIPT_MIN,
    RU_MIN_SCORE,
    SCRIPT_DOMINANCE,
    choose_reply_language,
    detect_language,
)

POSITIVES = {
    "ru": [
        "Привет, сколько стоит абонемент?",
        "Во сколько вы открываетесь?",
        "Здравствуйте, можно забронировать номер на завтра?",
        "Спасибо!",
        "Добрый день",
        "Где адрес?",
        "Ещё есть номер?",
        "Еще есть номер?",
        "Цена 1200?",
    ],
    "de": [
        "Wie viel kostet die Mitgliedschaft?",
        "Hallo, haben Sie am Sonntag geöffnet?",
        "Guten Tag, ich möchte einen Tisch reservieren",
        "Was kostet ein Zimmer?",
        "Danke schön",
        "Grüße aus der Straße",
        "Wann können wir buchen?",
        "Bitte reservieren",
    ],
    "ar": [
        "مرحبا كم سعر الاشتراك الشهري؟",
        "ما هي ساعات العمل؟",
        "السلام عليكم، أريد حجز غرفة",
        "مَرْحَبًا كَمْ السِّعْرُ؟",
        "كم السعر ١٢٠٠؟",
        "مر\u200eحبا كم الس\u200fعر؟",
        "شكراً",
        "أين العنوان؟",
        "هل يوجد غرفة؟",
    ],
}


@pytest.mark.parametrize(
    ("language", "text"), [(c, t) for c, texts in POSITIVES.items() for t in texts]
)
def test_positive(language, text):
    assert detect_language(text) == language


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Привіт, скільки коштує?", "other"),
        ("Здравейте благодаря", "other"),
        ("Жжжж", "other"),
        ("Привет, how much is the membership price per month?", "other"),
        ("Дзякуй ў", "other"),
        ("Добар дан хвала", "other"),
        ("I was sure the plants die in winter", "en"),
        ("Hyvää päivää", None),
        ("Det här är bra", None),
        ("Hallo, how much is it?", "other"),
        ("Üyelik ücreti nedir?", "tr"),
        ("fiyatı öğrenmek istiyorum", "tr"),
        ("سلام، قیمت اشتراک چقدر است؟", "other"),
        ("آپ کی قیمت کیا ہے؟", "other"),
        ("Hi, كم السعر for the classes please", "other"),
        ("١٢٣", None),
        ("ژژژ", "other"),
        ("سلام در از", "other"),
    ],
)
def test_negative(text, expected):
    assert detect_language(text) == expected


@pytest.mark.parametrize("language", ["ru", "de", "ar"])
def test_newest_wins_and_disabled_language_escalates(language):
    text = POSITIVES[language][0]
    chosen = choose_reply_language(
        [text, "Hello"], default_locale="tr", reply_languages=REPLY_LANGUAGES
    )
    assert (chosen.code, chosen.detected) == (language, language)
    chosen = choose_reply_language([text], default_locale="tr", reply_languages=["tr", "en"])
    assert (chosen.code, chosen.detected) == (None, language)
    assert (
        choose_reply_language(
            ["Hello", text], default_locale="tr", reply_languages=REPLY_LANGUAGES
        ).code
        == "en"
    )


@pytest.mark.parametrize(
    "text",
    [
        "Hallo how much is it",
        "Привет how much is the membership price",
        "كم السعر hello how much please",
    ],
)
def test_mixed_is_unsupported(text):
    result = choose_reply_language([text], default_locale="tr", reply_languages=REPLY_LANGUAGES)
    assert (result.code, result.detected) == (None, "other")


def test_script_thresholds():
    assert SCRIPT_DOMINANCE == 0.5 and MIXED_SCRIPT_MIN == 0.2
    # Exactly half versus just under: only a dominant script can use its words.
    assert detect_language("цена aaaa") == "ru"
    assert detect_language("цена aaaaa") == "other"
    assert detect_language("سعر aaa") == "ar"
    assert detect_language("سعر aaaa") == "other"
    # Stray name letters below 20% are ignored; at 20% they force R4.
    assert detect_language("hello abcd ЖЖ") == "en"
    assert detect_language("hello abc ЖЖ") == "other"
    assert detect_language("hello abcd ظظ") == "en"
    assert detect_language("hello abc ظظ") == "other"


def test_evidence_thresholds():
    assert RU_MIN_SCORE == AR_MIN_SCORE == 1
    assert detect_language("Жжж") == "other"
    assert detect_language("цена") == "ru"
    assert detect_language("ظظظ") == "other"
    assert detect_language("سعر") == "ar"
    assert DISTINCTIVE_SCORE == 2
    assert detect_language("жжжж") == "other"
    assert detect_language("ыжжж") == "ru"
    assert detect_language("xxx") is None
    assert detect_language("ßxxx") == "de"
    assert GERMAN_UMLAUT_SCORE == 1
    assert detect_language("ä") is None
    assert detect_language("Hallo ä") == "de"


def test_latin_dominance_boundaries():
    assert MIXED_RATIO == 0.5 and LATIN_MIN_MARGIN == 1
    assert detect_language("hallo danke bitte hello") == "de"  # 1 < half of 3
    assert detect_language("hallo danke hello") == "other"  # 1 == half of 2
    assert detect_language("hello merhaba") is None
    assert detect_language("hello thanks merhaba") == "en"
    assert detect_language("hello thanks bitte") == "en"  # weak foreign hit
    assert detect_language("hello thanks price hallo danke") == "other"
    assert not (_STOP_WORDS["de"] & (_STOP_WORDS["en"] | _STOP_WORDS["tr"]))


def test_reply_codes_are_separate_from_ui_locales():
    assert REPLY_LANGUAGES == ("tr", "en", "ru", "de", "ar")
    assert {"ar"} == RTL_REPLY_LANGUAGES
    assert is_reply_language("ru") and not is_reply_language(None)
    assert WorkspacePatch(reply_languages=["ru", "de", "ar"]).reply_languages == ["ru", "de", "ar"]
    with pytest.raises(ValidationError):
        WorkspacePatch(reply_languages=["fr"])
    with pytest.raises(ValidationError):
        WorkspacePatch(default_locale="ru")


@pytest.mark.parametrize(
    ("hint", "code"),
    [
        ("ru", "ru"),
        ("Russian", "ru"),
        ("de", "de"),
        ("German", "de"),
        ("ar", "ar"),
        ("Arabic", "ar"),
    ],
)
def test_transcript_provider_hints(hint, code):
    from app.inbox.transcription import _language

    assert _language("123", hint) == code
    assert _language("Hello, how much?", hint) == "en"


@pytest.mark.parametrize("code", ["ru", "de", "ar"])
def test_learning_loop_keeps_reply_language(code):
    from app.inbox.answers import _language

    assert _language(POSITIVES[code][0]) == code
