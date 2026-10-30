"""Application settings and production safety checks (ADR-017).

One ``Settings`` class reads environment variables (and ``.env`` in development).
In ``production`` the defaults are safe and unsafe combinations refuse to start.
Checks for variables introduced in later phases are added in those phases.
"""

import ipaddress
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url

from app.core.security import TokenCryptoError, TokenKeyRing

REPO_ROOT = Path(__file__).resolve().parents[3]

# Development-only placeholders. Production refuses the example secret key.
EXAMPLE_SECRET_KEY = "dev-only-change-me-dev-only-change-me"  # noqa: S105
DEFAULT_DATABASE_URL = "postgresql+psycopg://agentnest:agentnest@localhost:5433/agentnest"
DEFAULT_TEST_DATABASE_URL = "postgresql+psycopg://agentnest:agentnest@localhost:5433/agentnest_test"
MIN_SECRET_KEY_BYTES = 32

# Never included in ``Settings.public_dict()`` (logs, /meta, diagnostics).
_SECRET_FIELDS = frozenset(
    {
        "secret_key",
        "demo_password",
        "database_url",
        "migration_database_url",
        "test_database_url",
        "openai_api_key",
        "mock_instagram_app_secret",
        "meta_webhook_verify_token",
        "meta_app_secret",
        "token_encryption_keys",
        "s3_access_key_id",
        "s3_secret_access_key",
        "smtp_url",
        "sentry_dsn",
    }
)

# Per-task model overrides: task name -> Settings field (agent-runtime.md §10).
LLM_TASK_MODEL_FIELDS: dict[str, str] = {
    "interpret_command": "llm_model_interpret_command",
    "draft_reply": "llm_model_draft_reply",
    "draft_content": "llm_model_draft_content",
    "extract_fact_candidates": "llm_model_extract_facts",
}


class ConfigError(RuntimeError):
    """Raised at startup when the configuration is unsafe for the environment."""

    def __init__(self, problems: list[str]) -> None:
        self.problems = problems
        super().__init__("Refusing to start, unsafe configuration:\n- " + "\n- ".join(problems))


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=REPO_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",  # .env also holds variables of later phases
        case_sensitive=False,
    )

    app_env: Literal["development", "test", "production"] = "development"
    database_url: str = DEFAULT_DATABASE_URL
    migration_database_url: str = ""
    test_database_url: str = DEFAULT_TEST_DATABASE_URL
    secret_key: SecretStr = SecretStr(EXAMPLE_SECRET_KEY)
    frontend_origin: str = "http://localhost:5173"
    app_base_url: str = "http://localhost:8000"
    product_name: str = "AgentNest"
    cookie_secure: bool = False
    session_ttl_hours: int = Field(default=336, ge=1)
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    log_format: Literal["console", "json"] = "console"
    demo_tools_enabled: bool = True
    demo_password: SecretStr = SecretStr("demo-password")
    worker_concurrency: int = Field(default=2, ge=1)
    worker_poll_interval_seconds: float = Field(default=1.0, gt=0)
    job_lease_seconds: int = Field(default=120, ge=1)

    # --- AI (Phase 3, ADR-009). The default keeps the demo credential-free (INV-14). ---
    llm_provider: Literal["fake", "openai"] = "fake"
    openai_api_key: SecretStr = SecretStr("")
    llm_model_default: str = "gpt-6-luna"
    llm_model_interpret_command: str = ""  # empty = use llm_model_default
    llm_model_draft_reply: str = ""
    llm_model_draft_content: str = ""
    llm_model_extract_facts: str = ""
    llm_timeout_seconds: float = Field(default=30.0, gt=0)
    llm_max_calls_per_workspace_per_day: int = Field(default=500, ge=1)
    # Reasoning models spend output tokens on reasoning; keep it low for short structured tasks.
    llm_reasoning_effort: Literal["", "minimal", "low", "medium", "high"] = "low"
    # Optional JSON ``{"<model>": {"input_per_mtok": 0.0, "output_per_mtok": 0.0}}`` (USD) for
    # cost estimates in evals and system health. Unknown models have no estimate.
    llm_price_table: str = ""

    # --- Instagram (Phase 4, ADR-010). Mock only by default (INV-14). ---
    # Comma-separated provider kinds that may be connected and that receive webhooks.
    instagram_enabled_providers: str = "mock"
    # Permits mock accounts on ``is_demo`` workspaces in production.
    allow_simulated_workspaces: bool = True
    # Development placeholders; production requires real values for the enabled providers.
    mock_instagram_app_secret: SecretStr = SecretStr("dev-mock-instagram-app-secret")
    meta_webhook_verify_token: SecretStr = SecretStr("dev-meta-webhook-verify-token")
    meta_app_secret: SecretStr = SecretStr("")
    # Phase 7 foundations. Enabling Meta requires explicit credentials in every environment.
    meta_app_id: str = ""
    meta_graph_api_version: str = "v25.0"
    meta_oauth_redirect_uri: str = "http://localhost:8000/oauth/instagram/callback"
    meta_stories_enabled: bool = True
    token_encryption_keys: SecretStr = SecretStr("")
    token_encryption_active_key_id: str = ""
    token_refresh_days_before_expiry: int = Field(default=20, ge=1)
    reply_debounce_seconds: int = Field(default=8, ge=0)
    send_reconcile_window_minutes: int = Field(default=10, ge=1)
    # Circuit breaker (Phase 6, workflows.md G.2): N transient failures within the window
    # open it (``degraded``); the cooldown is how long the account is left alone before a probe.
    circuit_failure_threshold: int = Field(default=5, ge=1)
    circuit_window_minutes: int = Field(default=10, ge=1)
    circuit_cooldown_minutes: int = Field(default=10, ge=1)

    # --- Media (Phase 5, ADR-015). The local backend keeps the demo credential-free. ---
    media_storage_backend: Literal["local", "s3"] = "local"
    # Relative paths resolve against ``backend/`` (see ``media_root``).
    media_local_root: str = "./var/media"
    media_max_image_bytes: int = Field(default=8_388_608, ge=1)
    media_public_url_ttl_seconds: int = Field(default=3600, ge=1)
    # Reserved for a future secured local-media tunnel contract; does not enable Meta/local.
    media_public_base_url: str = ""
    s3_endpoint_url: str = ""  # Empty selects AWS's default endpoint.
    s3_region: str = "auto"
    s3_bucket: str = ""
    s3_access_key_id: SecretStr = SecretStr("")
    s3_secret_access_key: SecretStr = SecretStr("")

    # --- Mock publishing (Phase 5, integrations.md §3.3) ---
    sim_container_delay_seconds: int = Field(default=2, ge=0)
    publish_daily_limit: int = Field(default=50, ge=1)

    # --- Retention (Phase 6, security-and-privacy.md section 8). Global values; per-workspace
    # values are deferred. There is no audit setting: audit rows are never purged (plan H17). ---
    retention_webhook_payload_days: int = Field(default=30, ge=1)
    retention_inbound_event_row_days: int = Field(default=90, ge=1)
    retention_agent_input_days: int = Field(default=30, ge=1)
    retention_message_text_days: int = Field(default=365, ge=1)
    retention_customer_memory_days: int = Field(default=365, ge=1)
    retention_notifications_read_days: int = Field(default=90, ge=1)
    retention_jobs_succeeded_days: int = Field(default=7, ge=1)
    retention_jobs_dead_days: int = Field(default=90, ge=1)
    retention_media_orphan_days: int = Field(default=7, ge=1)
    retention_published_media_days: int = Field(default=90, ge=1)

    # --- Production hardening, proxy boundary, email & monitoring (Phase 8, ADR-025) ---
    trusted_proxy_cidrs: str = "127.0.0.1/32,::1/128"
    smtp_url: SecretStr = SecretStr("")
    mail_from: str = ""
    operator_alert_email: str = ""
    sentry_dsn: SecretStr = SecretStr("")

    @field_validator("log_level", mode="before")
    @classmethod
    def _upper_log_level(cls, value: Any) -> Any:
        return value.upper() if isinstance(value, str) else value

    @model_validator(mode="after")
    def _apply_environment_rules(self) -> "Settings":
        explicit = self.model_fields_set
        # Production defaults are safe; explicit unsafe values are refused below.
        if self.app_env == "production":
            if "demo_tools_enabled" not in explicit:
                self.demo_tools_enabled = False
            if "cookie_secure" not in explicit:
                self.cookie_secure = True
            if "log_format" not in explicit:
                self.log_format = "json"
            if "allow_simulated_workspaces" not in explicit:
                self.allow_simulated_workspaces = False
            if "instagram_enabled_providers" not in explicit:
                self.instagram_enabled_providers = "meta"
        problems = self.safety_problems()
        if problems:
            raise ConfigError(problems)
        return self

    def safety_problems(self) -> list[str]:
        """Provider/storage safety applies everywhere; production has extra deployment checks."""
        problems = self._instagram_problems()
        keys = self.token_encryption_keys.get_secret_value()
        if keys or self.token_encryption_active_key_id or "meta" in self.instagram_providers:
            try:
                TokenKeyRing(keys, self.token_encryption_active_key_id)
            except TokenCryptoError as exc:
                problems.append(str(exc))
        if self.media_storage_backend == "s3":
            for name in ("s3_bucket", "s3_region", "s3_access_key_id", "s3_secret_access_key"):
                value = getattr(self, name)
                raw = value.get_secret_value() if isinstance(value, SecretStr) else value
                if not raw.strip():
                    problems.append(f"{name.upper()} must be set when MEDIA_STORAGE_BACKEND=s3.")
        if "meta" in self.instagram_providers and self.media_storage_backend != "s3":
            problems.append(
                "MEDIA_STORAGE_BACKEND must be 's3' when 'meta' is enabled; "
                "public local-media serving is not implemented."
            )
        for entry in self.trusted_proxy_cidrs.split(","):
            cidr = entry.strip()
            if not cidr:
                continue
            try:
                ipaddress.ip_network(cidr, strict=False)
            except ValueError:
                problems.append(f"TRUSTED_PROXY_CIDRS contains an invalid IP or CIDR: {cidr!r}.")
        if self.smtp_url.get_secret_value().strip() and not self.mail_from.strip():
            problems.append("MAIL_FROM must be set when SMTP_URL is configured.")
        if self.app_env != "production":
            return problems
        secret = self.secret_key.get_secret_value()
        if "secret_key" not in self.model_fields_set or not secret:
            problems.append("SECRET_KEY must be set in production.")
        elif secret == EXAMPLE_SECRET_KEY:
            problems.append("SECRET_KEY must not be the example value in production.")
        elif len(secret.encode()) < MIN_SECRET_KEY_BYTES:
            problems.append(f"SECRET_KEY must be at least {MIN_SECRET_KEY_BYTES} bytes.")
        if "database_url" not in self.model_fields_set:
            problems.append("DATABASE_URL must be set explicitly in production.")
        if self.demo_tools_enabled:
            problems.append("DEMO_TOOLS_ENABLED must be false in production.")
        if not self.cookie_secure:
            problems.append("COOKIE_SECURE must be true in production.")
        if self.llm_provider == "fake":
            problems.append("LLM_PROVIDER must not be 'fake' in production.")
        elif not self.openai_api_key.get_secret_value():
            problems.append("OPENAI_API_KEY must be set when LLM_PROVIDER=openai.")
        if self.llm_provider == "openai" and not self.llm_model_default.strip():
            problems.append("LLM_MODEL_DEFAULT must be set when LLM_PROVIDER=openai.")
        return problems

    @property
    def effective_migration_database_url(self) -> str:
        """Database URL used by Alembic migrations (falls back to ``database_url``)."""
        return self.migration_database_url.strip() or self.database_url

    @property
    def trusted_proxy_networks(
        self,
    ) -> tuple[ipaddress.IPv4Network | ipaddress.IPv6Network, ...]:
        """Parsed trusted proxy CIDRs that are permitted to supply forwarded client IPs."""
        return tuple(
            ipaddress.ip_network(entry.strip(), strict=False)
            for entry in self.trusted_proxy_cidrs.split(",")
            if entry.strip()
        )

    @property
    def media_root(self) -> Path:
        """``MEDIA_LOCAL_ROOT`` as an absolute path (relative values are under ``backend/``)."""
        root = Path(self.media_local_root)
        return root if root.is_absolute() else (REPO_ROOT / "backend" / root).resolve()

    @property
    def instagram_providers(self) -> frozenset[str]:
        """The enabled provider kinds (``mock``, ``meta``)."""
        return frozenset(
            p.strip().lower() for p in self.instagram_enabled_providers.split(",") if p.strip()
        )

    def _instagram_problems(self) -> list[str]:
        problems: list[str] = []
        kinds = self.instagram_providers
        unknown = kinds - {"mock", "meta"}
        if unknown:
            problems.append(f"INSTAGRAM_ENABLED_PROVIDERS has unknown kinds: {sorted(unknown)}.")
        explicit = self.model_fields_set
        if "mock" in kinds and self.app_env == "production":
            if not self.allow_simulated_workspaces:
                problems.append(
                    "INSTAGRAM_ENABLED_PROVIDERS contains 'mock' in production, which requires "
                    "ALLOW_SIMULATED_WORKSPACES=true."
                )
            if "mock_instagram_app_secret" not in explicit or not (
                self.mock_instagram_app_secret.get_secret_value()
            ):
                problems.append("MOCK_INSTAGRAM_APP_SECRET must be set when 'mock' is enabled.")
        if "meta" in kinds:
            if not self.meta_app_id.strip():
                problems.append("META_APP_ID must be set when 'meta' is enabled.")
            if not self.meta_app_secret.get_secret_value().strip():
                problems.append("META_APP_SECRET must be set when 'meta' is enabled.")
            if "meta_webhook_verify_token" not in explicit or not (
                self.meta_webhook_verify_token.get_secret_value().strip()
            ):
                problems.append("META_WEBHOOK_VERIFY_TOKEN must be set when 'meta' is enabled.")
            if not self.meta_oauth_redirect_uri.strip():
                problems.append("META_OAUTH_REDIRECT_URI must be set when 'meta' is enabled.")
        return problems

    def llm_model_for(self, task: str) -> str:
        """The model for ``task``: its override if set, else the default."""
        field = LLM_TASK_MODEL_FIELDS.get(task)
        override = getattr(self, field) if field else ""
        return str(override or self.llm_model_default)

    def public_dict(self) -> dict[str, Any]:
        """Effective non-secret configuration, safe to log at startup."""
        data = {
            name: value for name, value in self.model_dump().items() if name not in _SECRET_FIELDS
        }
        data["database"] = make_url(self.database_url).render_as_string(hide_password=True)
        return data


@lru_cache
def get_settings() -> Settings:
    return Settings()


def validate_production_settings(settings: Settings | None = None) -> Settings:
    """Validate and return production-safe settings, raising ``ConfigError`` on any violation."""
    resolved = settings or get_settings()
    problems = list(resolved.safety_problems())
    if resolved.app_env != "production":
        problems.insert(0, "APP_ENV must be 'production' for production deployment.")
    if problems:
        raise ConfigError(problems)
    return resolved
