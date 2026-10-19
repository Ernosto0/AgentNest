"""Claim validator, tr/en patterns (business-knowledge.md §7.2, INV-02)."""

import uuid
from dataclasses import dataclass
from typing import Any

import pytest

from app.knowledge.claims import (
    DATE,
    DISCOUNT_WORD,
    EMAIL,
    MONEY,
    NUMBER,
    PERCENT,
    PHONE,
    TIME,
    TOO_LONG,
    URL,
    AllowList,
    byte_length,
    fold,
    length_issue,
    validate_claims,
)
from app.knowledge.render import RenderResult, render


@dataclass(frozen=True)
class Fact:
    key: str
    value_type: str
    value: dict[str, Any]
    version: int = 1
    fact_id: uuid.UUID = uuid.uuid4()


MONTHLY = Fact("pricing.membership_monthly", "money", {"amount": "6000.00", "currency": "TRY"})
PHONE_FACT = Fact("contact.phone", "phone", {"e164": "+905550000000", "display": "0555 000 00 00"})
SITE = Fact("contact.website", "url", {"url": "https://golkent.example/fit"})
MAIL = Fact("contact.email", "email", {"email": "info@golkent.example"})
TRIAL = Fact(
    "promotion.trial_session",
    "localized_text",
    {"tr": "ilk deneme seansı ücretsiz", "en": "first trial session is free"},
)
FACTS = [MONTHLY, PHONE_FACT, SITE, MAIL, TRIAL]
EMPTY = RenderResult(text="")


def codes(text: str, result: RenderResult = EMPTY, locale: str = "tr") -> list[str]:
    return [i.code for i in validate_claims(text, result, locale).issues]


def checked(template: str, locale: str = "tr", **kwargs: Any) -> tuple[RenderResult, Any]:
    result = render(template, FACTS, locale)
    assert result.ok, result.errors
    return result, validate_claims(result.text, result, locale, **kwargs)


# --- money ---------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "Aylık 6000 TL",
        "Aylık 6.000₺",
        "Aylık ₺6.000",
        "Aylık 6 bin lira",
        "Aylık 6 bin TL",
        "Aylık TRY 6,000",
        "Only $50 per month",
        "It costs 50 euro",
        "Just €50",
        "50 EUR",
        "6.000 TL'ye",
        "fiyat 5 TL",  # a small number next to a currency is still a price
        "£20 a visit",
        "6k TL",
    ],
)
def test_invented_money_is_flagged(text: str) -> None:
    assert MONEY in codes(text), text


def test_the_issue_span_points_at_the_original_text() -> None:
    text = "Merhaba! Aylık üyelik 6.000₺ dir."
    (issue,) = validate_claims(text, EMPTY, "tr").issues
    assert issue.code == MONEY and text[issue.start : issue.end] == "6.000₺"
    assert issue.text == "6.000₺"


# --- percent and discounts -----------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    ["%20 daha ucuz", "20% off", "yüzde 20 fark", "Yüzde 15", "50 percent", "%100"],
)
def test_percentages_are_flagged(text: str) -> None:
    assert PERCENT in codes(text), text


@pytest.mark.parametrize(
    "text",
    [
        "Size özel indirim var",
        "İNDİRİMLİ fiyat",
        "bedava deneyin",
        "ücretsiz deneme",
        "ÜCRETSİZ otopark",
        "It is free",
        "Get a discount",
    ],
)
def test_discount_words_are_flagged_without_a_promotion(text: str) -> None:
    assert DISCOUNT_WORD in codes(text), text


def test_discount_words_pass_when_a_usable_promotion_is_used_in_the_same_text() -> None:
    result, report = checked("{{fact:promotion.trial_session}}: ücretsiz deneme seansı için arayın")
    assert report.passed, report.issues


def test_a_non_promotion_fact_does_not_back_discount_words() -> None:
    result, report = checked("Aylık {{fact:pricing.membership_monthly}} ve ücretsiz kahve")
    assert [i.code for i in report.issues] == [DISCOUNT_WORD]


def test_free_inside_another_word_is_not_a_discount() -> None:
    assert DISCOUNT_WORD not in codes("a carefree afternoon")


# --- times ---------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "Açılış 19:00",
        "07:00–23:00 arası",
        "saat 9'da görüşelim",
        "Saat 9 gibi gelin",
        "9am to 5pm",
        "9 am",
        "7-23 arası açığız",
        "9-17 arasında",
        "9 ile 18 arası",
        "7'den 23'e kadar",
        "between 9 and 18",
        "9 o'clock",
        "19.00'da",
        "Monday 9:00",
    ],
)
def test_invented_times_are_flagged(text: str) -> None:
    assert TIME in codes(text), text


# --- dates ---------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "29 Ekim'de kapalıyız",
        "29 Ekim",
        "1 Ocak",
        "29.10 günü",
        "29/10/2026",
        "29.10.2026",
        "2026-10-29",
        "October 29",
        "29th October",
        "Oct 29",
        "15 Mayıs",
    ],
)
def test_invented_dates_are_flagged(text: str) -> None:
    assert DATE in codes(text), text


# --- phone, e-mail, URL --------------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "Arayın: 0555 000 00 00",
        "05550000000",
        "0 (555) 000 00 00",
        "+90 555 000 00 00",
        "+905550000000",
        "0090 555 000 00 00",
        "Call +44 20 7946 0958",
        "0212 555 12 34",
    ],
)
def test_invented_phone_numbers_are_flagged(text: str) -> None:
    assert PHONE in codes(text), text


@pytest.mark.parametrize("text", ["yaz: someone@example.com", "info@golkent.example'e yazın"])
def test_invented_emails_are_flagged(text: str) -> None:
    assert EMAIL in codes(text), text


@pytest.mark.parametrize(
    "text",
    [
        "https://evil.example/pay",
        "http://x.co",
        "www.golkent.example",
        "instagram.com/golkent",
        "golkent.com.tr/uyelik",
        "bkz. golkent.com",
    ],
)
def test_invented_urls_are_flagged(text: str) -> None:
    assert URL in codes(text), text


def test_an_email_is_not_also_reported_as_a_url() -> None:
    assert codes("yaz: someone@example.com") == [EMAIL]


def test_the_exact_value_of_a_rendered_fact_may_be_typed_out_elsewhere() -> None:
    result, _ = checked("Site: {{fact:contact.website}}")
    typed_again = result.text + " (https://golkent.example/fit)"
    assert validate_claims(typed_again, result, "tr").passed
    # ...but any other URL is still refused
    assert URL in [
        i.code for i in validate_claims(typed_again + " http://x.co", result, "tr").issues
    ]


# --- numbers and the small-number allow-list -----------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "2 kişi",
        "1 ay",
        "8 seans",
        "20 kişi",
        "Haftada 3 gün",
        "iki kişi gelin",
        "Merhaba! Nasıl yardımcı olabilirim?",
        "",
    ],
)
def test_small_cardinal_numbers_and_plain_text_pass(text: str) -> None:
    assert codes(text) == [], text


@pytest.mark.parametrize("text", ["250 kişi", "21 gün", "1500 üye", "2026 yılında", "2.75 saat"])
def test_other_numbers_above_the_allow_list_are_flagged(text: str) -> None:
    assert NUMBER in codes(text), text


def test_the_allow_list_is_configurable_per_locale() -> None:
    generous = AllowList(small_number_max=100)
    assert validate_claims("50 kişi", EMPTY, "tr", allow=generous).passed
    assert not validate_claims("50 kişi", EMPTY, "tr").passed


def test_an_allowed_phrase_is_never_a_claim() -> None:
    branded = AllowList(phrases=("Studio 360",))
    assert validate_claims("Studio 360 şubesi", EMPTY, "en", allow=branded).passed
    assert not validate_claims("Studio 360 şubesi", EMPTY, "en").passed


# --- rendered spans and suffixes -----------------------------------------------------------


def test_values_inside_rendered_spans_are_trusted() -> None:
    result, report = checked(
        "Aylık üyelik {{fact:pricing.membership_monthly}}. Arayın: {{fact:contact.phone}}"
    )
    assert "6.000" in result.text and report.passed, report.issues


def test_the_same_value_typed_by_the_model_next_to_a_span_is_still_flagged() -> None:
    result = render("Aylık {{fact:pricing.membership_monthly}}", FACTS, "tr")
    text = result.text + " veya 7.000 TL"
    report = validate_claims(text, result, "tr")
    assert [i.code for i in report.issues] == [MONEY]
    assert text[report.issues[0].start :].startswith("7.000 TL")


def test_the_code_appended_suffix_is_excluded() -> None:
    result = render("Merhaba!", FACTS, "tr")
    suffix = " Bu mesaj yapay zekâ ile hazırlandı. Bilgi: 0555 000 00 00"
    text = result.text + suffix
    span = (len(result.text), len(text))
    assert not validate_claims(text, result, "tr").passed
    assert validate_claims(text, result, "tr", allow_suffix_span=span).passed


def test_a_rendered_span_does_not_hide_an_invented_neighbour() -> None:
    result = render("{{fact:pricing.membership_monthly}}'dan 200 TL indirim", FACTS, "tr")
    assert {MONEY, DISCOUNT_WORD} <= {
        i.code for i in validate_claims(result.text, result, "tr").issues
    }


def test_issues_are_sorted_by_position_and_do_not_overlap() -> None:
    text = "29 Ekim saat 19:00 ve %20 indirim, 0555 000 00 00, a@b.co"
    issues = validate_claims(text, EMPTY, "tr").issues
    assert [i.start for i in issues] == sorted(i.start for i in issues)
    for earlier, later in zip(issues, issues[1:], strict=False):
        assert earlier.end <= later.start


# --- turkish folding ----------------------------------------------------------------------


def test_fold_keeps_the_length_so_spans_index_the_original() -> None:
    for text in ("İSTANBUL İNDİRİM", "ÇIĞ ŞÖYLE ÜST", "ıİiI", "mixed 6.000₺"):
        assert len(fold(text)) == len(text)


def test_dotted_and_dotless_capitals_match_discount_words() -> None:
    assert DISCOUNT_WORD in codes("İNDİRİM ve ÜCRETSİZ")


# --- length ---------------------------------------------------------------------------------


def test_byte_length_counts_utf8_bytes_not_characters() -> None:
    assert byte_length("abc") == 3
    assert byte_length("ğüşöç") == 10  # Turkish letters are two bytes each
    assert byte_length("₺") == 3


def test_length_issue_uses_bytes_for_dms_and_characters_for_captions() -> None:
    assert length_issue("a" * 1000, max_bytes=1000) is None
    assert length_issue("a" * 1001, max_bytes=1000).code == TOO_LONG  # type: ignore[union-attr]
    turkish = "ş" * 600  # 600 characters but 1200 bytes
    assert length_issue(turkish, max_bytes=1000) is not None
    assert length_issue(turkish, max_chars=2200) is None
    assert length_issue("a" * 2201, max_chars=2200) is not None
    assert length_issue("anything") is None


def test_the_report_serialises_for_storage() -> None:
    report = validate_claims("6000 TL", EMPTY, "tr")
    assert report.to_dict() == {
        "passed": False,
        "issues": [{"code": "MONEY", "span": [0, 7], "text": "6000 TL"}],
    }
