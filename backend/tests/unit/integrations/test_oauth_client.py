"""Synthetic OAuth shapes, credential safety and actual-scope capability detection."""

import logging
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from pydantic import SecretStr

from app.integrations.instagram.errors import ProviderAuthError, ProviderTransientError
from app.integrations.instagram.oauth import (
    SCOPES,
    build_authorize_url,
    compute_capabilities,
    exchange_code_for_long_lived_token,
)


def test_authorize_and_capabilities(settings):
    query = parse_qs(urlsplit(build_authorize_url(settings, "opaque-state")).query)
    assert query["state"] == ["opaque-state"]
    assert query["scope"] == [",".join(SCOPES)]
    assert not any(compute_capabilities([], True).values())
    assert compute_capabilities([SCOPES[2]], False) == {
        "messaging": False,
        "publish_feed_image": True,
        "publish_story_image": False,
    }


@pytest.mark.parametrize("wrapped", [False, True])
@pytest.mark.parametrize("permissions", [[], list(SCOPES)])
def test_exchange_uses_fixed_endpoints_and_never_assumes_requested_scopes(
    settings, wrapped, permissions, caplog
):
    cfg = settings.model_copy(update={"meta_app_secret": SecretStr("synthetic-secret")})
    calls = []
    short = {"access_token": "synthetic-short", "user_id": 123, "permissions": permissions}

    def handle(request):
        calls.append(request)
        if request.method == "POST":
            assert request.url.host == "api.instagram.com"
            assert b"code=synthetic-code" in request.content
            return httpx.Response(200, json={"data": [short]} if wrapped else short)
        assert request.url.host == "graph.instagram.com"
        if request.url.path == "/access_token":
            assert request.url.params["access_token"] == "synthetic-short"
            return httpx.Response(
                200, json={"access_token": "synthetic-long", "expires_in": 5184000}
            )
        assert request.url.path == f"/{cfg.meta_graph_api_version}/me"
        assert dict(request.url.params) == {"fields": "user_id"}
        assert request.headers["Authorization"] == "Bearer synthetic-long"
        return httpx.Response(200, json={"id": "123", "user_id": "canonical-456"})

    with caplog.at_level(logging.DEBUG):
        result = exchange_code_for_long_lived_token(
            cfg, "synthetic-code", transport=httpx.MockTransport(handle)
        )
    assert result.ig_user_id == "canonical-456" and result.granted_scopes == sorted(permissions)
    assert len(calls) == 3
    assert "synthetic-long" not in repr(result)
    for value in ("synthetic-secret", "synthetic-short", "synthetic-long", "synthetic-code"):
        assert value not in caplog.text


@pytest.mark.parametrize("body", [{}, {"id": "exchange-only"}, {"user_id": True}, {"user_id": ""}])
def test_invalid_token_owner_never_falls_back_to_exchange_identifier(settings, body):
    def handle(request):
        if request.method == "POST":
            return httpx.Response(200, json={"access_token": "short", "user_id": "exchange-id"})
        if request.url.path == "/access_token":
            return httpx.Response(200, json={"access_token": "private-long", "expires_in": 5184000})
        return httpx.Response(200, json=body)

    with pytest.raises(ProviderTransientError) as exc:
        exchange_code_for_long_lived_token(settings, "code", transport=httpx.MockTransport(handle))
    assert "private-long" not in str(exc.value)


def test_token_owner_authorization_failure_is_not_accepted(settings):
    def handle(request):
        if request.method == "POST":
            return httpx.Response(200, json={"access_token": "short", "user_id": "exchange-id"})
        if request.url.path == "/access_token":
            return httpx.Response(200, json={"access_token": "private-long", "expires_in": 5184000})
        return httpx.Response(403, json={"error": "private-provider-error"})

    with pytest.raises(ProviderAuthError) as exc:
        exchange_code_for_long_lived_token(settings, "code", transport=httpx.MockTransport(handle))
    assert "private-provider-error" not in str(exc.value)


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"data": []},
        {"data": [{}, {}]},
        {"access_token": "secret", "user_id": True},
        {"access_token": "secret", "user_id": "123", "permissions": "all"},
        {
            "access_token": "secret",
            "user_id": "123",
            "data": [{"access_token": "other", "user_id": "456"}],
        },
    ],
)
def test_malformed_short_response_is_safe(settings, body):
    with pytest.raises(ProviderTransientError) as exc:
        exchange_code_for_long_lived_token(
            settings,
            "private-code",
            transport=httpx.MockTransport(lambda r: httpx.Response(200, json=body)),
        )
    assert "secret" not in str(exc.value) and (
        exc.value.__context__ is None or exc.value.__suppress_context__
    )


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"access_token": "secret", "expires_in": True},
        {"access_token": "secret", "expires_in": 0},
    ],
)
def test_malformed_long_response_is_safe(settings, body):
    def handle(request):
        return httpx.Response(
            200,
            json={"access_token": "short", "user_id": "123"} if request.method == "POST" else body,
        )

    with pytest.raises(ProviderTransientError):
        exchange_code_for_long_lived_token(settings, "code", transport=httpx.MockTransport(handle))


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (400, ProviderAuthError),
        (401, ProviderAuthError),
        (403, ProviderAuthError),
        (429, ProviderTransientError),
        (500, ProviderTransientError),
        (302, ProviderTransientError),
    ],
)
def test_error_body_is_not_propagated(settings, status, expected):
    with pytest.raises(expected) as exc:
        exchange_code_for_long_lived_token(
            settings,
            "code",
            transport=httpx.MockTransport(
                lambda r: httpx.Response(status, json={"error_message": "sensitive-token"})
            ),
        )
    assert "sensitive-token" not in str(exc.value)
