"""Sentry-compatible error reporting with privacy scrubbing (P8-07, ADR-018, ADR-025).

Optional error tracking enabled only when ``SENTRY_DSN`` is configured.
Strictly enforces privacy and data-protection controls:
- ``send_default_pii = False``
- Strips Authorization, Cookie, and proxy headers from event payloads.
- Recursively masks sensitive fields matching ``_is_sensitive_key`` (tokens, passwords, secrets).
- Strips personal email, IP address, and customer identifiers.
"""

from collections.abc import MutableMapping, MutableSequence
from typing import Any

from app.core.config import Settings
from app.core.logging import _is_sensitive_key, get_logger, redact_value

_log = get_logger("app.sentry")

STRIPPED_HEADERS = {
    "authorization",
    "cookie",
    "set-cookie",
    "x-forwarded-for",
    "x-real-ip",
    "proxy-authorization",
}


def scrub_sentry_event(
    event: MutableMapping[str, Any], hint: MutableMapping[str, Any] | None = None
) -> MutableMapping[str, Any] | None:
    """Scrub PII, tokens, secrets, cookies, and sensitive headers from Sentry event payloads."""
    # 1. Scrub request data
    request = event.get("request")
    if isinstance(request, MutableMapping):
        headers = request.get("headers")
        if isinstance(headers, MutableMapping):
            for h in list(headers.keys()):
                if str(h).lower() in STRIPPED_HEADERS or _is_sensitive_key(str(h)):
                    headers[h] = "[REDACTED]"
        cookies = request.get("cookies")
        if cookies:
            request["cookies"] = "[REDACTED]"
        data = request.get("data")
        if data is not None:
            request["data"] = redact_value(data)

    # 2. Scrub user info (INV-18: never send customer/user email, ip, or handle)
    user = event.get("user")
    if isinstance(user, MutableMapping):
        user.pop("email", None)
        user.pop("ip_address", None)
        user.pop("username", None)

    # 3. Scrub extra metadata
    extra = event.get("extra")
    if isinstance(extra, MutableMapping):
        event["extra"] = redact_value(extra)

    # 4. Scrub contexts
    contexts = event.get("contexts")
    if isinstance(contexts, MutableMapping):
        event["contexts"] = redact_value(contexts)

    # 5. Scrub breadcrumbs
    breadcrumbs = event.get("breadcrumbs")
    if isinstance(breadcrumbs, MutableMapping):
        values = breadcrumbs.get("values")
        if isinstance(values, MutableSequence):
            for b in values:
                if isinstance(b, MutableMapping) and "data" in b:
                    b["data"] = redact_value(b["data"])
    elif isinstance(breadcrumbs, MutableSequence):
        for b in breadcrumbs:
            if isinstance(b, MutableMapping) and "data" in b:
                b["data"] = redact_value(b["data"])

    return event


def init_sentry(settings: Settings) -> bool:
    """Initialize Sentry SDK if ``SENTRY_DSN`` is configured with privacy scrubbing."""
    dsn = settings.sentry_dsn.get_secret_value().strip()
    if not dsn:
        return False

    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration
    except ImportError:
        _log.warning("sentry_sdk_not_available")
        return False

    sentry_sdk.init(
        dsn=dsn,
        environment=settings.app_env,
        release=f"{settings.product_name.lower()}@0.1.0",
        traces_sample_rate=0.0,
        before_send=scrub_sentry_event,  # type: ignore[arg-type]
        integrations=[
            FastApiIntegration(transaction_style="endpoint"),
            SqlalchemyIntegration(),
        ],
    )
    _log.info("sentry_initialized", environment=settings.app_env)
    return True
