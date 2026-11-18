"""INV-02 multilingual claims, trusted spans and original-offset integrity."""

import uuid
from dataclasses import dataclass
from typing import Any

import pytest

from app.inbox.context import DEFAULT_DISCLOSURE
from app.knowledge.claims import fold, strip_directional_marks, validate_claims
from app.knowledge.render import RenderResult, render


@dataclass
class Fact:
    key: str
    value_type: str
    value: dict[str, Any]
    version: int = 1
    fact_id: uuid.UUID = uuid.UUID(int=1)


FACTS = [
    Fact("pricing.room", "money", {"amount": "1200", "currency": "TRY", "unit": "day"}),
    Fact("hours.weekly", "weekly_hours", {"mon": [["09:00", "18:00"]]}),
    Fact("contact.phone", "phone", {"e164": "+905550000000", "display": "0555 000 00 00"}),
    Fact("contact.url", "url", {"url": "https://example.com"}),
]
EMPTY = RenderResult(text="")
CASES = {
    "de": {
        "MONEY": ["89,90 €", "1.234,50 €", "5 Euro", "10 tausend Franken", "5 CHF", "20 Pfund"],
        "TIME": [
            "um 15 Uhr",
            "15 Uhr",
            "15.30 Uhr",
            "von 9 bis 18 Uhr",
            "9-18 Uhr",
            "zwischen 9 und 18",
            "ab 9 Uhr",
            "9 bis 18",
        ],
        "DATE": [
            "am 18. November",
            "1. Januar",
            "18.11.",
            "18.11.2026",
            "18/11",
            "2026-11-18",
            "November 18",
        ],
        "PERCENT": ["20 Prozent Rabatt"],
        "DISCOUNT_WORD": [
            "20 Prozent Rabatt",
            "Ermäßigung",
            "kostenlos",
            "gratis",
            "umsonst",
            "geschenkt",
            "Aktion",
        ],
        "NUMBER": ["250 Zimmer"],
    },
    "ru": {
        "MONEY": [
            "5 000 ₽",
            "5 000 рублей",
            "₽ 750",
            "1 500 руб.",
            "5 евро",
            "10 тыс. рублей",
            "5 долларов",
            "20 фунтов",
        ],
        "TIME": [
            "в 15:00",
            "с 9 до 18",
            "с 9:00 до 18:00",
            "9 утра",
            "6 вечера",
            "в 15 часов",
            "15 часов",
            "в 15 ч",
            "9-18 часов",
        ],
        "DATE": ["18 ноября", "18 нояб.", "2026-11-18", "января 18"],
        "PERCENT": ["скидка 20%", "20 процентов"],
        "DISCOUNT_WORD": ["скидка 20%", "бесплатно", "акция", "в подарок"],
        "NUMBER": ["250 номеров"],
    },
    "ar": {
        "MONEY": [
            "500 ليرة",
            "١٢٠٠ ₺",
            "۱۲۰۰ ₺",
            "5 يورو",
            "5 €",
            "١٬٢٠٠٫٥٠ ₺",
            "5 بالريال",
            "5 د.إ",
            "5 ألف ليرة",
        ],
        "TIME": [
            "الساعة ٥",
            "الساعه 5",
            "من ٩ إلى ٦",
            "من 9 حتى 18",
            "بين 9 و 18",
            "9 صباحا",
            "5 مساء",
            "5 م",
            "9 ص",
            "٠٩:٣٠",
            "09:30",
        ],
        "DATE": ["١٨ نوفمبر", "18 تشرين الثاني", "18 آب", "2026-11-18"],
        "PERCENT": ["خصم ٢٠٪", "20 بالمئة", "20 بالمائة", "20 في المئة"],
        "DISCOUNT_WORD": ["خصم ٢٠٪", "خصومات", "تخفيض", "مجاني", "مجانًا", "عرض خاص", "هدية"],
        "PHONE": ["+٩٠٥٥٥٠٠٠٠٠٠٠", "٠٥٥٥ ٠٠٠ ٠٠ ٠٠"],
        "NUMBER": ["٢٥٠ غرف"],
    },
}


@pytest.mark.parametrize(
    ("locale", "code", "text"),
    [
        (locale, code, text)
        for locale, classes in CASES.items()
        for code, texts in classes.items()
        for text in texts
    ],
)
def test_invented_claims(locale, code, text):
    # Every language's patterns apply regardless of the selected reply locale.
    for selected in (locale, "tr", "en", "ru", "de", "ar"):
        report = validate_claims(text, EMPTY, selected)
        assert code in {issue.code for issue in report.issues}, report
        for issue in report.issues:
            assert text[issue.start : issue.end] == issue.text


@pytest.mark.parametrize("locale", ["ru", "de", "ar"])
def test_rendered_facts_and_suffix_are_trusted_but_neighbour_is_not(locale):
    result = render(
        "{{fact:pricing.room}} {{fact:hours.weekly}} {{fact:contact.phone}} {{fact:contact.url}}",
        FACTS,
        locale,
    )
    assert result.ok
    assert validate_claims(result.text, result, locale).passed
    suffix = " " + DEFAULT_DISCLOSURE[locale]
    text = result.text + suffix
    assert validate_claims(
        text, result, locale, allow_suffix_span=(len(result.text), len(text))
    ).passed
    price = {"de": "89,90 €", "ru": "5 000 рублей", "ar": "١٢٠٠ ₺"}[locale]
    text = result.text + " " + price
    report = validate_claims(text, result, locale)
    assert len(report.issues) == 1 and report.issues[0].code == "MONEY"
    assert report.issues[0].text == price
    assert text[slice(*report.issues[0].span)] == price


@pytest.mark.parametrize("locale", ["ru", "de", "ar"])
@pytest.mark.parametrize("separator", [" ", "\u00a0", "\u202f", "\u2009"])
@pytest.mark.parametrize(
    "mark",
    [
        "",
        "\u200e",
        "\u200f",
        "\u200b",
        "\u200c",
        "\u200d",
        "\u202a",
        "\u202b",
        "\u202c",
        "\u202d",
        "\u202e",
        "\u2060",
        "\u2066",
        "\u2067",
        "\u2068",
        "\u2069",
        "\u061c",
        "\ufeff",
        "\u00ad",
        "\u064b",
        "\u065f",
        "\u0670",
        "\u0640",
    ],
)
def test_ignorables_and_spaces_never_hide_money_or_change_offsets(locale, separator, mark):
    price = f"1{mark}{separator}234,50{separator}€"
    text = "prefix " + price + " suffix"
    report = validate_claims(text, EMPTY, locale)
    assert len(report.issues) == 1
    issue = report.issues[0]
    assert issue.code == "MONEY" and issue.text == price
    assert text[slice(*issue.span)] == issue.text


@pytest.mark.parametrize(
    "text",
    ["1\u200b2\u200b0\u200b0 ₺", "١٢٠٠ ₺", "۱۲۰۰ ₺", "\u200f1200\u200f₺", "1.2\u200f34,50 €"],
)
def test_original_digit_and_hidden_price_spans(text):
    issues = validate_claims(text, EMPTY, "ar").issues
    assert len(issues) == 1 and issues[0].code == "MONEY"
    assert text[slice(*issues[0].span)] == issues[0].text
    assert strip_directional_marks(issues[0].text) == strip_directional_marks(text)


@pytest.mark.parametrize(
    ("locale", "text"),
    [
        ("de", "Hallo, gerne helfen wir Ihnen. 2 Zimmer"),
        ("ru", "Здравствуйте, рады помочь. 2 номера"),
        ("ar", "مرحبا اهلا وسهلا 2 غرف غرفتين"),
    ],
)
def test_plain_text_and_small_counts(locale, text):
    assert validate_claims(text, EMPTY, locale).passed
    suffix = DEFAULT_DISCLOSURE[locale]
    assert validate_claims(suffix, EMPTY, locale, allow_suffix_span=(0, len(suffix))).passed


def test_fold_is_length_preserving_and_maps_digits_and_letters():
    source = "٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹٫٬٪ёäẞأإآٱى"
    assert fold(source) == "01234567890123456789.,%еasااااي"
    assert len(fold(source)) == len(source)


def test_promotion_exemption_still_applies():
    fact = Fact("promotion.offer", "text", {"text": "Promotion"})
    result = render("{{fact:promotion.offer}} Rabatt скидка خصم", [fact], "de")
    assert validate_claims(result.text, result, "de").passed


@pytest.mark.parametrize("text", ["09.05", "09:05", "09.05 Uhr"])
def test_legacy_dot_times_remain_times(text):
    assert "TIME" in {issue.code for issue in validate_claims(text, EMPTY, "de").issues}
