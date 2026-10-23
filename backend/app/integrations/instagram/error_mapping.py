"""Content-free Graph/transport error translation; adapters never retry.

Mappings are provisional offline contracts until V-05 supplies real recordings.
Never include Graph messages, URLs, response bodies or transport exception text.
"""

import re
from datetime import datetime
from email.utils import parsedate_to_datetime
from typing import Any

import httpx

from app.integrations.instagram.errors import (
    ProviderAuthError,
    ProviderError,
    ProviderInvalidRequest,
    ProviderOutcomeUnknown,
    ProviderPermissionError,
    ProviderRateLimited,
    ProviderTransientError,
    ProviderWindowClosed,
)


def transport_error(error: httpx.RequestError, *, ambiguous: bool) -> ProviderError:
    if isinstance(error, httpx.ConnectError | httpx.ConnectTimeout | httpx.PoolTimeout):
        return ProviderTransientError("CONNECTION_UNAVAILABLE")
    return (
        ProviderOutcomeUnknown("RESPONSE_UNCONFIRMED")
        if ambiguous
        else ProviderTransientError("TRANSPORT_UNAVAILABLE")
    )


def malformed_response(*, ambiguous: bool) -> ProviderError:
    return (
        ProviderOutcomeUnknown("RESPONSE_UNCONFIRMED")
        if ambiguous
        else ProviderTransientError("INVALID_PROVIDER_RESPONSE")
    )


def response_error(
    status: int,
    body: Any,
    retry_after: str | None = None,
    *,
    ambiguous: bool = False,
    now: datetime | None = None,
) -> ProviderError | None:
    node = body.get("error") if isinstance(body, dict) else None
    error = node if isinstance(node, dict) else {}
    code, subcode = error.get("code"), error.get("error_subcode")
    message = error.get("message")
    window_message = isinstance(message, str) and bool(
        re.search(r"outside.*24\s*[- ]?\s*h(?:our)?|24\s*[- ]?\s*hour.*window", message, re.I)
    )
    # A gateway/transport 5xx cannot prove the side effect was rejected, regardless of body.
    if status >= 500:
        return malformed_response(ambiguous=True) if ambiguous else ProviderTransientError()
    if status == 401 or code == 190:
        return ProviderAuthError()
    if subcode == 2534022 or code == 2534022 or (code == 10 and window_message):
        return ProviderWindowClosed()
    if status == 429 or code in (4, 17, 32, 613, 80002) or subcode == 2207051:
        return ProviderRateLimited(_retry_after(retry_after, now))
    if status == 403 or code in (10, 200, 294):
        return ProviderPermissionError()
    if code in range(36000, 36005) or (isinstance(subcode, int) and 2207001 <= subcode <= 2207085):
        return ProviderInvalidRequest("MEDIA_REJECTED")
    if error.get("is_transient") is True:
        return ProviderTransientError()
    if status >= 400 or (node is not None and isinstance(code, int)):
        return ProviderInvalidRequest("PROVIDER_REJECTED")
    if node is not None:
        return malformed_response(ambiguous=ambiguous)
    if status >= 300:
        return malformed_response(ambiguous=ambiguous)
    return None


def _retry_after(value: str | None, now: datetime | None) -> int | None:
    if value is None:
        return None
    value = value.strip()
    if len(value) > 128:
        return None
    if value.isascii() and value.isdecimal():
        seconds = int(value)
        return seconds if seconds <= 2**31 - 1 else None
    if now is not None:
        try:
            date = parsedate_to_datetime(value)
            if date.tzinfo is not None:
                seconds = max(0, int((date - now).total_seconds()))
                return seconds if seconds <= 2**31 - 1 else None
        except (ValueError, TypeError, OverflowError):
            pass
    return None
