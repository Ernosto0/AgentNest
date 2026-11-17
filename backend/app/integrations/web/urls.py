"""Pure URL policy. Non-default ports expose internal admin services, not business sites."""

import ipaddress
import re
from dataclasses import dataclass
from urllib.parse import urlsplit, urlunsplit


class FetchRefused(Exception):
    def __init__(self, reason: str, *, retryable: bool = False, host: str | None = None):
        super().__init__(reason)
        self.reason, self.retryable, self.host = reason, retryable, host


@dataclass(frozen=True)
class ParsedUrl:
    scheme: str
    host: str
    port: int
    path_and_query: str
    url: str


def parse_site_url(raw: str) -> ParsedUrl:
    raw = raw.strip()
    if not raw or len(raw) > 2000 or any(ord(c) < 32 or ord(c) == 127 for c in raw):
        raise FetchRefused("invalid_url")
    if "://" not in raw:
        # Explicit non-hierarchical schemes must not become hostnames.
        if re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", raw) and not re.match(r"^[^/:]+:\d+(?:/|$)", raw):
            raise FetchRefused("scheme")
        raw = "https://" + raw
    if len(raw) > 2000:
        raise FetchRefused("invalid_url")
    try:
        parts = urlsplit(raw)
        if parts.scheme not in ("http", "https"):
            raise FetchRefused("scheme")
        if "@" in parts.netloc:
            raise FetchRefused("userinfo")
        host = (parts.hostname or "").lower().removesuffix(".")
        try:
            ipaddress.ip_address(host)
        except ValueError:
            pass
        else:
            raise FetchRefused("ip_literal")
        try:
            host = host.encode("idna").decode("ascii").lower()
        except UnicodeError:
            raise FetchRefused("host") from None
        last = host.rsplit(".", 1)[-1]
        if last.isdigit() or re.fullmatch(r"0x[0-9a-f]+", last, re.I):
            raise FetchRefused("ip_literal")
        if (
            not host
            or host == "home.arpa"
            or "." not in host
            or len(host) > 253
            or not re.fullmatch(r"[a-z0-9.-]+", host)
            or any(not label or len(label) > 63 for label in host.split("."))
            or host.endswith(
                (
                    ".localhost",
                    ".local",
                    ".internal",
                    ".localdomain",
                    ".lan",
                    ".home.arpa",
                    ".intranet",
                )
            )
        ):
            raise FetchRefused("host")
        port = parts.port
        default = 443 if parts.scheme == "https" else 80
        if port not in (None, default):
            raise FetchRefused("port", host=host)
        path = parts.path or "/"
        query = ("?" + parts.query) if parts.query else ""
        url = urlunsplit((parts.scheme, host, path, parts.query, ""))
        return ParsedUrl(parts.scheme, host, default, path + query, url)
    except (ValueError, UnicodeError):
        raise FetchRefused("invalid_url") from None
