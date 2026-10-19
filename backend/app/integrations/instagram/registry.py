"""Provider lookup by kind (ADR-010). The kind comes from the webhook path or the account row."""

from collections.abc import Callable

from sqlalchemy.orm import Session

from app.core.clock import Clock
from app.core.config import Settings
from app.integrations.instagram.base import InstagramProvider
from app.integrations.instagram.mock import MockInstagramProvider


class ProviderNotEnabled(Exception):
    """The provider kind is unknown, disabled by configuration, or not built yet."""


def enabled_kinds(settings: Settings) -> frozenset[str]:
    return settings.instagram_providers


def get_provider(
    kind: str,
    *,
    settings: Settings,
    session_factory: Callable[[], Session],
    clock: Clock,
) -> InstagramProvider:
    if kind not in enabled_kinds(settings):
        raise ProviderNotEnabled(kind)
    if kind == "mock":
        secret = settings.mock_instagram_app_secret.get_secret_value()
        return MockInstagramProvider(session_factory, clock, secret)
    raise ProviderNotEnabled(f"{kind} (the Meta adapter arrives in Phase 7)")
