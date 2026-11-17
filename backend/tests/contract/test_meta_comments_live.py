"""Explicit manual diagnostics; all live evidence is pending until recorded.

These adapter probes bypass the application ledger. Never use them for product sends.
Public comment effects remain disabled in the separate legacy Meta harness.
"""

import hashlib
import json
import os
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
import pytest

from app.core.clock import SystemClock
from app.integrations.instagram.base import AccountRef
from app.integrations.instagram.meta import MetaInstagramProvider

pytestmark = pytest.mark.meta_comments_live
PROBE_TEXT = "AgentNest manually opted-in private reply probe."


def _probe[T](call: Callable[[], T]) -> T:
    try:
        return call()
    except Exception:  # noqa: S110 - never retain sensitive provider exceptions
        pass
    pytest.fail("Live comment probe failed; inspect safely before any retry.", pytrace=False)


def _check(condition: bool) -> None:
    if not condition:
        pytest.fail("Live comment probe contract expectation failed.", pytrace=False)


def _record(**values: Any) -> None:
    # Closed allow-list: never accept raw provider objects, errors, URLs or text.
    safe = {
        key: value
        for key, value in values.items()
        if key
        in {
            "http_status",
            "error_code",
            "error_subcode",
            "comments_subscribed",
            "count",
            "timestamp_present",
            "owner_matches",
            "allowed",
            "recipient_hash",
        }
        and (isinstance(value, bool | int) or value is None)
    }
    recipient = values.get("recipient_id")
    if isinstance(recipient, str):
        safe["recipient_hash"] = hashlib.sha256(recipient.encode()).hexdigest()[:16]
    filename = os.environ.get("META_LIVE_PROBE_RECORD", "")
    if filename:
        with Path(filename).open("a", encoding="utf-8") as output:
            output.write(json.dumps(safe, sort_keys=True) + "\n")


def _inputs(*, mutation: bool = False, second: bool = False, repeat: bool = False) -> str:
    if os.environ.get("CI"):
        pytest.skip("Live comment probes never run in CI.")
    target = os.environ.get(
        "META_LIVE_COMMENT_ID_SAME_COMMENTER" if second else "META_LIVE_COMMENT_ID", ""
    ).strip()
    if not target:
        pytest.skip("An exact target comment is required.")
    if mutation and os.environ.get("META_LIVE_COMMENT_EFFECT") != "private_reply":
        pytest.skip("Separate private_reply effect opt-in required.")
    if mutation and os.environ.get("META_LIVE_COMMENT_SEND") != "YES_SEND_REAL_MESSAGE":
        pytest.skip("Explicit real message opt-in required.")
    if (second or repeat) and os.environ.get(
        "META_LIVE_COMMENT_LIMIT_PROBES"
    ) != "YES_SEND_REAL_MESSAGE":
        pytest.skip("Separate limit probe opt-in required.")
    return target


@pytest.fixture
def live_account():
    token = os.environ.get("META_LIVE_ACCESS_TOKEN", "").strip()
    ig_id = os.environ.get("META_LIVE_IG_USER_ID", "").strip()
    if os.environ.get("CI") or not token or not ig_id:
        pytest.skip("Manual comments require both explicit live credentials, outside CI.")
    clock = SystemClock()

    def capture(response: httpx.Response) -> None:
        # Never log response bodies; extract numeric error codes only.
        try:
            data = response.json()
            error = data.get("error", {}) if isinstance(data, dict) else {}
            _record(
                http_status=response.status_code,
                error_code=error.get("code"),
                error_subcode=error.get("error_subcode"),
            )
        except ValueError:
            _record(http_status=response.status_code)

    class RecordingTransport(httpx.HTTPTransport):
        def handle_request(self, request: httpx.Request) -> httpx.Response:
            response = super().handle_request(request)
            response.read()
            capture(response)
            return response

    provider = _probe(
        lambda: MetaInstagramProvider(
            clock,
            "",
            os.environ.get("META_GRAPH_API_VERSION", "v25.0"),
            transport=RecordingTransport(),
        )
    )
    return provider, AccountRef(uuid.UUID(int=0), uuid.UUID(int=0), ig_id, lambda: token)


def test_subscription_readback(live_account):
    provider, account = live_account
    data = _probe(
        lambda: provider._request(account, f"{account.external_account_id}/subscribed_apps")
    )
    rows = data.get("data", [])
    present = any("comments" in row.get("subscribed_fields", []) for row in rows)
    _record(comments_subscribed=present, count=len(rows))
    _check(present)


def test_read_comment(live_account):
    target = _inputs()
    provider, account = live_account
    comment = _probe(lambda: provider.read_comment(account, target))
    _record(timestamp_present=comment.timestamp is not None, owner_matches=True)
    _check(comment.id == target)


def test_send_private_reply(live_account):
    target = _inputs(mutation=True)
    provider, account = live_account
    sent = _probe(lambda: provider.send_private_reply(account, target, PROBE_TEXT, "manual-probe"))
    _record(allowed=True, recipient_id=sent.recipient_id)
    _check(bool(sent.reply_id))


def test_second_reply_same_comment_rejected(live_account):
    target = _inputs(mutation=True, repeat=True)
    provider, account = live_account

    # Explicit target must already have received the first probe; never silently send it here.
    def attempt():
        from app.integrations.instagram.errors import ProviderError, ProviderOutcomeUnknown

        try:
            sent = provider.send_private_reply(account, target, PROBE_TEXT, "manual-second-probe")
        except ProviderOutcomeUnknown:
            _record(allowed=None)
            return None
        except ProviderError:
            _record(allowed=False)
            return False
        _record(allowed=True, recipient_id=sent.recipient_id)
        return True

    _check(_probe(attempt) is False)


def test_second_comment_same_commenter(live_account):
    target = _inputs(mutation=True, second=True)
    provider, account = live_account

    def attempt():
        from app.integrations.instagram.errors import ProviderError, ProviderOutcomeUnknown

        try:
            sent = provider.send_private_reply(
                account, target, PROBE_TEXT, "manual-commenter-probe"
            )
        except ProviderOutcomeUnknown:
            _record(allowed=None)
            return
        except ProviderError:
            _record(allowed=False)
            return
        _record(allowed=True, recipient_id=sent.recipient_id)

    _probe(attempt)
