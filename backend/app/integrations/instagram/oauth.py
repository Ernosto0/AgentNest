"""Instagram Login exchange. Synthetic offline contracts; live research remains pending."""

import logging
from dataclasses import dataclass, field
from urllib.parse import urlencode

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.core.config import Settings
from app.integrations.instagram.errors import ProviderAuthError, ProviderTransientError

SCOPES = (
    "instagram_business_basic",
    "instagram_business_manage_messages",
    "instagram_business_content_publish",
)


@dataclass(frozen=True)
class TokenExchangeResult:
    access_token: str = field(repr=False)
    expires_in_seconds: int
    ig_user_id: str
    granted_scopes: list[str]


class _Short(BaseModel):
    model_config = ConfigDict(strict=True)
    access_token: str = Field(min_length=1, repr=False)
    user_id: str | int
    permissions: list[str] = Field(default_factory=list)


class _Long(BaseModel):
    model_config = ConfigDict(strict=True)
    access_token: str = Field(min_length=1, repr=False)
    expires_in: int = Field(gt=0, le=366 * 86400)


def build_authorize_url(settings: Settings, state: str) -> str:
    return "https://www.instagram.com/oauth/authorize?" + urlencode(
        {
            "client_id": settings.meta_app_id,
            "redirect_uri": settings.meta_oauth_redirect_uri,
            "response_type": "code",
            "scope": ",".join(SCOPES),
            "state": state,
        }
    )


def compute_capabilities(granted_scopes: list[str], stories_enabled: bool) -> dict[str, bool]:
    return {
        "messaging": SCOPES[1] in granted_scopes,
        "publish_feed_image": SCOPES[2] in granted_scopes,
        "publish_story_image": SCOPES[2] in granted_scopes and stories_enabled,
    }


def exchange_code_for_long_lived_token(
    settings: Settings, code: str, *, transport: httpx.BaseTransport | None = None
) -> TokenExchangeResult:
    # Install before the FIRST exchange; both code and long-lived endpoints carry secrets.
    for name in ("httpx", "httpcore"):
        logging.getLogger(name).setLevel(logging.WARNING)
    try:
        with httpx.Client(
            transport=transport, timeout=15, follow_redirects=False, trust_env=False
        ) as client:
            short_response = client.post(
                "https://api.instagram.com/oauth/access_token",
                data={
                    "client_id": settings.meta_app_id,
                    "client_secret": settings.meta_app_secret.get_secret_value(),
                    "grant_type": "authorization_code",
                    "redirect_uri": settings.meta_oauth_redirect_uri,
                    "code": code,
                },
            )
            _check(short_response)
            body = short_response.json()
            if isinstance(body, dict) and "data" in body:
                if "access_token" in body or "user_id" in body:
                    raise ProviderTransientError("PROVIDER_UNAVAILABLE")
                data = body["data"]
                if not isinstance(data, list) or len(data) != 1:
                    raise ProviderTransientError("PROVIDER_UNAVAILABLE")
                body = data[0]
            short = _Short.model_validate(body)
            if isinstance(short.user_id, bool) or not str(short.user_id):
                raise ProviderTransientError("PROVIDER_UNAVAILABLE")
            long_response = client.get(
                "https://graph.instagram.com/access_token",
                params={
                    "grant_type": "ig_exchange_token",
                    "client_secret": settings.meta_app_secret.get_secret_value(),
                    "access_token": short.access_token,
                },
            )
            _check(long_response)
            long = _Long.model_validate(long_response.json())
            return TokenExchangeResult(
                long.access_token,
                long.expires_in,
                str(short.user_id),
                sorted(set(short.permissions)),
            )
    except (httpx.HTTPError, ValueError, ValidationError):
        raise ProviderTransientError("PROVIDER_UNAVAILABLE") from None


def _check(response: httpx.Response) -> None:
    if response.status_code in (400, 401, 403):
        raise ProviderAuthError("ACCOUNT_NEEDS_REAUTH")
    if response.status_code != 200:
        raise ProviderTransientError("PROVIDER_UNAVAILABLE")
