"""Stream public HTML over a fresh hostname-authenticated, IP-pinned connection per hop."""

import logging
import socket
import ssl
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.parse import quote, urljoin

import certifi
import httpcore

from app.integrations.web.address_policy import is_public_address
from app.integrations.web.urls import FetchRefused, parse_site_url


@dataclass(frozen=True)
class FetchedPage:
    url: str
    host: str
    final_host: str
    status: int
    content_type: str
    body: bytes
    redirects: int


class PageFetcher(Protocol):
    simulated: bool

    def fetch(self, url: str) -> FetchedPage: ...


class PinnedBackend(httpcore.SyncBackend):
    def __init__(self, pinned_ip: str):
        self.pinned_ip = pinned_ip

    def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: Iterable[Any] | None = None,
    ) -> httpcore.NetworkStream:
        return super().connect_tcp(self.pinned_ip, port, timeout, local_address, socket_options)


class SafeFetcher:
    simulated = False

    def __init__(
        self,
        *,
        resolver: Callable[..., Any] = socket.getaddrinfo,
        backend_factory: Callable[[str], httpcore.NetworkBackend] | None = None,
        monotonic: Callable[[], float] = time.monotonic,
        max_bytes: int = 2_097_152,
        max_redirects: int = 3,
        connect_timeout: float = 5.0,
        read_timeout: float = 10.0,
        total_timeout: float = 20.0,
    ):
        self.resolver, self.backend_factory, self.monotonic = resolver, backend_factory, monotonic
        self.max_bytes, self.max_redirects = max_bytes, max_redirects
        self.connect_timeout, self.read_timeout, self.total_timeout = (
            connect_timeout,
            read_timeout,
            total_timeout,
        )
        logging.getLogger("httpcore").setLevel(logging.WARNING)

    def fetch(self, url: str) -> FetchedPage:
        deadline = self.monotonic() + self.total_timeout
        initial_host = parse_site_url(url).host
        for hop in range(self.max_redirects + 1):
            parsed = parse_site_url(url)
            host = parsed.host

            def remaining(host: str = host) -> float:
                left = deadline - self.monotonic()
                if left <= 0:
                    raise FetchRefused("timeout", retryable=True, host=host)
                return left

            try:
                remaining()
                try:
                    infos = self.resolver(host, parsed.port, type=socket.SOCK_STREAM)
                except OSError:
                    raise FetchRefused("dns", retryable=True, host=host) from None
                addresses = list(dict.fromkeys(str(info[4][0]) for info in infos))
                if not addresses:
                    raise FetchRefused("dns", retryable=True, host=host)
                if not all(is_public_address(a) for a in addresses):
                    raise FetchRefused("blocked_address", host=host)
                ip = next((a for a in addresses if ":" not in a), addresses[0])
                backend = self.backend_factory(ip) if self.backend_factory else PinnedBackend(ip)
                with httpcore.ConnectionPool(
                    ssl_context=ssl.create_default_context(cafile=certifi.where()),
                    network_backend=backend,
                    max_connections=1,
                    retries=0,
                    http2=False,
                ) as pool:
                    limit = remaining()
                    timeouts = {
                        "connect": min(self.connect_timeout, limit),
                        "read": min(self.read_timeout, limit),
                        "write": min(self.connect_timeout, limit),
                        "pool": min(self.connect_timeout, limit),
                    }
                    with pool.stream(
                        "GET",
                        httpcore.URL(
                            scheme=parsed.scheme.encode("ascii"),
                            host=host.encode("ascii"),
                            port=parsed.port,
                            target=quote(parsed.path_and_query, safe="/%?=&:+,@;!$'()*~-._").encode(
                                "ascii"
                            ),
                        ),
                        headers={
                            "Host": host,
                            "User-Agent": "PivorisImport/1.0",
                            "Accept": "text/html,application/xhtml+xml;q=0.9",
                            "Accept-Language": "tr,en;q=0.8",
                            "Accept-Encoding": "identity",
                        },
                        extensions={"timeout": timeouts},
                    ) as response:
                        remaining()
                        headers = {
                            k.decode("ascii").lower(): v.decode("latin-1")
                            for k, v in response.headers
                        }
                        status = response.status
                        if status in (301, 302, 303, 307, 308) and "location" in headers:
                            location = headers["location"]
                            if len(location) > 2000:
                                raise FetchRefused("invalid_url", host=host)
                            if hop == self.max_redirects:
                                raise FetchRefused("redirects", host=host)
                            try:
                                url = urljoin(parsed.url, location)
                            except ValueError:
                                raise FetchRefused("invalid_url", host=host) from None
                            continue
                        if status != 200:
                            raise FetchRefused(
                                "status", retryable=status == 429 or status >= 500, host=host
                            )
                        if (
                            headers.get("content-encoding", "identity").strip().lower()
                            != "identity"
                        ):
                            raise FetchRefused("encoding", host=host)
                        content_type = headers.get("content-type", "")
                        if content_type.split(";", 1)[0].strip().lower() not in (
                            "text/html",
                            "application/xhtml+xml",
                        ):
                            raise FetchRefused("content_type", host=host)
                        length = headers.get("content-length", "")
                        if length.isdigit() and int(length) > self.max_bytes:
                            raise FetchRefused("too_large", host=host)
                        body = bytearray()
                        for chunk in response.iter_stream():
                            remaining()
                            if len(body) + len(chunk) > self.max_bytes:
                                raise FetchRefused("too_large", host=host)
                            body.extend(chunk)
                        remaining()
                        return FetchedPage(
                            parsed.url, initial_host, host, status, content_type, bytes(body), hop
                        )
            except httpcore.TimeoutException:
                raise FetchRefused("timeout", retryable=True, host=host) from None
            except (httpcore.NetworkError, httpcore.ProtocolError, OSError) as exc:
                cert_error = isinstance(exc, ssl.SSLCertVerificationError) or isinstance(
                    exc.__cause__, ssl.SSLCertVerificationError
                )
                raise FetchRefused("network", retryable=not cert_error, host=host) from None
        raise FetchRefused("redirects", host=initial_host)
