"""AC-X6: production refuses unsafe configuration (INV-20)."""

import pytest

from app.core.config import EXAMPLE_SECRET_KEY, ConfigError, Settings

GOOD_SECRET = "x" * 48
PROD_DB = "postgresql+psycopg://u:p@db.internal:5432/agentnest"


@pytest.fixture(autouse=True)
def _clean_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """conftest exports DATABASE_URL etc.; these tests must see only their explicit arguments."""
    for name in (
        "APP_ENV",
        "DATABASE_URL",
        "SECRET_KEY",
        "DEMO_TOOLS_ENABLED",
        "COOKIE_SECURE",
        "LOG_FORMAT",
        "LOG_LEVEL",
    ):
        monkeypatch.delenv(name, raising=False)


def prod(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "app_env": "production",
        "secret_key": GOOD_SECRET,
        "database_url": PROD_DB,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)  # type: ignore[arg-type]


def test_safe_production_config_starts_with_safe_defaults() -> None:
    settings = prod()
    assert settings.demo_tools_enabled is False
    assert settings.cookie_secure is True
    assert settings.log_format == "json"


def test_demo_tools_enabled_is_refused_in_production() -> None:
    with pytest.raises(ConfigError, match="DEMO_TOOLS_ENABLED"):
        prod(demo_tools_enabled=True)


def test_missing_secret_key_is_refused() -> None:
    with pytest.raises(ConfigError, match="SECRET_KEY must be set"):
        Settings(_env_file=None, app_env="production", database_url=PROD_DB)


def test_example_secret_key_is_refused() -> None:
    with pytest.raises(ConfigError, match="example value"):
        prod(secret_key=EXAMPLE_SECRET_KEY)


def test_short_secret_key_is_refused() -> None:
    with pytest.raises(ConfigError, match="at least 32 bytes"):
        prod(secret_key="too-short")


def test_insecure_cookies_are_refused_in_production() -> None:
    with pytest.raises(ConfigError, match="COOKIE_SECURE"):
        prod(cookie_secure=False)


def test_database_url_must_be_explicit_in_production() -> None:
    with pytest.raises(ConfigError, match="DATABASE_URL"):
        Settings(_env_file=None, app_env="production", secret_key=GOOD_SECRET)


def test_all_problems_are_reported_together() -> None:
    with pytest.raises(ConfigError) as info:
        Settings(_env_file=None, app_env="production", demo_tools_enabled=True)
    assert len(info.value.problems) >= 3


def test_development_defaults_allow_demo_tools() -> None:
    settings = Settings(_env_file=None, app_env="development")
    assert settings.demo_tools_enabled is True
    assert settings.cookie_secure is False


def test_public_dict_contains_no_secrets() -> None:
    settings = prod()
    dumped = str(settings.public_dict())
    assert GOOD_SECRET not in dumped
    assert "u:p@" not in dumped and ":p@" not in dumped
    assert "demo-password" not in dumped
    assert settings.public_dict()["database"].startswith("postgresql+psycopg://u:***@")


def test_log_level_is_case_insensitive() -> None:
    assert Settings(_env_file=None, log_level="debug").log_level == "DEBUG"
