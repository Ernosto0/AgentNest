"""Where job handlers get their LLM provider and settings.

A job handler only receives a session factory and a clock, so the process-wide provider is
resolved here: built once from ``LLM_PROVIDER`` (the deterministic fake by default). Tests
swap it with ``override_runtime`` to script model output or change limits.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache

from sqlalchemy.orm import Session, sessionmaker

from app.ai.runner import RunnerDeps
from app.core.clock import Clock
from app.core.config import Settings, get_settings
from app.integrations.llm import LLMProvider, build_provider

_provider_override: LLMProvider | None = None
_settings_override: Settings | None = None


@lru_cache
def _default_provider() -> LLMProvider:
    return build_provider(get_settings())


def get_provider() -> LLMProvider:
    return _provider_override or _default_provider()


def get_runtime_settings() -> Settings:
    return _settings_override or get_settings()


def runner_deps(session_factory: sessionmaker[Session], clock: Clock) -> RunnerDeps:
    return RunnerDeps(session_factory, clock, get_provider(), get_runtime_settings())


@contextmanager
def override_runtime(
    *, provider: LLMProvider | None = None, settings: Settings | None = None
) -> Iterator[None]:
    """Use ``provider`` / ``settings`` for jobs run inside the block (tests)."""
    global _provider_override, _settings_override
    saved = (_provider_override, _settings_override)
    _provider_override = provider or _provider_override
    _settings_override = settings or _settings_override
    try:
        yield
    finally:
        _provider_override, _settings_override = saved


def reset_default_provider() -> None:
    """Forget the cached provider (after changing environment in tests)."""
    _default_provider.cache_clear()
