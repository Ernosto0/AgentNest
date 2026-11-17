"""Download a customer's image from the Instagram CDN, safely and capped.

The attachment URL comes from a webhook payload, so it is untrusted input (INV-03) and the server
fetches it (SSRF). The rules are the ones of the voice-note fetcher
(``integrations/transcription/fetch.py``, whose host list and address check this module reuses),
all enforced before and during the download:

- ``https`` only, no credentials in the URL, port 443 only.
- The host must be an Instagram or Facebook CDN host. The real hosts of Instagram image URLs are
  **unverified** against a live account; adding one is a code change, on purpose.
- Every address the host resolves to must be globally routable (defence in depth).
- Redirects are never followed, no cookies or proxy settings are used, and **no Authorization
  header is sent**: the CDN link is self-authenticating and must not receive the page token.
- ``Content-Length`` above the cap refuses the download before any body is read, the body is
  streamed with a running total, and a total deadline bounds a slow trickle.
- The declared content type is checked before the body is read.
- The URL is a signed link: it is never logged and never put in an exception message.
"""

import logging
import socket
import time
from collections.abc import Callable
from urllib.parse import urlsplit

import httpx

from app.integrations.transcription.fetch import (
    CHUNK_BYTES,
    EXPIRED_STATUSES,
    Resolver,
    address_allowed,
    host_allowed,
)
from app.integrations.vision.base import FetchedImage
from app.integrations.vision.errors import ImageFetchError, ImageRejected
from app.integrations.vision.images import declared_type_allowed


def check_url(url: str, resolver: Resolver = socket.getaddrinfo) -> None:
    """Raise ``ImageFetchError`` unless the URL may be fetched right now."""
    refused = ImageFetchError("IMAGE_URL_REFUSED")
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
        raise ImageFetchError("IMAGE_DOWNLOAD_FAILED", retryable=True) from None
    addresses = {str(info[4][0]) for info in infos}
    if not addresses:
        raise ImageFetchError("IMAGE_DOWNLOAD_FAILED", retryable=True)
    if not all(address_allowed(a) for a in addresses):
        raise refused


class HttpsImageFetcher:
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

    def fetch(self, url: str, *, max_bytes: int, timeout_s: float) -> FetchedImage:
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
                    "GET", url, headers={"Accept": "image/*", "Accept-Encoding": "identity"}
                ) as response,
            ):
                return self._read(response, max_bytes, deadline)
        except httpx.RequestError:
            raise ImageFetchError("IMAGE_DOWNLOAD_FAILED", retryable=True) from None

    def _read(self, response: httpx.Response, max_bytes: int, deadline: float) -> FetchedImage:
        status = response.status_code
        if 300 <= status < 400:
            raise ImageFetchError("IMAGE_URL_REFUSED")
        if status in EXPIRED_STATUSES:
            raise ImageFetchError("IMAGE_EXPIRED")
        if status == 429 or status >= 500:
            raise ImageFetchError("IMAGE_DOWNLOAD_FAILED", retryable=True)
        if status != 200:
            raise ImageFetchError("IMAGE_DOWNLOAD_FAILED")
        content_type = response.headers.get("content-type", "")
        if not declared_type_allowed(content_type):
            raise ImageRejected("IMAGE_UNSUPPORTED_TYPE")
        declared = response.headers.get("content-length", "")
        if declared.isdigit() and int(declared) > max_bytes:
            raise ImageRejected("IMAGE_TOO_LARGE")
        data = bytearray()
        for chunk in response.iter_bytes(CHUNK_BYTES):
            data.extend(chunk)
            if len(data) > max_bytes:
                raise ImageRejected("IMAGE_TOO_LARGE")
            if self._monotonic() > deadline:
                raise ImageFetchError("IMAGE_DOWNLOAD_FAILED", retryable=True)
        return FetchedImage(bytes(data), content_type)
