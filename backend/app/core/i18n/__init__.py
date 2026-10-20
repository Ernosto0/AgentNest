"""Server-side catalogs: ``t(key, locale, **params)`` (ADR-016).

Catalogs are flat JSON files (``tr.json``, ``en.json``). Lookup falls back from the
requested locale to the default locale, then to the key itself.
"""

import json
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from babel.dates import format_datetime

SUPPORTED_LOCALES = ("tr", "en")
DEFAULT_LOCALE = "tr"

_CATALOG_DIR = Path(__file__).parent
_BABEL_LOCALES = {"tr": "tr_TR", "en": "en"}


class _SafeParams(dict[str, Any]):
    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


@lru_cache
def _catalog(locale: str) -> dict[str, str]:
    data = json.loads((_CATALOG_DIR / f"{locale}.json").read_text(encoding="utf-8"))
    return {str(k): str(v) for k, v in data.items()}


def catalog_keys(locale: str) -> set[str]:
    return set(_catalog(locale))


def normalize_locale(value: str | None) -> str:
    """``tr-TR`` -> ``tr``; unsupported or missing -> the default locale."""
    if not value:
        return DEFAULT_LOCALE
    base = value.strip().lower().replace("_", "-").split("-")[0]
    return base if base in SUPPORTED_LOCALES else DEFAULT_LOCALE


def t(key: str, locale: str | None = DEFAULT_LOCALE, **params: Any) -> str:
    primary = normalize_locale(locale)
    for candidate in (primary, DEFAULT_LOCALE):
        template = _catalog(candidate).get(key)
        if template is not None:
            return template.format_map(_SafeParams(params))
    return key


def format_local_datetime(value: datetime, timezone: str, locale: str | None) -> str:
    """Format an instant in the given IANA timezone using the locale's medium style."""
    return format_datetime(
        value.astimezone(ZoneInfo(timezone)),
        format="medium",
        locale=_BABEL_LOCALES[normalize_locale(locale)],
    )


def format_local_slot(value: datetime, timezone: str, locale: str | None) -> str:
    """A short local day and time for choices and results ("16 Eki 19:00"); INV-19."""
    return format_datetime(
        value.astimezone(ZoneInfo(timezone)),
        format="d MMM HH:mm",
        locale=_BABEL_LOCALES[normalize_locale(locale)],
    )
