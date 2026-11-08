"""Calendar provider lookup by kind (ADR-010)."""

from collections.abc import Callable

from sqlalchemy.orm import Session

from app.core.clock import Clock
from app.core.config import Settings
from app.core.security import TokenCryptoError, TokenKeyRing, account_token_aad
from app.integrations.calendar.base import CalendarProvider, CalendarRef
from app.integrations.calendar.errors import CalendarAuthError
from app.integrations.calendar.google import GoogleCalendarProvider
from app.integrations.calendar.mock import MockCalendarProvider
from app.integrations.calendar.models import CalendarConnection


class CalendarProviderNotEnabled(Exception):
    """The calendar provider kind is unknown or disabled by configuration."""


def enabled_calendar_kinds(settings: Settings) -> frozenset[str]:
    return settings.calendar_providers


def calendar_ref(connection: CalendarConnection, settings: Settings) -> CalendarRef:
    """Capture encrypted values/IDs while loaded; no ORM access or DB during requests."""
    if connection.provider_kind != "google":
        return CalendarRef(
            connection_id=connection.id,
            workspace_id=connection.workspace_id,
            calendar_id=connection.calendar_id,
        )
    blob = connection.token_ciphertext
    refresh_blob = connection.refresh_token_ciphertext
    key_id = connection.token_key_id
    aad = account_token_aad(connection.workspace_id, connection.id)
    keys = settings.token_encryption_keys
    active_id = settings.token_encryption_active_key_id

    def token() -> str:
        if blob is None or key_id is None:
            raise CalendarAuthError("TOKEN_UNAVAILABLE")
        try:
            return TokenKeyRing(keys.get_secret_value(), active_id).decrypt(blob, key_id, aad=aad)
        except TokenCryptoError:
            raise CalendarAuthError("TOKEN_UNAVAILABLE") from None

    def refresh_token() -> str:
        if refresh_blob is None or key_id is None:
            raise CalendarAuthError("REFRESH_TOKEN_UNAVAILABLE")
        try:
            return TokenKeyRing(keys.get_secret_value(), active_id).decrypt(
                refresh_blob, key_id, aad=aad
            )
        except TokenCryptoError:
            raise CalendarAuthError("REFRESH_TOKEN_UNAVAILABLE") from None

    return CalendarRef(
        connection_id=connection.id,
        workspace_id=connection.workspace_id,
        calendar_id=connection.calendar_id,
        token_provider=token,
        refresh_token_provider=refresh_token,
    )


def get_calendar_provider(
    kind: str,
    *,
    settings: Settings,
    session_factory: Callable[[], Session],
    clock: Clock,
) -> CalendarProvider:
    if kind not in enabled_calendar_kinds(settings):
        raise CalendarProviderNotEnabled(kind)
    if kind == "mock":
        return MockCalendarProvider(session_factory, clock)
    if kind == "google":
        return GoogleCalendarProvider(
            clock,
            settings.google_client_id,
            settings.google_client_secret.get_secret_value(),
        )
    raise CalendarProviderNotEnabled(kind)
