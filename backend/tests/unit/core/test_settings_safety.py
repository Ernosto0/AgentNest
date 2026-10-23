"""AC-X6: production refuses unsafe configuration (INV-20)."""

import base64
from pathlib import Path

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
        "META_APP_ID",
        "META_GRAPH_API_VERSION",
        "META_OAUTH_REDIRECT_URI",
        "META_STORIES_ENABLED",
        "TOKEN_ENCRYPTION_KEYS",
        "TOKEN_ENCRYPTION_ACTIVE_KEY_ID",
        "TOKEN_REFRESH_DAYS_BEFORE_EXPIRY",
        "MEDIA_PUBLIC_BASE_URL",
        "S3_ENDPOINT_URL",
        "S3_REGION",
        "S3_BUCKET",
        "S3_ACCESS_KEY_ID",
        "S3_SECRET_ACCESS_KEY",
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
        "meta_app_id": "test-meta-app",
        "meta_webhook_verify_token": "verify-token",
        "token_encryption_keys": "k1:" + base64.b64encode(b"k" * 32).decode(),
        "token_encryption_active_key_id": "k1",
        "media_storage_backend": "s3",  # Meta needs a public URL; local is refused with it
        "s3_bucket": "test-bucket",
        "s3_access_key_id": "synthetic-access-key",
        "s3_secret_access_key": "synthetic-secret-key",
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


# --- Phase 6 settings (retention) ------------------------------------------------------------

RETENTION_DEFAULTS = {
    "retention_webhook_payload_days": 30,
    "retention_inbound_event_row_days": 90,
    "retention_agent_input_days": 30,
    "retention_message_text_days": 365,
    "retention_notifications_read_days": 90,
    "retention_jobs_succeeded_days": 7,
    "retention_jobs_dead_days": 90,
    "retention_media_orphan_days": 7,
    "retention_published_media_days": 90,
}


def test_the_retention_defaults_are_the_documented_ones_in_every_environment() -> None:
    development = Settings(_env_file=None)
    assert {name: getattr(development, name) for name in RETENTION_DEFAULTS} == RETENTION_DEFAULTS
    # Production needs nothing extra for them: the safe defaults apply.
    production = prod()
    assert {name: getattr(production, name) for name in RETENTION_DEFAULTS} == RETENTION_DEFAULTS


def test_there_is_no_audit_retention_setting() -> None:
    """Audit rows are never purged in Phase 6 (plan H17): no variable may suggest otherwise."""
    assert not [name for name in Settings.model_fields if "audit" in name]


@pytest.mark.parametrize("name", sorted(RETENTION_DEFAULTS))
def test_a_retention_period_below_one_day_is_refused(name: str) -> None:
    for bad in (0, -5):
        with pytest.raises(ValueError):
            Settings(_env_file=None, **{name: bad})  # type: ignore[arg-type]


def test_retention_periods_are_read_from_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RETENTION_MESSAGE_TEXT_DAYS", "400")
    monkeypatch.setenv("RETENTION_MEDIA_ORPHAN_DAYS", "3")
    settings = Settings(_env_file=None)
    assert settings.retention_message_text_days == 400
    assert settings.retention_media_orphan_days == 3


def test_retention_settings_are_public_numbers_not_secrets() -> None:
    dumped = prod().public_dict()
    assert {name: dumped[name] for name in RETENTION_DEFAULTS} == RETENTION_DEFAULTS


def test_every_retention_variable_is_in_the_example_env_and_the_docs() -> None:
    root = Path(__file__).resolve().parents[4]
    example = (root / ".env.example").read_text(encoding="utf-8")
    docs = (root / "docs" / "operations" / "environment-variables.md").read_text(encoding="utf-8")
    for name in RETENTION_DEFAULTS:
        variable = name.upper()
        assert f"{variable}=" in example, f"{variable} is missing from .env.example"
        assert f"`{variable}`" in docs, f"{variable} is missing from environment-variables.md"


# --- Phase 7 foundations -------------------------------------------------------------------

PHASE7_FIELDS = (
    "meta_app_id",
    "meta_graph_api_version",
    "meta_oauth_redirect_uri",
    "meta_stories_enabled",
    "token_encryption_keys",
    "token_encryption_active_key_id",
    "token_refresh_days_before_expiry",
    "media_public_base_url",
    "s3_endpoint_url",
    "s3_region",
    "s3_bucket",
    "s3_access_key_id",
    "s3_secret_access_key",
)


def test_phase7_defaults_preserve_the_credential_free_local_demo() -> None:
    settings = Settings(_env_file=None)
    assert settings.instagram_providers == {"mock"}
    assert settings.media_storage_backend == "local"
    assert settings.meta_app_id == ""
    assert settings.meta_graph_api_version == "v25.0"
    assert settings.meta_oauth_redirect_uri == "http://localhost:8000/oauth/instagram/callback"
    assert settings.meta_stories_enabled is True
    assert settings.token_encryption_keys.get_secret_value() == ""
    assert settings.token_encryption_active_key_id == ""
    assert settings.token_refresh_days_before_expiry == 20
    assert settings.media_public_base_url == ""
    assert settings.s3_endpoint_url == ""
    assert settings.s3_region == "auto"
    assert settings.safety_problems() == []


@pytest.mark.parametrize("environment", ["development", "test", "production"])
@pytest.mark.parametrize(
    ("field", "error"),
    [
        ("meta_app_id", "META_APP_ID"),
        ("meta_app_secret", "META_APP_SECRET"),
        ("meta_webhook_verify_token", "META_WEBHOOK_VERIFY_TOKEN"),
        ("meta_oauth_redirect_uri", "META_OAUTH_REDIRECT_URI"),
        ("token_encryption_keys", "TOKEN_ENCRYPTION_KEYS"),
        ("token_encryption_active_key_id", "TOKEN_ENCRYPTION_ACTIVE_KEY_ID"),
    ],
)
def test_meta_requires_credentials_and_keys_in_every_environment(
    environment: str, field: str, error: str
) -> None:
    with pytest.raises(ConfigError, match=error):
        prod(app_env=environment, instagram_enabled_providers="meta", **{field: ""})


@pytest.mark.parametrize("environment", ["development", "test", "production"])
def test_a_tunnel_setting_does_not_make_local_media_public(environment: str) -> None:
    with pytest.raises(ConfigError, match="public local-media serving is not implemented"):
        prod(
            app_env=environment,
            instagram_enabled_providers="meta",
            media_storage_backend="local",
            media_public_base_url="https://tunnel.example.test",
        )


@pytest.mark.parametrize("environment", ["development", "test", "production"])
@pytest.mark.parametrize(
    "field", ["s3_bucket", "s3_region", "s3_access_key_id", "s3_secret_access_key"]
)
def test_s3_requires_its_configuration_even_without_meta(environment: str, field: str) -> None:
    with pytest.raises(ConfigError, match=field.upper()):
        prod(
            app_env=environment,
            instagram_enabled_providers="mock",
            allow_simulated_workspaces=True,
            mock_instagram_app_secret="mock-secret",
            **{field: " "},
        )


def test_meta_verification_token_must_be_explicit_not_the_development_placeholder() -> None:
    with pytest.raises(ConfigError, match="META_WEBHOOK_VERIFY_TOKEN"):
        Settings(_env_file=None, instagram_enabled_providers="meta")


@pytest.mark.parametrize("environment", ["development", "test", "production"])
def test_optional_keys_are_validated_even_when_meta_is_disabled(environment: str) -> None:
    with pytest.raises(ConfigError, match="TOKEN_ENCRYPTION_KEYS"):
        prod(
            app_env=environment,
            instagram_enabled_providers="",
            token_encryption_keys="secret-bad-key",
        )


def test_phase7_secrets_do_not_appear_in_public_settings_or_config_errors() -> None:
    settings = prod()
    public = settings.public_dict()
    for name in ("token_encryption_keys", "s3_access_key_id", "s3_secret_access_key"):
        assert name not in public
        assert getattr(settings, name).get_secret_value() not in str(public)
    with pytest.raises(ConfigError) as info:
        prod(token_encryption_keys="do-not-disclose-this-input")
    assert "do-not-disclose-this-input" not in str(info.value)


@pytest.mark.parametrize("days", [0, -1])
def test_token_refresh_horizon_must_be_positive(days: int) -> None:
    with pytest.raises(ValueError):
        Settings(_env_file=None, token_refresh_days_before_expiry=days)


def test_phase7_environment_variables_are_read_and_documented(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("META_GRAPH_API_VERSION", "v99.0")
    monkeypatch.setenv("META_STORIES_ENABLED", "false")
    monkeypatch.setenv("TOKEN_REFRESH_DAYS_BEFORE_EXPIRY", "7")
    settings = Settings(_env_file=None)
    assert settings.meta_graph_api_version == "v99.0"
    assert settings.meta_stories_enabled is False
    assert settings.token_refresh_days_before_expiry == 7
    root = Path(__file__).resolve().parents[4]
    example = (root / ".env.example").read_text(encoding="utf-8")
    docs = (root / "docs/operations/environment-variables.md").read_text(encoding="utf-8")
    for name in PHASE7_FIELDS:
        assert f"{name.upper()}=" in example
        assert f"`{name.upper()}`" in docs
