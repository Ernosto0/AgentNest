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
        "LLM_PROVIDER",
        "OPENAI_API_KEY",
        "LLM_MODEL_DEFAULT",
        "INSTAGRAM_ENABLED_PROVIDERS",
        "ALLOW_SIMULATED_WORKSPACES",
        "MOCK_INSTAGRAM_APP_SECRET",
        "META_WEBHOOK_VERIFY_TOKEN",
        "META_APP_SECRET",
        "MEDIA_STORAGE_BACKEND",
        "MEDIA_LOCAL_ROOT",
    ):
        monkeypatch.delenv(name, raising=False)


def prod(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "app_env": "production",
        "secret_key": GOOD_SECRET,
        "database_url": PROD_DB,
        "llm_provider": "openai",
        "openai_api_key": "sk-test-key",
        "meta_app_secret": "meta-secret",
        "meta_webhook_verify_token": "verify-token",
        "media_storage_backend": "s3",  # Meta needs a public URL; local is refused with it
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


def test_fake_llm_is_refused_in_production() -> None:
    with pytest.raises(ConfigError, match="LLM_PROVIDER must not be 'fake'"):
        prod(llm_provider="fake")


def test_default_llm_provider_is_fake_so_production_must_choose_one() -> None:
    with pytest.raises(ConfigError, match="LLM_PROVIDER"):
        Settings(_env_file=None, app_env="production", secret_key=GOOD_SECRET, database_url=PROD_DB)


def test_openai_requires_a_key_and_a_model_in_production() -> None:
    with pytest.raises(ConfigError, match="OPENAI_API_KEY"):
        prod(openai_api_key="")
    with pytest.raises(ConfigError, match="LLM_MODEL_DEFAULT"):
        prod(llm_model_default=" ")


def test_openai_key_never_appears_in_the_public_dict() -> None:
    settings = prod(openai_api_key="sk-super-secret-value")
    assert "sk-super-secret-value" not in str(settings.public_dict())
    assert "openai_api_key" not in settings.public_dict()


def test_task_model_override_falls_back_to_the_default() -> None:
    settings = Settings(_env_file=None, llm_model_default="base", llm_model_extract_facts="mini")
    assert settings.llm_model_for("interpret_command") == "base"
    assert settings.llm_model_for("extract_fact_candidates") == "mini"


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


def test_production_defaults_to_the_real_provider_only() -> None:
    settings = prod()
    assert settings.instagram_providers == {"meta"}
    assert settings.allow_simulated_workspaces is False


def test_mock_provider_needs_allow_simulated_workspaces_in_production() -> None:
    with pytest.raises(ConfigError, match="ALLOW_SIMULATED_WORKSPACES"):
        prod(instagram_enabled_providers="meta,mock", mock_instagram_app_secret="s")


def test_mock_provider_is_accepted_for_demo_workspaces_with_a_real_secret() -> None:
    settings = prod(
        instagram_enabled_providers="meta,mock",
        allow_simulated_workspaces=True,
        mock_instagram_app_secret="mock-secret",
    )
    assert settings.instagram_providers == {"meta", "mock"}


def test_mock_secret_must_be_set_explicitly_in_production() -> None:
    with pytest.raises(ConfigError, match="MOCK_INSTAGRAM_APP_SECRET"):
        prod(instagram_enabled_providers="mock", allow_simulated_workspaces=True)


def test_meta_needs_its_secrets_in_production() -> None:
    with pytest.raises(ConfigError, match="META_APP_SECRET"):
        prod(meta_app_secret="")
    with pytest.raises(ConfigError, match="META_WEBHOOK_VERIFY_TOKEN"):
        prod(meta_webhook_verify_token="")


def test_unknown_instagram_provider_kinds_are_refused() -> None:
    with pytest.raises(ConfigError, match="unknown kinds"):
        prod(instagram_enabled_providers="meta,whatsapp")


def test_instagram_secrets_are_not_in_the_public_settings() -> None:
    public = prod().public_dict()
    for name in ("mock_instagram_app_secret", "meta_webhook_verify_token", "meta_app_secret"):
        assert name not in public


def test_local_media_storage_is_refused_when_meta_is_enabled() -> None:
    with pytest.raises(ConfigError, match="MEDIA_STORAGE_BACKEND"):
        prod(media_storage_backend="local")


def test_local_media_storage_is_fine_for_a_mock_only_production_demo() -> None:
    settings = prod(
        instagram_enabled_providers="mock",
        allow_simulated_workspaces=True,
        mock_instagram_app_secret="mock-secret",
        media_storage_backend="local",
    )
    assert settings.media_storage_backend == "local"
