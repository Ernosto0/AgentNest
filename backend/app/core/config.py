"""Application settings and production safety checks (ADR-017).

One ``Settings`` class reads environment variables (and ``.env`` in development).
In ``production`` the defaults are safe and unsafe combinations refuse to start.
Checks for variables introduced in later phases are added in those phases.
"""

from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url

REPO_ROOT = Path(__file__).resolve().parents[3]

# Development-only placeholders. Production refuses the example secret key.
EXAMPLE_SECRET_KEY = "dev-only-change-me-dev-only-change-me"  # noqa: S105
DEFAULT_DATABASE_URL = "postgresql+psycopg://agentnest:agentnest@localhost:5433/agentnest"
DEFAULT_TEST_DATABASE_URL = "postgresql+psycopg://agentnest:agentnest@localhost:5433/agentnest_test"
MIN_SECRET_KEY_BYTES = 32

# Never included in ``Settings.public_dict()`` (logs, /meta, diagnostics).
_SECRET_FIELDS = frozenset({"secret_key", "demo_password", "database_url", "test_database_url"})


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

    @field_validator("log_level", mode="before")
    @classmethod
    def _upper_log_level(cls, value: Any) -> Any:
        return value.upper() if isinstance(value, str) else value

    @model_validator(mode="after")
    def _apply_environment_rules(self) -> "Settings":
        if self.app_env != "production":
            return self
        explicit = self.model_fields_set
        # Production defaults are safe; explicit unsafe values are refused below.
        if "demo_tools_enabled" not in explicit:
            self.demo_tools_enabled = False
        if "cookie_secure" not in explicit:
            self.cookie_secure = True
        if "log_format" not in explicit:
            self.log_format = "json"
        problems = self.safety_problems()
        if problems:
            raise ConfigError(problems)
        return self

    def safety_problems(self) -> list[str]:
        """Return the reasons this configuration is unsafe in production (empty otherwise)."""
        if self.app_env != "production":
            return []
        problems: list[str] = []
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
        return problems

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
