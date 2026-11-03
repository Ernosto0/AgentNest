"""Session 13 unit tests for Sentry error reporting and privacy scrubbing
(P8-07, ADR-018, ADR-025).
"""

from typing import Any

from pydantic import SecretStr

from app.core.config import Settings
from app.core.sentry import init_sentry, scrub_sentry_event


def test_init_sentry_returns_false_when_dsn_empty() -> None:
    settings = Settings(sentry_dsn=SecretStr(""))
    assert init_sentry(settings) is False


def test_init_sentry_initializes_when_dsn_configured() -> None:
    settings = Settings(sentry_dsn=SecretStr("https://pubkey@sentry.example.com/123"))
    # Should succeed or gracefully handle test environment
    result = init_sentry(settings)
    assert result is True


def test_scrub_sentry_event_strips_sensitive_headers_and_cookies() -> None:
    event: dict[str, Any] = {
        "request": {
            "url": "https://api.example.com/api/v1/auth/login",
            "headers": {
                "Authorization": "Bearer secret-token-xyz",
                "Cookie": "session_id=s-12345",
                "X-Forwarded-For": "203.0.113.195",
                "User-Agent": "Mozilla/5.0",
                "Accept": "application/json",
            },
            "cookies": "session_id=s-12345",
            "data": {
                "email": "user@example.com",
                "password": "super-secret-password-123",
                "csrf_token": "csrf-secret-abc",
                "normal_field": "visible_value",
            },
        }
    }

    scrubbed = scrub_sentry_event(event)
    assert scrubbed is not None

    headers = scrubbed["request"]["headers"]
    assert headers["Authorization"] == "[REDACTED]"
    assert headers["Cookie"] == "[REDACTED]"
    assert headers["X-Forwarded-For"] == "[REDACTED]"
    assert headers["User-Agent"] == "Mozilla/5.0"
    assert headers["Accept"] == "application/json"
    assert scrubbed["request"]["cookies"] == "[REDACTED]"

    data = scrubbed["request"]["data"]
    assert data["password"] == "[REDACTED]"
    assert data["csrf_token"] == "[REDACTED]"
    assert data["normal_field"] == "visible_value"


def test_scrub_sentry_event_strips_user_pii() -> None:
    event: dict[str, Any] = {
        "user": {
            "id": "u-12345-uuid",
            "email": "customer@business.com",
            "username": "customer_handle",
            "ip_address": "198.51.100.42",
        }
    }

    scrubbed = scrub_sentry_event(event)
    assert scrubbed is not None
    user = scrubbed["user"]
    assert user["id"] == "u-12345-uuid"
    assert "email" not in user
    assert "username" not in user
    assert "ip_address" not in user


def test_scrub_sentry_event_scrubs_extra_contexts_and_breadcrumbs() -> None:
    event: dict[str, Any] = {
        "extra": {
            "secret_key": "raw-key-value",
            "tokens": 42,  # tokens plural (usage count) must NOT be masked
            "access_token": "token-xyz",
            "count": 10,
        },
        "contexts": {
            "runtime": {"name": "cpython"},
            "auth": {"api_key": "sk-123456", "authenticated": True},
        },
        "breadcrumbs": {
            "values": [
                {"message": "user clicked", "data": {"auth_token": "token-val", "step": 1}},
                {"message": "query run", "data": {"status": "ok"}},
            ]
        },
    }

    scrubbed = scrub_sentry_event(event)
    assert scrubbed is not None

    extra = scrubbed["extra"]
    assert extra["secret_key"] == "[REDACTED]"
    assert extra["access_token"] == "[REDACTED]"
    assert extra["tokens"] == 42
    assert extra["count"] == 10

    auth_ctx = scrubbed["contexts"]["auth"]
    assert auth_ctx["api_key"] == "[REDACTED]"
    assert auth_ctx["authenticated"] is True

    crumbs = scrubbed["breadcrumbs"]["values"]
    assert crumbs[0]["data"]["auth_token"] == "[REDACTED]"
    assert crumbs[0]["data"]["step"] == 1
    assert crumbs[1]["data"]["status"] == "ok"
