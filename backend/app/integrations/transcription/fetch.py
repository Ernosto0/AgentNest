"""Download a customer's voice note from the Instagram CDN, safely and capped.

The attachment URL comes from a webhook payload, so it is untrusted input (INV-03) and the server
fetches it (SSRF). Rules, all enforced before and during the download:

- ``https`` only, no credentials in the URL, port 443 only.
- The host must be an Instagram or Facebook CDN host (suffix list below). The real hosts of
  Instagram voice-note URLs are **unverified** against a live account; adding one is a code
  change here, on purpose.
- Every address the host resolves to must be globally routable (defence in depth; there is a
  residual time-of-check/time-of-use gap because the HTTP client resolves again).
- Redirects are never followed, no cookies or proxy settings are used, and **no Authorization
  header is sent**: the CDN link is self-authenticating and must not receive the page token.
- ``Content-Length`` above the cap refuses the download before any body is read, and the body is
  streamed with a running total, so a server that lies is cut off at the cap.
- The declared content type is checked before the body is read.
- A total deadline bounds a slow trickle (``timeout`` alone only bounds each read).
- The URL is a signed link: it is never logged and never put in an exception message.
"""

import ipaddress
import logging
import socket
import time
from collections.abc import Callable
from typing import Any
from urllib.parse import urlsplit

import httpx

from app.integrations.transcription.audio import declared_type_allowed
from app.integrations.transcription.base import FetchedAudio
from app.integrations.transcription.errors import AudioFetchError, AudioRejected

ALLOWED_HOST_SUFFIXES: tuple[str, ...] = (
    ".cdninstagram.com",
    ".fbcdn.net",
    ".fbsbx.com",
)
CHUNK_BYTES = 64 * 1024
EXPIRED_STATUSES = frozenset({401, 403, 404, 410})

Resolver = Callable[..., Any]  # socket.getaddrinfo-compatible


def host_allowed(host: str) -> bool:
    host = host.lower().rstrip(".")
    return any(host.endswith(s) and len(host) > len(s) for s in ALLOWED_HOST_SUFFIXES)


def address_allowed(address: str) -> bool:
    """True only for a globally routable unicast address."""
    try:
        ip = ipaddress.ip_address(address.split("%", 1)[0])
    except ValueError:
        return False
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    if isinstance(ip, ipaddress.IPv6Address) and ip.sixtofour is not None:
        ip = ip.sixtofour
    return ip.is_global and not ip.is_multicast


def check_url(url: str, resolver: Resolver = socket.getaddrinfo) -> None:
    """Raise ``AudioFetchError`` unless the URL may be fetched right now."""
    refused = AudioFetchError("VOICE_URL_REFUSED")
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError:
        raise refused from None
    host = (parts.hostname or "").lower()
    if parts.scheme != "https" or not host or parts.username or parts.password:
        raise refused
    if port not in (None, 443) or not host_allowed(host):
        raise refused
    try:
        infos = resolver(host, 443, type=socket.SOCK_STREAM)
    except OSError:
        raise AudioFetchError("VOICE_DOWNLOAD_FAILED", retryable=True) from None
    addresses = {str(info[4][0]) for info in infos}
    if not addresses:
        raise AudioFetchError("VOICE_DOWNLOAD_FAILED", retryable=True)
    if not all(address_allowed(a) for a in addresses):
        raise refused


class HttpsAudioFetcher:
    """The fetcher for real (Meta) accounts."""

    def __init__(
        self,
        *,
        transport: httpx.BaseTransport | None = None,
        resolver: Resolver = socket.getaddrinfo,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self._transport = transport
        self._resolver = resolver
        self._monotonic = monotonic
        # httpx logs request URLs at INFO; the link is a signed credential.
        for name in ("httpx", "httpcore"):
            logging.getLogger(name).setLevel(logging.WARNING)

    def fetch(self, url: str, *, max_bytes: int, timeout_s: float) -> FetchedAudio:
        check_url(url, self._resolver)
        deadline = self._monotonic() + timeout_s * 2
        try:
            with (
                httpx.Client(
                    transport=self._transport,
                    timeout=timeout_s,
                    follow_redirects=False,
                    trust_env=False,
                ) as client,
                client.stream(
                    "GET", url, headers={"Accept": "audio/*", "Accept-Encoding": "identity"}
                ) as response,
            ):
                return self._read(response, max_bytes, deadline)
        except httpx.RequestError:
            raise AudioFetchError("VOICE_DOWNLOAD_FAILED", retryable=True) from None

    def _read(self, response: httpx.Response, max_bytes: int, deadline: float) -> FetchedAudio:
        status = response.status_code
        if 300 <= status < 400:
            raise AudioFetchError("VOICE_URL_REFUSED")
        if status in EXPIRED_STATUSES:
            raise AudioFetchError("VOICE_EXPIRED")
        if status == 429 or status >= 500:
            raise AudioFetchError("VOICE_DOWNLOAD_FAILED", retryable=True)
        if status != 200:
            raise AudioFetchError("VOICE_DOWNLOAD_FAILED")
        content_type = response.headers.get("content-type", "")
        if not declared_type_allowed(content_type):
            raise AudioRejected("VOICE_UNSUPPORTED_TYPE")
        declared = response.headers.get("content-length", "")
        if declared.isdigit() and int(declared) > max_bytes:
            raise AudioRejected("VOICE_TOO_LARGE")
        data = bytearray()
        for chunk in response.iter_bytes(CHUNK_BYTES):
            data.extend(chunk)
            if len(data) > max_bytes:
                raise AudioRejected("VOICE_TOO_LARGE")
            if self._monotonic() > deadline:
                raise AudioFetchError("VOICE_DOWNLOAD_FAILED", retryable=True)
        return FetchedAudio(bytes(data), content_type)
