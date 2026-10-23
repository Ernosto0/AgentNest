"""Synthetic offline Graph contracts: request shapes, safety, response/error taxonomy."""

import json
import logging
import traceback
import uuid
from datetime import timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest
from structlog.testing import capture_logs

from app.core.clock import FrozenClock
from app.core.config import Settings
from app.core.security import TokenKeyRing, account_token_aad
from app.integrations.instagram.base import AccountRef, ContainerSpec, TokenInfo
from app.integrations.instagram.error_mapping import response_error
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
from app.integrations.instagram.meta import MetaInstagramProvider
from app.integrations.instagram.models import SocialAccount
from app.integrations.instagram.registry import account_ref, get_provider

FIXTURES = Path(__file__).parents[2] / "contract" / "fixtures" / "meta"
TOKEN = "synthetic-sensitive-bearer"


def fixture(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES / f"{name}.json").read_text())


class API:
    def __init__(self, clock: FrozenClock, data: Any = None, status: int = 200) -> None:
        self.requests: list[httpx.Request] = []
        self.data, self.status = data, status
        self.failure: type[httpx.RequestError] | None = None
        self.raw: bytes | None = None
        self.tokens = 0
        self.account = AccountRef(uuid.uuid4(), uuid.uuid4(), "biz-1", self.token)
        self.provider = MetaInstagramProvider(
            clock, "synthetic-app-secret", "v25.0", transport=httpx.MockTransport(self.handle)
        )

    def token(self) -> str:
        self.tokens += 1
        return TOKEN

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        assert request.url.host == "graph.instagram.com"
        assert request.extensions["timeout"]["read"] == 15.0
        if self.failure:
            raise self.failure(f"untrusted-url?access_token={TOKEN}", request=request)
        if self.raw is not None:
            return httpx.Response(self.status, content=self.raw)
        return httpx.Response(self.status, json=self.data, headers={"Retry-After": "45"})


@pytest.mark.parametrize(
    ("method", "name", "path", "params", "body"),
    [
        ("get_account_profile", "profile_ok", "biz-1", {"fields": "user_id,username"}, None),
        (
            "send_text_message",
            "send_ok",
            "biz-1/messages",
            {},
            {"recipient": {"id": "customer-1"}, "message": {"text": "Merhaba"}},
        ),
        (
            "create_media_container",
            "container_create_ok",
            "biz-1/media",
            {},
            {"image_url": "https://example.test/image.jpg", "caption": "caption"},
        ),
        (
            "publish_container",
            "publish_ok",
            "biz-1/media_publish",
            {},
            {"creation_id": "container-1"},
        ),
        (
            "get_container_status",
            "container_status_finished",
            "container-1",
            {"fields": "id,status_code,status"},
            None,
        ),
        ("get_media", "media_ok", "media-1", {"fields": "id,permalink,timestamp"}, None),
        (
            "get_publishing_quota",
            "publishing_limit_ok",
            "biz-1/content_publishing_limit",
            {"fields": "config,quota_usage"},
            None,
        ),
    ],
)
def test_requests_and_typed_success(
    clock: FrozenClock, method: str, name: str, path: str, params: dict[str, str], body: Any
) -> None:
    api = API(clock, fixture(name))
    args = {
        "send_text_message": ("customer-1", "Merhaba"),
        "create_media_container": (
            ContainerSpec("IMAGE", "https://example.test/image.jpg", "caption"),
        ),
        "publish_container": ("container-1",),
        "get_container_status": ("container-1",),
        "get_media": ("media-1",),
    }.get(method, ())
    result = getattr(api.provider, method)(api.account, *args)
    assert result is not None
    (request,) = api.requests
    assert request.url.path == f"/v25.0/{path}"
    assert dict(request.url.params) == params
    assert request.headers["Authorization"] == f"Bearer {TOKEN}"
    assert request.method == ("POST" if body is not None else "GET")
    if body is not None:
        assert json.loads(request.content) == body
    assert api.tokens == 1


@pytest.mark.parametrize("state", ["in_progress", "finished", "published", "error", "expired"])
def test_all_container_states(clock: FrozenClock, state: str) -> None:
    api = API(clock, fixture(f"container_status_{state}"))
    value = api.provider.get_container_status(api.account, "container-1")
    assert value.status_code == state.upper()
    assert value.media_id is None
    assert bool(value.error_detail) == (state == "error")


def test_quota_and_refresh_use_response_and_clock(
    clock: FrozenClock, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    api = API(clock, fixture("publishing_limit_ok"))
    quota = api.provider.get_publishing_quota(api.account)
    assert (quota.used, quota.limit, quota.window_hours) == (2, 50, 24)
    api.data = fixture("refresh_token_ok")
    result = api.provider.refresh_token(api.account)
    assert result.expires_at == clock.now() + timedelta(days=60)
    assert result.access_token == "synthetic-refreshed-token"
    assert result.access_token not in repr(result)
    assert TokenInfo(None).access_token is None
    request = api.requests[-1]
    assert request.url.path == "/refresh_access_token"
    assert dict(request.url.params) == {"grant_type": "ig_refresh_token", "access_token": TOKEN}
    assert "Authorization" not in request.headers
    assert TOKEN not in caplog.text
    assert "synthetic-refreshed-token" not in caplog.text


@pytest.mark.parametrize(
    "call",
    [
        lambda a: a.provider.send_text_message(a.account, "customer-1", "é" * 501),
        lambda a: a.provider.send_text_message(a.account, "customer-1", " "),
        lambda a: a.provider.create_media_container(
            a.account, ContainerSpec("IMAGE", "localmedia:x")
        ),
        lambda a: a.provider.create_media_container(
            a.account, ContainerSpec("IMAGE", "http://example.test/a.jpg")
        ),
        lambda a: a.provider.create_media_container(
            a.account, ContainerSpec("STORIES", "https://example.test/a.jpg", "")
        ),
        lambda a: a.provider.create_media_container(
            a.account, ContainerSpec("STORIES", "https://example.test/a.jpg", "text")
        ),
        lambda a: a.provider.get_media(a.account, "https://evil.test/?access_token=x"),
    ],
)
def test_local_validation_before_decryption_or_network(clock: FrozenClock, call: Any) -> None:
    api = API(clock)
    with pytest.raises(ProviderInvalidRequest):
        call(api)
    assert api.requests == [] and api.tokens == 0


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("auth_expired_190", ProviderAuthError),
        ("permission_10", ProviderPermissionError),
        ("window_closed_2534022", ProviderWindowClosed),
        ("rate_limit_4", ProviderRateLimited),
        ("invalid_media_36000", ProviderInvalidRequest),
        ("invalid_request_100", ProviderInvalidRequest),
    ],
)
def test_all_error_fixtures(clock: FrozenClock, name: str, expected: type[ProviderError]) -> None:
    data = fixture(f"error_{name}")
    data["error"]["message"] = f"secret-response-text {TOKEN}"
    api = API(clock, data, 400)
    with pytest.raises(expected) as error:
        api.provider.send_text_message(api.account, "customer-1", "Merhaba")
    rendered = "".join(traceback.format_exception(error.value))
    assert TOKEN not in rendered and "secret-response-text" not in rendered
    assert len(api.requests) == 1


@pytest.mark.parametrize(
    ("status", "code", "subcode", "expected"),
    [
        (401, 100, None, ProviderAuthError),
        (403, 100, None, ProviderPermissionError),
        (400, 294, None, ProviderPermissionError),
        (400, 10, 2534022, ProviderWindowClosed),
        (400, 100, 2207051, ProviderRateLimited),
        (429, 100, None, ProviderRateLimited),
        *[(400, c, None, ProviderRateLimited) for c in (4, 17, 32, 613)],
        *[(400, c, None, ProviderInvalidRequest) for c in range(36000, 36005)],
        (400, 100, 2207001, ProviderInvalidRequest),
        (400, 100, 2207085, ProviderInvalidRequest),
        (503, 190, None, ProviderOutcomeUnknown),
    ],
)
def test_taxonomy_and_precedence(
    status: int, code: int, subcode: int | None, expected: type[ProviderError]
) -> None:
    error = response_error(
        status, {"error": {"code": code, "error_subcode": subcode}}, "45", ambiguous=True
    )
    assert isinstance(error, expected)
    if isinstance(error, ProviderRateLimited):
        assert error.retry_after_s == 45


def test_window_text_detection_and_safe_fallbacks() -> None:
    assert isinstance(
        response_error(
            400, {"error": {"code": 10, "message": "outside the 24 hour messaging window"}}
        ),
        ProviderWindowClosed,
    )
    assert isinstance(
        response_error(400, {"error": {"is_transient": True}}), ProviderTransientError
    )
    assert response_error(400, {"error": {"code": 100}}).request_code == "PROVIDER_REJECTED"  # type: ignore[union-attr]
    assert response_error(400, {"error": {"code": 36004}}).request_code == "MEDIA_REJECTED"  # type: ignore[union-attr]
    assert response_error(200, {}) is None


@pytest.mark.parametrize("call", ["send", "publish", "profile", "create", "refresh"])
@pytest.mark.parametrize(
    "failure",
    [
        httpx.ConnectError,
        httpx.ConnectTimeout,
        httpx.PoolTimeout,
        httpx.ReadTimeout,
        httpx.WriteError,
        httpx.ReadError,
        httpx.RemoteProtocolError,
    ],
)
def test_transport_ambiguity_no_retries_no_secrets(
    clock: FrozenClock,
    call: str,
    failure: type[httpx.RequestError],
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    api = API(clock)
    api.failure = failure
    ambiguous = call in ("send", "publish") and failure not in (
        httpx.ConnectError,
        httpx.ConnectTimeout,
        httpx.PoolTimeout,
    )
    with pytest.raises(ProviderOutcomeUnknown if ambiguous else ProviderTransientError) as error:
        invoke(api, call)
    assert len(api.requests) == 1
    assert TOKEN not in "".join(traceback.format_exception(error.value)) + caplog.text


def invoke(api: API, call: str) -> Any:
    return {
        "send": lambda: api.provider.send_text_message(api.account, "customer-1", "Merhaba"),
        "publish": lambda: api.provider.publish_container(api.account, "container-1"),
        "profile": lambda: api.provider.get_account_profile(api.account),
        "create": lambda: api.provider.create_media_container(
            api.account, ContainerSpec("IMAGE", "https://example.test/a.jpg")
        ),
        "refresh": lambda: api.provider.refresh_token(api.account),
    }[call]()


@pytest.mark.parametrize("call", ["send", "publish", "profile", "create", "refresh"])
@pytest.mark.parametrize(
    "data", [{}, [], {"id": None}, {"id": 1}, {"access_token": TOKEN, "expires_in": "bad"}, None]
)
def test_malformed_success_has_safe_typed_error(clock: FrozenClock, call: str, data: Any) -> None:
    api = API(clock, data)
    with pytest.raises(
        ProviderOutcomeUnknown if call in ("send", "publish") else ProviderTransientError
    ):
        invoke(api, call)
    assert len(api.requests) == 1


@pytest.mark.parametrize("call", ["send", "publish", "profile", "create", "refresh"])
@pytest.mark.parametrize("status", [200, 302, 503])
def test_invalid_json_redirect_and_5xx_follow_ambiguity_rule(
    clock: FrozenClock, call: str, status: int
) -> None:
    api = API(clock, status=status)
    api.raw = b"invalid-sensitive-response"
    with pytest.raises(
        ProviderOutcomeUnknown if call in ("send", "publish") else ProviderTransientError
    ):
        invoke(api, call)
    assert len(api.requests) == 1


def test_lookup_filters_sender_recipient_and_time(clock: FrozenClock) -> None:
    data = fixture("conversations_messages_ok")
    message = data["data"][0]["messages"]["data"][0]
    data["data"][0]["messages"]["data"] += [
        dict(message, id="inbound", **{"from": {"id": "customer-1"}}),
        dict(message, id="other", to={"data": [{"id": "other"}]}),
        dict(message, id="old", created_time="2025-01-01T00:00:00+00:00"),
    ]
    api = API(clock, data)
    found = api.provider.find_recent_outbound(api.account, "customer-1", clock.now())
    assert [(v.message_id, v.text, v.sent_at) for v in found] == [
        ("meta-mid-1", "Merhaba", clock.now())
    ]
    assert dict(api.requests[0].url.params) == {
        "user_id": "customer-1",
        "fields": "messages{id,from,to,message,created_time}",
    }


def test_safe_cursor_pagination_ignores_remote_next_urls(clock: FrozenClock) -> None:
    data = fixture("conversations_messages_ok")
    data["paging"] = {
        "next": f"https://evil.test/?access_token={TOKEN}",
        "cursors": {"after": "cursor-1"},
    }
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.url.host == "graph.instagram.com"
        return httpx.Response(200, json=data if len(requests) == 1 else {"data": []})

    api = API(clock)
    api.provider = MetaInstagramProvider(
        clock, "secret", "v25.0", transport=httpx.MockTransport(handler)
    )
    assert len(api.provider.find_recent_outbound(api.account, "customer-1", clock.now())) == 1
    assert requests[1].url.params["after"] == "cursor-1"


def test_encrypted_snapshot_is_lazy_detached_and_authenticates_aad(clock: FrozenClock) -> None:
    settings = Settings(
        _env_file=None,
        token_encryption_keys="k1:" + "a2tra2tra2tra2tra2tra2tra2tra2tra2tra2tra2s=",
        token_encryption_active_key_id="k1",
    )
    ring = TokenKeyRing(settings.token_encryption_keys.get_secret_value(), "k1")
    row = SocialAccount(
        id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        external_account_id="biz-1",
        provider_kind="meta",
    )
    row.token_ciphertext, row.token_key_id = ring.encrypt(
        TOKEN, aad=account_token_aad(row.workspace_id, row.id)
    )
    ref = account_ref(row, settings)
    row.token_ciphertext = None
    assert ref.token_provider is not None and ref.token_provider() == TOKEN
    assert TOKEN not in repr(ref)
    bad = account_ref(row, settings)
    with pytest.raises(ProviderAuthError):
        bad.token_provider()  # type: ignore[misc]
    row.token_ciphertext, row.token_key_id = ring.encrypt(TOKEN, aad=b"wrong-workspace")
    bad = account_ref(row, settings)
    with pytest.raises(ProviderAuthError):
        bad.token_provider()  # type: ignore[misc]


def test_registry_resolves_enabled_meta(clock: FrozenClock) -> None:
    settings = Settings(_env_file=None).model_copy(update={"instagram_enabled_providers": "meta"})
    provider = get_provider("meta", settings=settings, clock=clock, session_factory=lambda: None)  # type: ignore[arg-type]
    assert provider.kind == "meta"


@pytest.mark.parametrize("call", ["send", "publish"])
def test_malformed_success_logs_actual_unknown_outcome(clock: FrozenClock, call: str) -> None:
    api = API(clock, {})
    with capture_logs() as logs, pytest.raises(ProviderOutcomeUnknown):
        invoke(api, call)
    assert len(logs) == 1
    assert logs[0]["operation"] == ("send_text_message" if call == "send" else "publish_container")
    assert logs[0]["provider_kind"] == "meta"
    assert logs[0]["outcome"] == "OUTCOME_UNKNOWN"
    assert logs[0]["duration_ms"] >= 0


@pytest.mark.parametrize("value", ["garbage", "-1", "9" * 100, "9" * 5000, "四"])
def test_untrusted_retry_after_is_safe(value: str) -> None:
    error = response_error(429, {}, value)
    assert isinstance(error, ProviderRateLimited) and error.retry_after_s is None


def test_http_date_retry_after_uses_injected_clock(clock: FrozenClock) -> None:
    error = response_error(429, {}, "Thu, 15 Jan 2026 12:01:00 GMT", now=clock.now())
    assert isinstance(error, ProviderRateLimited) and error.retry_after_s == 60
    error = response_error(429, {}, "Thu, 15 Jan 3000 12:01:00 GMT", now=clock.now())
    assert isinstance(error, ProviderRateLimited) and error.retry_after_s is None


@pytest.mark.parametrize("error_node", [[], "bad", {}])
def test_malformed_error_envelope_on_200_is_ambiguous(clock: FrozenClock, error_node: Any) -> None:
    api = API(clock, {"error": error_node})
    with pytest.raises(ProviderOutcomeUnknown):
        invoke(api, "send")


def test_malformed_media_url_is_typed_before_request(clock: FrozenClock) -> None:
    api = API(clock)
    with capture_logs() as logs, pytest.raises(ProviderInvalidRequest):
        api.provider.create_media_container(api.account, ContainerSpec("IMAGE", "https://[bad"))
    assert api.tokens == 0 and api.requests == []
    assert logs[0]["outcome"] == "PROVIDER_REJECTED"


def test_unexpected_error_does_not_log_success(
    clock: FrozenClock, monkeypatch: pytest.MonkeyPatch
) -> None:
    api = API(clock)

    def fail(*args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("synthetic failure")

    monkeypatch.setattr(api.provider, "_request", fail)
    with capture_logs() as logs, pytest.raises(RuntimeError):
        api.provider.get_account_profile(api.account)
    assert logs[0]["outcome"] == "PROVIDER_ERROR"
