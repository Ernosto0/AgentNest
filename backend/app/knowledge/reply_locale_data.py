"""Reply-only labels and formatting data; UI catalogs remain Turkish/English."""

BABEL_LOCALES = {"tr": "tr_TR", "en": "en", "ru": "ru_RU", "de": "de_DE", "ar": "ar"}
CURRENCY_SYMBOLS = {"TRY": "₺", "EUR": "€", "USD": "$", "GBP": "£", "RUB": "₽"}
RANGE_JOINERS = {"tr": "–", "en": "–", "ru": "–", "de": "–", "ar": "\u200e–\u200e"}
_UNITS = ("month", "session", "package", "item", "hour", "person", "day", "year")
LABELS = {
    "ru": dict(
        zip(_UNITS, ("месяц", "занятие", "пакет", "шт.", "час", "чел.", "день", "год"), strict=True)
    ),
    "de": dict(
        zip(
            _UNITS,
            ("Monat", "Sitzung", "Paket", "Stück", "Stunde", "Person", "Tag", "Jahr"),
            strict=True,
        )
    ),
    "ar": dict(
        zip(_UNITS, ("شهر", "جلسة", "باقة", "قطعة", "ساعة", "شخص", "يوم", "سنة"), strict=True)
    ),
}
REPLY_LABELS = {
    code: {f"knowledge.unit.{key}": value for key, value in units.items()}
    for code, units in LABELS.items()
}
for _code, _closed, _yes, _no, _share, _private in (
    ("ru", "закрыто", "Да", "Нет", "Показывать цены", "Не показывать цены"),
    ("de", "geschlossen", "Ja", "Nein", "Preise teilen", "Preise nicht teilen"),
    ("ar", "مغلق", "نعم", "لا", "مشاركة الأسعار", "عدم مشاركة الأسعار"),
):
    REPLY_LABELS[_code].update(
        {
            "knowledge.hours.closed": _closed,
            "knowledge.bool.true": _yes,
            "knowledge.bool.false": _no,
            "knowledge.enum.share": _share,
            "knowledge.enum.do_not_share": _private,
        }
    )
