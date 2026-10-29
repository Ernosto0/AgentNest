"""Manually opted-in adapter probes, never evidence until actually run against Meta.

Required: META_LIVE_ACCESS_TOKEN and META_LIVE_IG_USER_ID. Optional recipient/image
inputs explicitly authorize a real DM/post respectively; no automatic side-effect retry.
These diagnostic probes bypass the application ledger. Product sends/publishes must
continue through operations. Do not record output, request URLs or response bodies here.
"""

import os
import time
import uuid
from collections.abc import Callable
from datetime import timedelta

import pytest

from app.core.clock import SystemClock
from app.integrations.instagram.base import AccountRef, ContainerSpec
from app.integrations.instagram.meta import MetaInstagramProvider
from app.integrations.instagram.oauth import compute_capabilities

pytestmark = pytest.mark.meta_live


def _probe[T](call: Callable[[], T]) -> T:
    """Suppress exceptions/tracebacks that could contain credentials or presigned URLs."""
    try:
        return call()
    except Exception:  # noqa: S110 - raw exceptions may contain credentials; never log them.
        pass
    # Raise outside the except block so no raw exception remains in __context__.
    pytest.fail(
        "Live adapter probe failed; inspect account state safely before any retry.", pytrace=False
    )


def _check(condition: bool) -> None:
    # Do not use assertion introspection on live response objects or identifiers.
    if not condition:
        pytest.fail("Live adapter contract expectation failed.", pytrace=False)


@pytest.fixture
def live_account() -> tuple[MetaInstagramProvider, AccountRef, SystemClock]:
    token = os.environ.get("META_LIVE_ACCESS_TOKEN", "").strip()
    ig_id = os.environ.get("META_LIVE_IG_USER_ID", "").strip()
    if not token or not ig_id:
        pytest.skip("Manual Meta probes require both explicit live credentials.")
    clock = SystemClock()
    provider = _probe(
        lambda: MetaInstagramProvider(clock, "", os.environ.get("META_GRAPH_API_VERSION", "v25.0"))
    )
    account = AccountRef(uuid.UUID(int=0), uuid.UUID(int=0), ig_id, token_provider=lambda: token)
    return provider, account, clock


def test_live_profile(live_account: tuple[MetaInstagramProvider, AccountRef, SystemClock]) -> None:
    provider, account, _ = live_account
    profile = _probe(lambda: provider.get_account_profile(account))
    _check(profile.external_account_id == account.external_account_id and bool(profile.username))


def test_live_quota(live_account: tuple[MetaInstagramProvider, AccountRef, SystemClock]) -> None:
    provider, account, _ = live_account
    quota = _probe(lambda: provider.get_publishing_quota(account))
    _check(quota.used >= 0 and quota.limit > 0 and quota.window_hours == 24)


def test_live_optional_dm_and_lookup(
    live_account: tuple[MetaInstagramProvider, AccountRef, SystemClock],
) -> None:
    recipient = os.environ.get("META_LIVE_RECIPIENT_ID", "").strip()
    if not recipient:
        pytest.skip("A recipient input is required to opt in to a real DM.")
    provider, account, clock = live_account
    since = clock.now() - timedelta(seconds=2)
    text = "AgentNest manually opted-in contract probe."
    result = _probe(lambda: provider.send_text_message(account, recipient, text))
    _check(bool(result.message_id))
    # Read-only polling accommodates eventual consistency; never repeat the send.
    for _ in range(15):
        recent = _probe(lambda: provider.find_recent_outbound(account, recipient, since))
        if any(
            item.message_id == result.message_id and item.recipient_id == recipient
            for item in recent
        ):
            return
        time.sleep(2)
    _check(False)


def test_live_optional_image_publish(
    live_account: tuple[MetaInstagramProvider, AccountRef, SystemClock],
) -> None:
    image_url = os.environ.get("META_LIVE_IMAGE_URL", "").strip()
    if not image_url:
        pytest.skip("An HTTPS JPEG input is required to opt in to a real feed post.")
    provider, account, _ = live_account
    container = _probe(
        lambda: provider.create_media_container(account, ContainerSpec("IMAGE", image_url))
    )
    _check(bool(container))
    for _ in range(30):
        status = _probe(lambda: provider.get_container_status(account, container))
        if status.status_code == "FINISHED":
            break
        _check(status.status_code == "IN_PROGRESS")
        time.sleep(2)
    else:
        pytest.fail("Live image processing did not finish within the probe window.", pytrace=False)
    media_id = _probe(lambda: provider.publish_container(account, container))
    _check(bool(media_id))
    media = _probe(lambda: provider.get_media(account, media_id))
    _check(
        media.media_id == media_id
        and bool(media.permalink)
        and media.permalink.startswith("https://")
    )


def _comment_probe_inputs(effect: str) -> tuple[str, str]:
    """Exact founder-owned fixtures only; never select a customer comment automatically."""
    media_id = os.environ.get("META_LIVE_COMMENT_MEDIA_ID", "").strip()
    comment_id = os.environ.get("META_LIVE_COMMENT_ID", "").strip()
    if not media_id or not comment_id:
        pytest.skip("Comment probes require exact media and comment test targets.")
    if effect != "read" and os.environ.get("META_LIVE_COMMENT_EFFECT", "") != effect:
        pytest.skip("Each comment mutation requires a separate exact effect opt-in.")
    capability = {
        "read": "comment_read",
        "reply": "comment_reply",
        "private_reply": "comment_private_reply",
        "hide": "comment_moderate",
        "unhide": "comment_moderate",
        "delete": "comment_moderate",
    }[effect]
    # Do not introduce a test-only flag that can bypass an unresolved research gate.
    # Replace this gate only with reviewed authenticated capability evidence.
    if not compute_capabilities([], False)[capability]:
        pytest.skip("R75 comment capability evidence remains pending; real probe disabled.")
    return media_id, comment_id


@pytest.mark.parametrize("effect", ["read", "reply", "private_reply", "hide", "unhide", "delete"])
def test_live_optional_comment_target(
    live_account: tuple[MetaInstagramProvider, AccountRef, SystemClock], effect: str
) -> None:
    media_id, comment_id = _comment_probe_inputs(effect)
    provider, account, _ = live_account
    source = _probe(lambda: provider.read_comment(account, comment_id))
    _check(source.id == comment_id and source.media.id == media_id)
    if effect == "read":
        return
    operation_key = f"manual-contract-{uuid.uuid4()}"
    text = "AgentNest explicitly authorized synthetic-test-target contract probe."
    if effect == "private_reply":
        value = _probe(
            lambda: provider.send_private_reply(account, comment_id, text, operation_key)
        )
        _check(bool(value.reply_id))
        return
    result = _probe(
        lambda: provider.perform_comment_effect(
            account, comment_id, effect, text if effect == "reply" else None, operation_key
        )
    )
    _check(bool(result.provider_id))
    # No repeat mutation on uncertainty. An acknowledgement alone is not readback.
