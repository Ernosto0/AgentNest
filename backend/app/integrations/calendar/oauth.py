"""Google Calendar OAuth2 exchange and metadata lookup."""

import logging
from dataclasses import dataclass, field
from urllib.parse import urlencode

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.core.config import Settings
from app.integrations.calendar.errors import CalendarAuthError, CalendarTransientError

GOOGLE_CALENDAR_SCOPES = (
    "https://www.googleapis.com/auth/calendar.events",
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/userinfo.email",
)


@dataclass(frozen=True)
class GoogleCalendarTokenResult:
    access_token: str = field(repr=False)
    refresh_token: str | None = field(repr=False)
    expires_in_seconds: int
    external_account_id: str
    account_email: str | None
    calendar_id: str
    calendar_summary: str | None
    calendar_timezone: str | None
    granted_scopes: list[str]


class _TokenResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")
    access_token: str = Field(min_length=1, repr=False)
    refresh_token: str | None = Field(default=None, repr=False)
    expires_in: int = Field(gt=0, le=366 * 86400)
    scope: str = ""


class _UserInfoResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str | None = None
    sub: str | None = None
    email: str | None = None


class _CalendarMetadataResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(min_length=1)
    summary: str | None = None
    timeZone: str | None = None


def build_authorize_url(settings: Settings, state: str) -> str:
    return "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(
        {
            "client_id": settings.google_client_id,
            "redirect_uri": settings.google_oauth_redirect_uri,
            "response_type": "code",
            "scope": " ".join(GOOGLE_CALENDAR_SCOPES),
            "access_type": "offline",
            "prompt": "consent",
            "include_granted_scopes": "true",
            "state": state,
        }
    )


def compute_capabilities(granted_scopes: list[str]) -> dict[str, bool]:
    has_events = "https://www.googleapis.com/auth/calendar.events" in granted_scopes or (
        "https://www.googleapis.com/auth/calendar" in granted_scopes
    )
    has_read = has_events or "https://www.googleapis.com/auth/calendar.readonly" in granted_scopes
    return {
        "availability_read": has_read,
        "event_create": has_events,
        "event_update": has_events,
        "event_cancel": has_events,
    }


def exchange_code_for_tokens(
    settings: Settings, code: str, *, transport: httpx.BaseTransport | None = None
) -> GoogleCalendarTokenResult:
    for name in ("httpx", "httpcore"):
        logging.getLogger(name).setLevel(logging.WARNING)
    try:
        with httpx.Client(
            transport=transport, timeout=15, follow_redirects=False, trust_env=False
        ) as client:
            token_resp = client.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "client_id": settings.google_client_id,
                    "client_secret": settings.google_client_secret.get_secret_value(),
                    "grant_type": "authorization_code",
                    "redirect_uri": settings.google_oauth_redirect_uri,
                    "code": code,
                },
            )
            _check(token_resp)
            token_data = _TokenResponse.model_validate(token_resp.json())

            headers = {"Authorization": f"Bearer {token_data.access_token}"}
            user_resp = client.get(
                "https://www.googleapis.com/oauth2/v2/userinfo",
                headers=headers,
            )
            _check(user_resp)
            user_info = _UserInfoResponse.model_validate(user_resp.json())

            cal_resp = client.get(
                "https://www.googleapis.com/calendar/v3/calendars/primary",
                headers=headers,
            )
            _check(cal_resp)
            cal_meta = _CalendarMetadataResponse.model_validate(cal_resp.json())

            account_email = user_info.email or cal_meta.id
            external_id = user_info.id or user_info.sub or account_email
            if not external_id:
                raise CalendarTransientError("PROVIDER_UNAVAILABLE")

            scopes = sorted({s.strip() for s in token_data.scope.split() if s.strip()})
            if not scopes:
                scopes = list(GOOGLE_CALENDAR_SCOPES)

            return GoogleCalendarTokenResult(
                access_token=token_data.access_token,
                refresh_token=token_data.refresh_token,
                expires_in_seconds=token_data.expires_in,
                external_account_id=external_id,
                account_email=account_email,
                calendar_id=cal_meta.id,
                calendar_summary=cal_meta.summary or account_email,
                calendar_timezone=cal_meta.timeZone,
                granted_scopes=scopes,
            )
    except (httpx.HTTPError, ValueError, ValidationError):
        raise CalendarTransientError("PROVIDER_UNAVAILABLE") from None


def _check(response: httpx.Response) -> None:
    if response.status_code in (400, 401, 403):
        raise CalendarAuthError("ACCOUNT_NEEDS_REAUTH")
    if response.status_code != 200:
        raise CalendarTransientError("PROVIDER_UNAVAILABLE")
