"""Customer reply languages, independent of UI and content locales."""

REPLY_LANGUAGES = ("tr", "en", "ru", "de", "ar")
RTL_REPLY_LANGUAGES = frozenset({"ar"})


def is_reply_language(code: str | None) -> bool:
    return code in REPLY_LANGUAGES
