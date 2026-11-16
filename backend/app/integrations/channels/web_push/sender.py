"""Send one Web Push message through ``pywebpush`` and classify the outcome.

The one module that imports ``pywebpush`` / ``py_vapid`` (import-linter). It uses the library's
**synchronous** ``webpush()`` (the app and the job worker are sync); the library still imports
``aiohttp`` at import time, so ``aiohttp`` stays a dependency but is never used here.

Rules enforced here, per send:

- The endpoint passes ``endpoint_policy.check_endpoint`` first (allowlist + public addresses).
- A short timeout; redirects are never followed (a push service has no reason to redirect, and a
  redirect could point inward).
- Nothing identifying is logged or returned: not the endpoint, not the keys, not the payload, not
  the push service's response body. The outcome carries a kind, a status code and a fixed reason.
- This is called outside any DB transaction (the adapter closes its read transaction first).
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

import requests
from py_vapid import Vapid
from pywebpush import WebPushException, webpush

from app.integrations.channels.web_push.endpoint_policy import (
    EndpointRefused,
    Resolver,
    check_endpoint,
)

DEFAULT_TIMEOUT_SECONDS = 8.0

OutcomeKind = Literal["sent", "gone", "retry", "refused", "failed"]


@dataclass(frozen=True)
class SendOutcome:
    """``sent``: accepted by the push service. ``gone``: 404/410, the device is revoked.
    ``retry``: transient (5xx, 429, timeout, DNS), try again later. ``refused``: the endpoint
    policy said no (``permanent`` refusals revoke the device). ``failed``: anything else."""

    kind: OutcomeKind
    reason: str = ""
    status_code: int | None = None
    permanent: bool = False


def _no_redirect_session() -> requests.Session:
    """A session that never follows a redirect: ``max_redirects = 0`` makes ``requests`` raise
    ``TooManyRedirects`` on the first 3xx instead of following it."""
    session = requests.Session()
    session.max_redirects = 0
    return session


Sender = Callable[..., SendOutcome]


def classify_status(status: int | None) -> SendOutcome:
    """Map a push service's HTTP status to an outcome (used for errors; 200-202 is success)."""
    if status in (404, 410):
        return SendOutcome("gone", "subscription_gone", status)
    if status == 429 or (status is not None and status >= 500):
        return SendOutcome("retry", "push_service_unavailable", status)
    if status is not None and 300 <= status < 400:
        return SendOutcome("failed", "push_service_redirect_refused", status)
    if status in (401, 403):
        return SendOutcome("failed", "push_service_rejected_vapid", status)
    if status == 413:
        return SendOutcome("failed", "payload_too_large", status)
    return SendOutcome("failed", "push_service_rejected", status)


def send_web_push(
    *,
    endpoint: str,
    p256dh: str,
    auth: str,
    payload: str,
    vapid_private_key: str,
    vapid_subject: str,
    ttl: int,
    urgency: str = "normal",
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    resolver: Resolver | None = None,
    push_fn: Callable[..., Any] = webpush,
) -> SendOutcome:
    """Encrypt ``payload`` for the device and POST it. Never raises for a push-service problem."""
    try:
        if resolver is None:
            check_endpoint(endpoint)
        else:
            check_endpoint(endpoint, resolver)
    except EndpointRefused as refused:
        return SendOutcome("refused", refused.reason, permanent=refused.permanent)

    try:
        vapid = Vapid.from_string(private_key=vapid_private_key)
    except Exception:  # a configuration problem, never a device problem
        return SendOutcome("failed", "vapid_key_unusable")

    try:
        response = push_fn(
            subscription_info={"endpoint": endpoint, "keys": {"p256dh": p256dh, "auth": auth}},
            data=payload,
            vapid_private_key=vapid,
            vapid_claims={"sub": vapid_subject},
            ttl=ttl,
            timeout=timeout,
            headers={"Urgency": urgency},
            requests_session=_no_redirect_session(),
        )
    except WebPushException as exc:
        return classify_status(exc.status_code)
    except requests.TooManyRedirects:
        return SendOutcome("failed", "push_service_redirect_refused")
    except (requests.Timeout, requests.ConnectionError):
        return SendOutcome("retry", "push_service_unreachable")
    except Exception:  # encryption failure on a malformed key, library bug, ...
        return SendOutcome("failed", "push_send_error")

    status = getattr(response, "status_code", None)
    if isinstance(status, int) and status > 202:
        return classify_status(status)
    return SendOutcome("sent", status_code=status if isinstance(status, int) else None)
