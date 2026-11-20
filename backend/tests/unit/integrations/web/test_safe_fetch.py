import socket
import ssl

import httpcore
import pytest

from app.integrations.web.safe_fetch import PinnedBackend, SafeFetcher
from app.integrations.web.urls import FetchRefused

URL = "https://business.example/gizli?token=SECRET"
PUBLIC = "93.184.216.34"


class Resolver:
    def __init__(self, answers=None):
        self.answers = answers or [[PUBLIC]]
        self.calls = []

    def __call__(self, host, port, **kwargs):
        self.calls.append((host, port, kwargs))
        answer = self.answers[min(len(self.calls) - 1, len(self.answers) - 1)]
        if isinstance(answer, Exception):
            raise answer
        return [
            (
                socket.AF_INET6 if ":" in ip else socket.AF_INET,
                socket.SOCK_STREAM,
                6,
                "",
                (ip, port),
            )
            for ip in answer
        ]


class Script:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.pins = []
        self.writes = []
        self.reads = []
        self.sni = []

    def __call__(self, ip):
        self.pins.append(ip)
        owner = self

        class Stream(httpcore.MockStream):
            def write(self, buffer, timeout=None):
                owner.writes.append(buffer)

            def read(self, max_bytes, timeout=None):
                data = super().read(max_bytes, timeout)
                owner.reads.append(len(data))
                return data

            def start_tls(self, ssl_context, server_hostname=None, timeout=None):
                assert ssl_context.verify_mode == ssl.CERT_REQUIRED
                assert ssl_context.check_hostname
                owner.sni.append(server_hostname)
                return self

        class Backend(httpcore.MockBackend):
            def connect_tcp(self, host, port, **kwargs):
                return Stream(list(self._buffer))

        return Backend(next(self.responses))


def response(status=200, headers=None, body=b"hello"):
    if headers is None:
        headers = {"Content-Type": "text/html", "Content-Length": str(len(body))}
    head = f"HTTP/1.1 {status} Status\r\n".encode()
    head += b"".join(f"{key}: {value}\r\n".encode() for key, value in headers.items())
    return [head + b"\r\n", body]


def refused(script, reason, *, retryable=False, resolver=None, **kwargs):
    with pytest.raises(FetchRefused) as caught:
        SafeFetcher(resolver=resolver or Resolver(), backend_factory=script, **kwargs).fetch(URL)
    assert caught.value.reason == reason
    assert caught.value.retryable == retryable
    assert str(caught.value) == reason and "SECRET" not in str(caught.value)
    return caught.value


def test_headers_pin_sni_and_rebinding():
    resolver = Resolver([[PUBLIC], ["127.0.0.1"]])
    script = Script([response()])
    page = SafeFetcher(resolver=resolver, backend_factory=script).fetch(URL)
    assert page.body == b"hello" and page.url == URL
    assert script.pins == [PUBLIC] and len(resolver.calls) == 1
    assert script.sni == ["business.example"]
    request = b"".join(script.writes).decode()
    lines = request.split("\r\n")
    assert lines[0] == "GET /gizli?token=SECRET HTTP/1.1"
    assert set(lines[1:-2]) == {
        "Host: business.example",
        "User-Agent: PivorisImport/1.0",
        "Accept: text/html,application/xhtml+xml;q=0.9",
        "Accept-Language: tr,en;q=0.8",
        "Accept-Encoding: identity",
    }
    assert all(name not in request.lower() for name in ("cookie:", "authorization:", "referer:"))


@pytest.mark.parametrize("answers", [["127.0.0.1"], [PUBLIC, "10.0.0.1"], ["::ffff:127.0.0.1"]])
def test_blocked_answers_never_connect(answers):
    script = Script([])
    refused(script, "blocked_address", resolver=Resolver([answers, [PUBLIC]]))
    assert not script.pins


def test_dns_and_ipv6():
    refused(Script([]), "dns", retryable=True, resolver=Resolver([OSError("SECRET")]))
    refused(Script([]), "dns", retryable=True, resolver=Resolver([[]]))
    script = Script([response()])
    SafeFetcher(resolver=Resolver([["2606:4700:4700::1111"]]), backend_factory=script).fetch(URL)
    assert script.pins == ["2606:4700:4700::1111"]


@pytest.mark.parametrize(
    ("target", "reason"),
    [
        ("http://127.0.0.1", "ip_literal"),
        ("http://localhost", "host"),
        ("https://example.com:8080", "port"),
        ("file:///etc/passwd", "scheme"),
    ],
)
def test_redirect_policy(target, reason):
    script = Script([response(302, {"Location": target})])
    refused(script, reason)
    assert len(script.pins) == 1


def test_redirect_to_private():
    script = Script([response(302, {"Location": "https://internal.example"})])
    refused(script, "blocked_address", resolver=Resolver([[PUBLIC], ["10.0.0.1"]]))
    assert script.pins == [PUBLIC]


def test_redirect_limits_relative_and_reresolution():
    script = Script([*[response(302, {"Location": f"/page{i}"}) for i in range(3)], response()])
    resolver = Resolver()
    page = SafeFetcher(resolver=resolver, backend_factory=script).fetch(URL)
    assert page.redirects == 3 and page.url == "https://business.example/page2"
    assert len(resolver.calls) == len(script.pins) == 4
    script = Script([response(302, {"Location": "/next"})] * 4)
    refused(script, "redirects")
    refused(Script([response(302, {})]), "status")
    refused(Script([response(302, {"Location": "/" + "x" * 2000})]), "invalid_url")


@pytest.mark.parametrize(
    ("headers", "reason"),
    [
        ({"Content-Type": "application/json"}, "content_type"),
        ({"Content-Type": "image/png"}, "content_type"),
        ({}, "content_type"),
        ({"Content-Type": "text/html", "Content-Encoding": "gzip"}, "encoding"),
        ({"Content-Type": "text/html", "Content-Length": "99999"}, "too_large"),
    ],
)
def test_headers_refused_before_body(headers, reason):
    script = Script([response(headers=headers)])
    refused(script, reason, max_bytes=10)
    assert len(script.reads) == 1


@pytest.mark.parametrize(
    ("status", "retryable"),
    [(404, False), (403, False), (204, False), (206, False), (503, True), (429, True)],
)
def test_status(status, retryable):
    refused(Script([response(status)]), "status", retryable=retryable)


def test_stream_cap():
    headers = b"HTTP/1.1 200 OK\r\nContent-Type: text/html\r\nTransfer-Encoding: chunked\r\n\r\n"
    script = Script([[headers, b"4\r\n1234\r\n", b"4\r\n5678\r\n", b"4\r\n9012\r\n", b"0\r\n\r\n"]])
    refused(script, "too_large", max_bytes=6)
    assert len(script.reads) == 3


def test_slow_trickle():
    ticks = iter([0, 0, 0, 0, 21])
    refused(Script([response()]), "timeout", retryable=True, monotonic=lambda: next(ticks))


def test_pinned_backend_substitutes_host(monkeypatch):
    calls = []

    def parent(self, host, port, timeout, local_address, socket_options):
        calls.append((host, port))
        return httpcore.MockStream([])

    monkeypatch.setattr(httpcore.SyncBackend, "connect_tcp", parent)
    PinnedBackend(PUBLIC).connect_tcp("business.example", 443)
    assert calls == [(PUBLIC, 443)]


@pytest.mark.parametrize(
    ("exc", "reason", "retryable"),
    [
        (httpcore.ReadTimeout(), "timeout", True),
        (httpcore.ConnectError(), "network", True),
        (httpcore.RemoteProtocolError(), "network", True),
        (OSError(), "network", True),
        (ssl.SSLCertVerificationError(), "network", False),
    ],
)
def test_transport_errors(exc, reason, retryable):
    def backend(ip):
        raise exc

    refused(backend, reason, retryable=retryable)


def test_unicode_request_target_and_xhtml():
    script = Script([response(headers={"Content-Type": "APPLICATION/XHTML+XML; charset=UTF-8"})])
    page = SafeFetcher(resolver=Resolver(), backend_factory=script).fetch(
        "https://business.example/iletişim?q=üyelik#removed"
    )
    assert page.body == b"hello" and "#" not in page.url
    assert b"/ileti%C5%9Fim?q=%C3%BCyelik" in b"".join(script.writes)


def test_redirect_rebind_same_host_is_blocked():
    resolver = Resolver([[PUBLIC], ["127.0.0.1"]])
    script = Script([response(301, {"Location": "/next"})])
    refused(script, "blocked_address", resolver=resolver)
    assert len(resolver.calls) == 2 and len(script.pins) == 1


def test_missing_length_stream_is_capped():
    head = b"HTTP/1.1 200 OK\r\nContent-Type: text/html\r\nConnection: close\r\n\r\n"
    script = Script([[head, b"1234", b"5678", b"9012", b""]])
    refused(script, "too_large", max_bytes=6)
    assert sum(script.reads[1:]) == 8  # cap + at most one body chunk


def test_lying_length_still_never_consumes_oversized_body():
    script = Script(
        [response(headers={"Content-Type": "text/html", "Content-Length": "100"}, body=b"x" * 1000)]
    )
    refused(script, "too_large", max_bytes=6)
    assert len(script.reads) == 1
