from datetime import UTC, datetime, timedelta

import pytest

from app.core.clock import FrozenClock, SystemClock
from app.core.errors import ERROR_CATALOG, AppError
from app.core.i18n import (
    DEFAULT_LOCALE,
    catalog_keys,
    format_local_datetime,
    normalize_locale,
    t,
)


def test_system_clock_is_utc_aware() -> None:
    now = SystemClock().now()
    assert now.tzinfo is not None and now.utcoffset() == timedelta(0)


def test_frozen_clock_moves_only_when_advanced() -> None:
    clock = FrozenClock(datetime(2026, 1, 1, tzinfo=UTC))
    assert clock.now() == clock.now() == datetime(2026, 1, 1, tzinfo=UTC)
    clock.advance(minutes=5)
    clock.advance(timedelta(seconds=30))
    assert clock.now() == datetime(2026, 1, 1, 0, 5, 30, tzinfo=UTC)


def test_frozen_clock_rejects_naive_start_and_negative_steps() -> None:
    with pytest.raises(ValueError):
        FrozenClock(datetime(2026, 1, 1))
    with pytest.raises(ValueError):
        FrozenClock().advance(minutes=-1)


def test_every_error_code_has_translations_in_both_catalogs() -> None:
    for locale in ("tr", "en"):
        keys = catalog_keys(locale)
        for code in ERROR_CATALOG:
            assert f"errors.{code}.what" in keys, (locale, code)
            assert f"errors.{code}.next" in keys, (locale, code)


def test_catalogs_have_identical_key_sets() -> None:
    assert catalog_keys("tr") == catalog_keys("en")


def test_app_error_defaults_and_overrides() -> None:
    assert AppError("NOT_FOUND").http_status == 404
    assert AppError("NOT_FOUND", http_status=410).http_status == 410
    assert AppError("FORBIDDEN", permission="x").params == {"permission": "x"}


def test_app_error_rejects_unknown_codes() -> None:
    with pytest.raises(ValueError):
        AppError("NOPE")


def test_t_uses_requested_locale() -> None:
    assert t("errors.NOT_FOUND.what", "en") == "We could not find what you were looking for."
    assert t("errors.NOT_FOUND.what", "tr").startswith("Aradığınız")


def test_t_falls_back_to_default_locale_for_unsupported_locale() -> None:
    assert DEFAULT_LOCALE == "tr"
    assert t("errors.NOT_FOUND.what", "de") == t("errors.NOT_FOUND.what", "tr")


def test_t_returns_the_key_when_missing() -> None:
    assert t("no.such.key", "en") == "no.such.key"


def test_t_interpolates_params_and_keeps_missing_placeholders() -> None:
    assert "abc123" in t("errors.INTERNAL_ERROR.next", "en", request_id="abc123")
    assert "{request_id}" in t("errors.INTERNAL_ERROR.next", "en")


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("tr-TR", "tr"), ("EN_us", "en"), (None, "tr"), ("", "tr"), ("fr", "tr")],
)
def test_normalize_locale(raw: str | None, expected: str) -> None:
    assert normalize_locale(raw) == expected


def test_format_local_datetime_uses_the_workspace_timezone() -> None:
    instant = datetime(2026, 7, 1, 17, 0, tzinfo=UTC)
    assert "20:00" in format_local_datetime(instant, "Europe/Istanbul", "tr")
    lisbon = format_local_datetime(instant, "Europe/Lisbon", "en")  # WEST, UTC+1; 12-hour clock
    assert "6:00" in lisbon and "PM" in lisbon
