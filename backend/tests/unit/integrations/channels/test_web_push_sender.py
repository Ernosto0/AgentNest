"""F-01 part 2: the Web Push sender and its SSRF guard (no database, no network).

Proves: only known push-service hosts are contacted, a host that resolves to a private, loopback,
link-local, CGNAT or otherwise non-public address is refused on every send, redirects are never
followed, the timeout is short, push-service statuses map to the right outcome (404/410 revoke,
5xx/429/timeout retry), and the real ``pywebpush`` can encrypt and sign for a real subscriber key
against a fake transport. Nothing here opens a socket.
"""

import base64
import json
import socket
from typing import Any

import pytest
import requests
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from pywebpush import WebPushException, webpush

from app.core.security import generate_vapid_keys
from app.integrations.channels.web_push import endpoint_policy
from app.integrations.channels.web_push.endpoint_policy import (
    EndpointRefused,
    address_allowed,
    check_endpoint,
    host_allowed,
)
from app.integrations.channels.web_push.sender import (
    DEFAULT_TIMEOUT_SECONDS,
    _no_redirect_session,
    classify_status,
    send_web_push,
)

PUBLIC_IP = "142.250.185.74"
FCM = "https://fcm.googleapis.com/fcm/send/device-token-abc"


def resolver_to(*addresses: str):  # type: ignore[no-untyped-def]
    def resolve(host: str, port: int, **_: Any) -> list[tuple[Any, ...]]:
        return [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, port)) for address in addresses
        ]

    return resolve


def b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


@pytest.mark.parametrize(
    "host",
    [
        "fcm.googleapis.com",
        "updates.push.services.mozilla.com",
        "web.push.apple.com",
        "api.push.apple.com",
        "wns2-par02p.notify.windows.com",
        "FCM.GoogleAPIs.com",
    ],
)
def test_known_push_services_are_allowed(host: str) -> None:
    assert host_allowed(host)


@pytest.mark.parametrize(
    "host",
    [
        "evil.example.com",
        "googleapis.com",
        "evilfcm.googleapis.com.evil.example",
        "fcm.googleapis.com.evil.example",
        "push.services.mozilla.com",  # the bare suffix host itself is not a push endpoint
        "notify.windows.com",
        "xpush.apple.com",  # a look-alike without the dot boundary
        "127.0.0.1",
        "localhost",
        "169.254.169.254",
        "",
    ],
)
def test_other_hosts_are_refused(host: str) -> None:
    assert not host_allowed(host)


@pytest.mark.parametrize(
    "address",
    [
        "127.0.0.1",
        "10.0.0.5",
        "172.16.3.4",
        "192.168.1.1",
        "169.254.169.254",  # the cloud metadata address
        "100.64.0.1",  # carrier-grade NAT
        "0.0.0.0",  # noqa: S104  (a refused address, not a bind)
        "224.0.0.1",
        "::1",
        "fe80::1",
        "fc00::1",
        "::ffff:10.0.0.1",  # IPv4-mapped private
        "::ffff:127.0.0.1",
        "2002:0a00:0001::1",  # 6to4 wrapping 10.0.0.1
        "not-an-address",
    ],
)
def test_non_public_addresses_are_refused(address: str) -> None:
    assert not address_allowed(address)


@pytest.mark.parametrize("address", [PUBLIC_IP, "2a00:1450:4001:81b::200a"])
def test_public_addresses_are_allowed(address: str) -> None:
    assert address_allowed(address)


def test_an_allowlisted_host_on_a_public_address_passes() -> None:
    check_endpoint(FCM, resolver_to(PUBLIC_IP))


@pytest.mark.parametrize("address", ["127.0.0.1", "10.1.2.3", "169.254.169.254", "::1"])
def test_an_allowlisted_name_resolving_inward_is_refused_every_send(address: str) -> None:
    for _ in range(2):  # re-checked on every send, not remembered
        with pytest.raises(EndpointRefused) as refused:
            check_endpoint(FCM, resolver_to(address))
        assert refused.value.reason == "endpoint_address_not_public"
        assert not refused.value.permanent


def test_one_private_answer_among_public_ones_refuses() -> None:
    with pytest.raises(EndpointRefused):
        check_endpoint(FCM, resolver_to(PUBLIC_IP, "10.0.0.1"))


def test_dns_failure_is_transient_not_permanent() -> None:
    def broken(*_: Any, **__: Any) -> None:
        raise socket.gaierror("no such host")

    with pytest.raises(EndpointRefused) as refused:
        check_endpoint(FCM, broken)
    assert refused.value.reason == "endpoint_dns_failed" and not refused.value.permanent


@pytest.mark.parametrize(
    "endpoint",
    [
        "http://fcm.googleapis.com/fcm/send/x",  # not https
        "https://evil.example.com/push",
        "https://fcm.googleapis.com:8443/fcm/send/x",
        "https://user:pw@fcm.googleapis.com/fcm/send/x",
        "https://127.0.0.1/push",
        "https://[::1]/push",
        "ftp://fcm.googleapis.com/x",
        "https:///nohost",
        "not a url",
    ],
)
def test_static_endpoint_problems_are_permanent_and_never_resolve(endpoint: str) -> None:
    def must_not_resolve(*_: Any, **__: Any) -> None:
        raise AssertionError("resolved a host that is not allowed")

    with pytest.raises(EndpointRefused) as refused:
        check_endpoint(endpoint, must_not_resolve)
    assert refused.value.permanent


def test_the_allowlist_is_the_documented_one() -> None:
    assert set(endpoint_policy.ALLOWED_HOSTS) == {"fcm.googleapis.com"}
    assert set(endpoint_policy.ALLOWED_HOST_SUFFIXES) == {
        ".push.services.mozilla.com",
        ".push.apple.com",
        ".notify.windows.com",
    }


# --- sender: calls, outcomes ------------------------------------------------------------------

PUBLIC_KEY, PRIVATE_KEY = generate_vapid_keys()


class Response:
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code
        self.reason = "x"
        self.text = "body that must never be logged or returned"


def run(push_fn: Any, endpoint: str = FCM, **kwargs: Any) -> Any:
    return send_web_push(
        endpoint=endpoint,
        p256dh="p",
        auth="a",
        payload='{"title":"t"}',
        vapid_private_key=PRIVATE_KEY,
        vapid_subject="mailto:ops@example.com",
        ttl=3600,
        resolver=resolver_to(PUBLIC_IP),
        push_fn=push_fn,
        **kwargs,
    )


def test_a_push_is_sent_with_a_short_timeout_ttl_urgency_and_no_redirects() -> None:
    seen: dict[str, Any] = {}

    def push_fn(**kwargs: Any) -> Response:
        seen.update(kwargs)
        return Response(201)

    outcome = run(push_fn, urgency="high")
    assert outcome.kind == "sent" and outcome.status_code == 201
    assert seen["timeout"] == DEFAULT_TIMEOUT_SECONDS <= 10
    assert seen["ttl"] == 3600
    assert seen["headers"] == {"Urgency": "high"}
    assert seen["data"] == '{"title":"t"}'
    assert seen["requests_session"].max_redirects == 0
    assert seen["subscription_info"]["endpoint"] == FCM


def test_a_blocked_endpoint_is_never_sent_to() -> None:
    def push_fn(**_: Any) -> Response:
        raise AssertionError("must not send")

    outcome = send_web_push(
        endpoint=FCM,
        p256dh="p",
        auth="a",
        payload="{}",
        vapid_private_key=PRIVATE_KEY,
        vapid_subject="mailto:ops@example.com",
        ttl=60,
        resolver=resolver_to("10.0.0.9"),
        push_fn=push_fn,
    )
    assert outcome.kind == "refused" and not outcome.permanent
    outcome = run(push_fn, endpoint="https://evil.example.com/x")
    assert outcome.kind == "refused" and outcome.permanent


@pytest.mark.parametrize(
    ("status", "kind"),
    [
        (404, "gone"),
        (410, "gone"),
        (429, "retry"),
        (500, "retry"),
        (503, "retry"),
        (400, "failed"),
        (401, "failed"),
        (403, "failed"),
        (413, "failed"),
        (302, "failed"),
    ],
)
def test_statuses_map_to_outcomes(status: int, kind: str) -> None:
    def push_fn(**_: Any) -> Response:
        raise WebPushException("Push failed", response=Response(status))

    outcome = run(push_fn)
    assert outcome.kind == kind and outcome.status_code == status
    assert classify_status(status).kind == kind
    assert "body that must never" not in repr(outcome)


def test_timeouts_and_connection_errors_retry() -> None:
    for error in (requests.Timeout(FCM), requests.ConnectionError(FCM)):

        def push_fn(error: Exception = error, **_: Any) -> Response:
            raise error

        outcome = run(push_fn)
        assert outcome.kind == "retry"
        assert FCM not in repr(outcome)


def test_a_redirect_is_refused_not_followed() -> None:
    def push_fn(**_: Any) -> Response:
        raise requests.TooManyRedirects(FCM)

    outcome = run(push_fn)
    assert outcome.kind == "failed" and outcome.reason == "push_service_redirect_refused"


def test_the_session_really_refuses_to_follow_a_redirect() -> None:
    class RedirectingAdapter(requests.adapters.HTTPAdapter):
        sent: list[str] = []

        def send(self, request: requests.PreparedRequest, **kwargs: Any) -> requests.Response:
            self.sent.append(str(request.url))
            response = requests.Response()
            response.status_code = 302
            response.headers["Location"] = "http://169.254.169.254/latest/meta-data"
            response.url = str(request.url)
            response.request = request
            return response

    adapter = RedirectingAdapter()
    session = _no_redirect_session()
    session.mount("https://", adapter)
    with pytest.raises(requests.TooManyRedirects):
        session.post(FCM, data=b"x", timeout=1)
    assert adapter.sent == [FCM]  # the redirect target was never contacted


def test_an_unexpected_library_error_never_leaks_its_text() -> None:
    def push_fn(**_: Any) -> Response:
        raise ValueError(f"bad key for {FCM}")

    outcome = run(push_fn)
    assert outcome.kind == "failed" and FCM not in repr(outcome)


def test_an_unusable_vapid_key_is_a_failure_not_a_device_problem() -> None:
    outcome = send_web_push(
        endpoint=FCM,
        p256dh="p",
        auth="a",
        payload="{}",
        vapid_private_key="not a key",
        vapid_subject="mailto:ops@example.com",
        ttl=60,
        resolver=resolver_to(PUBLIC_IP),
        push_fn=lambda **_: Response(201),
    )
    assert outcome.kind == "failed" and outcome.reason == "vapid_key_unusable"


def test_the_real_library_encrypts_and_signs_for_a_real_subscriber_key() -> None:
    """pywebpush is not mocked: only the HTTP transport is, so the payload is really encrypted
    (aes128gcm) to a real P-256 subscriber key and the request carries a real VAPID header."""
    subscriber = ec.generate_private_key(ec.SECP256R1())
    p256dh = b64(
        subscriber.public_key().public_bytes(
            serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
        )
    )
    posted: dict[str, Any] = {}

    class FakeSession:
        def post(self, endpoint: str, timeout: float, data: bytes, headers: dict[str, str]) -> Any:
            posted.update(
                endpoint=endpoint,
                timeout=timeout,
                data=data,
                headers={k.lower(): v for k, v in headers.items()},
            )
            response = requests.Response()
            response.status_code = 201
            return response

    def push_fn(**kwargs: Any) -> Any:
        kwargs["requests_session"] = FakeSession()
        return webpush(**kwargs)

    payload = json.dumps({"title": "Onay", "body": "b", "url": "/w/x/approvals", "tag": "t"})
    outcome = send_web_push(
        endpoint=FCM,
        p256dh=p256dh,
        auth=b64(b"a" * 16),
        payload=payload,
        vapid_private_key=PRIVATE_KEY,
        vapid_subject="mailto:ops@example.com",
        ttl=3600,
        urgency="high",
        resolver=resolver_to(PUBLIC_IP),
        push_fn=push_fn,
    )
    assert outcome.kind == "sent"
    assert posted["endpoint"] == FCM
    assert posted["timeout"] == DEFAULT_TIMEOUT_SECONDS
    assert posted["headers"]["content-encoding"] == "aes128gcm"
    assert posted["headers"]["ttl"] == "3600"
    assert posted["headers"]["urgency"] == "high"
    assert posted["headers"]["authorization"].startswith("vapid t=")
    assert PUBLIC_KEY in posted["headers"]["authorization"]
    assert b"Onay" not in posted["data"]  # encrypted, not the clear text
