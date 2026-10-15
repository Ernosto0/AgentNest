import pytest

from app.core.errors import AppError
from app.core.security import hash_password, password_policy_problems, verify_password
from app.identity.service import normalize_email, slugify, valid_currencies, valid_timezones


@pytest.mark.parametrize(
    ("name", "slug"),
    [
        ("Gölkent Fitness & Pilates", "golkent-fitness-pilates"),
        ("İstanbul Şube", "istanbul-sube"),
        ("  Harbor   Pilates Studio ", "harbor-pilates-studio"),
        ("###", "workspace"),
        ("a" * 200, "a" * 60),
    ],
)
def test_slugify(name: str, slug: str) -> None:
    assert slugify(name) == slug


def test_normalize_email() -> None:
    assert normalize_email("  Owner@Demo.Local ") == "owner@demo.local"


def test_currency_and_timezone_whitelists() -> None:
    assert {"TRY", "EUR", "USD", "GBP"} <= valid_currencies()
    assert not {"XXX", "DEM", "try", ""} & valid_currencies()
    assert {"Europe/Istanbul", "Europe/Lisbon", "UTC"} <= valid_timezones()
    assert "../etc/passwd" not in valid_timezones()


def test_password_policy_is_length_based_with_a_common_password_list() -> None:
    assert password_policy_problems("short") == ["too_short"]
    assert password_policy_problems("password123") == ["too_common"]
    assert password_policy_problems("Password123") == ["too_common"]  # case-insensitive
    assert password_policy_problems("correct-horse-battery") == []
    assert password_policy_problems("a" * 10) == []  # no composition rules


def test_verify_password_roundtrip_and_unknown_user_path() -> None:
    hashed = hash_password("correct-horse-battery")
    assert verify_password(hashed, "correct-horse-battery") is True
    assert verify_password(hashed, "wrong") is False
    assert verify_password(None, "anything") is False  # unknown user still costs a verify
    assert verify_password("not-a-hash", "x") is False


def test_app_error_with_validation_errors_is_constructible() -> None:
    error = AppError("VALIDATION_FAILED", errors=[{"field": "x", "code": "y", "params": {}}])
    assert error.http_status == 422
