"""Provider lookup by kind (ADR-010). The kind comes from the webhook path or the account row."""

from collections.abc import Callable

from sqlalchemy.orm import Session

from app.core.clock import Clock
from app.core.config import Settings
from app.core.security import TokenCryptoError, TokenKeyRing, account_token_aad
from app.integrations.instagram.base import AccountRef, InstagramProvider
from app.integrations.instagram.errors import ProviderAuthError
from app.integrations.instagram.meta import MetaInstagramProvider
from app.integrations.instagram.mock import MockInstagramProvider
from app.integrations.instagram.models import SocialAccount
from app.integrations.instagram.webhook_format import WebhookCodec
from app.integrations.storage.base import MediaStorage, MediaStorageUnavailable
from app.integrations.storage.registry import get_media_storage


class ProviderNotEnabled(Exception):
    """The provider kind is unknown, disabled by configuration, or not built yet."""


def enabled_kinds(settings: Settings) -> frozenset[str]:
    return settings.instagram_providers


def account_ref(account: SocialAccount, settings: Settings) -> AccountRef:
    """Capture encrypted values/IDs while loaded; no ORM access or DB during requests.

    Only the callable decrypts. It captures neither the ORM row nor its Session, and
    translates unavailable/tampered ciphertext into a content-free auth error.
    """
    if account.provider_kind != "meta":
        return AccountRef(account.id, account.workspace_id, account.external_account_id)
    blob, key_id = account.token_ciphertext, account.token_key_id
    aad = account_token_aad(account.workspace_id, account.id)
    keys = settings.token_encryption_keys
    active_id = settings.token_encryption_active_key_id

    def token() -> str:
        if blob is None or key_id is None:
            raise ProviderAuthError("TOKEN_UNAVAILABLE")
        try:
            return TokenKeyRing(keys.get_secret_value(), active_id).decrypt(blob, key_id, aad=aad)
        except TokenCryptoError:
            raise ProviderAuthError("TOKEN_UNAVAILABLE") from None

    return AccountRef(account.id, account.workspace_id, account.external_account_id, token)


def get_webhook_codec(kind: str, settings: Settings) -> WebhookCodec:
    """Signature verification and parsing for a webhook path. Needs no database."""
    if kind not in enabled_kinds(settings):
        raise ProviderNotEnabled(kind)
    if kind == "mock":
        return WebhookCodec(settings.mock_instagram_app_secret.get_secret_value())
    if kind == "meta":
        return WebhookCodec(settings.meta_app_secret.get_secret_value())
    raise ProviderNotEnabled(kind)


def _mock_storage(settings: Settings, clock: Clock) -> MediaStorage | None:
    """The storage the mock reads publishing images from (plan G3). A backend that is not built
    yet (``s3``) leaves it out, so messaging keeps working; only publishing then fails."""
    try:
        return get_media_storage(settings, clock)
    except MediaStorageUnavailable:
        return None


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
        return MockInstagramProvider(
            session_factory,
            clock,
            secret,
            storage=_mock_storage(settings, clock),
            container_delay_s=settings.sim_container_delay_seconds,
            daily_publish_limit=settings.publish_daily_limit,
        )
    if kind == "meta":
        return MetaInstagramProvider(
            clock, settings.meta_app_secret.get_secret_value(), settings.meta_graph_api_version
        )
    raise ProviderNotEnabled(kind)
