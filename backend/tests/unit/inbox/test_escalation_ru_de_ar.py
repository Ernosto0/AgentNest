"""Every deterministic safety flag covers each newly draftable language."""

import pytest

from app.inbox.escalation import keyword_flags

CASES = {
    "complaint": [
        "Beschwerde einreichen",
        "schlechter Service",
        "жалоба на сервис",
        "я недоволен",
        "شكوى عن الخدمة",
        "خدمة سيئة",
    ],
    "refund": [
        "Rückerstattung bitte",
        "Geld zurück",
        "возврат оплаты",
        "верните деньги",
        "استرداد المال",
        "أريد أموالي",
    ],
    "discount": [
        "Rabatt bitte",
        "Ermäßigung bitte",
        "скидка пожалуйста",
        "можно дешевле",
        "خصم من فضلك",
        "تخفيض السعر",
    ],
    "legal": [
        "mein Anwalt",
        "ich werde klagen",
        "мой адвокат",
        "подам в суд",
        "هذا محامي",
        "سأرفع دعوى",
    ],
    "health_safety": [
        "ein Unfall",
        "ins Krankenhaus",
        "получил травму",
        "нужна скорая",
        "وقع حادث",
        "اتصل بالطوارئ",
    ],
    "abusive": ["du Arschloch", "Dummkopf", "ты идиот", "заткнись", "أنت أحمق", "اخرس"],
    "personal_data": [
        "meine Kreditkarte",
        "mein Reisepass",
        "мой паспорт",
        "номер карты",
        "بطاقة ائتمان",
        "جواز سفر",
    ],
}


@pytest.mark.parametrize(("flag", "text"), [(f, t) for f, texts in CASES.items() for t in texts])
def test_flags(flag, text):
    assert flag in keyword_flags(text)


@pytest.mark.parametrize(
    "text", ["Wie viel kostet ein Zimmer?", "Сколько стоит номер?", "كم سعر الغرفة؟"]
)
def test_ordinary_questions(text):
    assert keyword_flags(text) == set()


@pytest.mark.parametrize(
    ("flag", "text"),
    [
        ("legal", "سأتصل بمحامي إذا لم تحلوا المشكلة"),
        ("legal", "سأستشير المحامي"),
        ("refund", "أريد الاسترداد لاشتراكي"),
        ("discount", "هل هناك بخصم؟"),
        ("complaint", "لدي شكوى"),
    ],
)
def test_arabic_particles_attached_to_a_keyword_still_match(flag, text):
    assert flag in keyword_flags(text)
