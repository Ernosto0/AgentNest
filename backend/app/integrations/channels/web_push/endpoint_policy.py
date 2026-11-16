"""Where the server may POST a push: known push services only, on public addresses (SSRF guard).

A subscription's ``endpoint`` is a URL chosen by whoever registered the device, and the server
POSTs to it. Two checks run at **every send** (not only at subscribe time):

1. **Allowlist.** The host must be one of the browsers' own push services. A custom or
   self-hosted push service is not supported: adding one is a code change here, on purpose.

   ====================  =========================================  =======================
   Browser family        Push service host                          Rule
   ====================  =========================================  =======================
   Chrome, Edge, Opera,  ``fcm.googleapis.com``                     exact host
   Brave, Samsung
   Firefox               ``*.push.services.mozilla.com``            suffix
   Safari / iOS          ``*.push.apple.com``                       suffix
   Edge (WNS)            ``*.notify.windows.com``                   suffix
   ====================  =========================================  =======================

2. **Public addresses only.** The host is resolved and every address must be globally routable:
   loopback, private, link-local (including the cloud metadata address), CGNAT, reserved,
   multicast and unspecified addresses are refused, including IPv4 embedded in IPv6.

The allowlist is the real protection: an attacker cannot make ``fcm.googleapis.com`` resolve
somewhere else. The resolution check is defence in depth. A residual time-of-check/time-of-use
gap remains (the HTTP client resolves again when it connects), which is acceptable because the
names are controlled by the push-service operators. Redirects are never followed (see
``sender``), and a short timeout bounds a slow endpoint.
"""

import ipaddress
import socket
from collections.abc import Callable
from typing import Any
from urllib.parse import urlsplit

ALLOWED_HOSTS: frozenset[str] = frozenset({"fcm.googleapis.com"})
ALLOWED_HOST_SUFFIXES: tuple[str, ...] = (
    ".push.services.mozilla.com",
    ".push.apple.com",
    ".notify.windows.com",
)

Resolver = Callable[..., Any]  # socket.getaddrinfo-compatible


class EndpointRefused(Exception):  # noqa: N818  (a refusal reason, not an error condition)
    """The endpoint must not be contacted. ``permanent`` means it never will be acceptable."""

    def __init__(self, reason: str, *, permanent: bool) -> None:
        super().__init__(reason)
        self.reason = reason
        self.permanent = permanent


def host_allowed(host: str) -> bool:
    host = host.lower().rstrip(".")
    return host in ALLOWED_HOSTS or any(
        host.endswith(suffix) and len(host) > len(suffix) for suffix in ALLOWED_HOST_SUFFIXES
    )


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


def check_endpoint(endpoint: str, resolver: Resolver = socket.getaddrinfo) -> None:
    """Raise ``EndpointRefused`` unless the endpoint may be contacted right now.

    A static problem (scheme, port, credentials, host not on the allowlist) is permanent: the
    device can never be reached and should be revoked. An address problem or a DNS failure is
    not permanent (it may be transient), so the device is kept and the send is failed.
    """
    try:
        parts = urlsplit(endpoint)
        port = parts.port
    except ValueError:
        raise EndpointRefused("malformed_endpoint", permanent=True) from None
    host = (parts.hostname or "").lower()
    if parts.scheme != "https" or not host or parts.username or parts.password:
        raise EndpointRefused("endpoint_not_https", permanent=True)
    if port not in (None, 443):
        raise EndpointRefused("endpoint_port_not_allowed", permanent=True)
    if not host_allowed(host):
        raise EndpointRefused("endpoint_host_not_allowed", permanent=True)
    try:
        infos = resolver(host, 443, type=socket.SOCK_STREAM)
    except OSError:
        raise EndpointRefused("endpoint_dns_failed", permanent=False) from None
    addresses = {str(info[4][0]) for info in infos}
    if not addresses:
        raise EndpointRefused("endpoint_dns_failed", permanent=False)
    if not all(address_allowed(address) for address in addresses):
        raise EndpointRefused("endpoint_address_not_public", permanent=False)
