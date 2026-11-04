"""Optional live Telegram Bot API probe harness (never run in CI).

Required: TELEGRAM_LIVE_BOT_TOKEN and TELEGRAM_LIVE_CHAT_ID.
Diagnostic probes run directly against the live Telegram Bot API to verify
real bot token validity, message sending, and photo upload.
"""

from __future__ import annotations

import io
import os
from collections.abc import Callable
from typing import Any

import pytest
from PIL import Image

from app.integrations.channels.telegram.client import TelegramClient

pytestmark = pytest.mark.telegram_live


def _probe[T](call: Callable[[], T]) -> T:
    """Suppress raw exceptions/tracebacks that could contain tokens or sensitive URLs."""
    try:
        return call()
    except Exception:  # noqa: S110 - raw exceptions may contain credentials; never log them.
        pass
    pytest.fail(
        "Live Telegram probe failed; check token and chat permissions safely.", pytrace=False
    )


def _check(condition: bool) -> None:
    if not condition:
        pytest.fail("Live Telegram probe contract expectation failed.", pytrace=False)


@pytest.fixture
def live_credentials() -> tuple[str, str]:
    token = os.environ.get("TELEGRAM_LIVE_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_LIVE_CHAT_ID", "").strip()
    if not token or not chat_id:
        pytest.skip(
            "Live Telegram probes require TELEGRAM_LIVE_BOT_TOKEN and TELEGRAM_LIVE_CHAT_ID."
        )
    return token, chat_id


@pytest.fixture
def live_client(live_credentials: tuple[str, str]) -> TelegramClient:
    token, _ = live_credentials
    return TelegramClient(token=token)


def test_live_telegram_get_me(live_client: TelegramClient) -> None:
    """Verify bot token validity by querying getMe."""
    me = _probe(lambda: live_client.get_me())
    _check(isinstance(me, dict))
    _check(bool(me.get("is_bot")))
    _check(bool(me.get("username")))


def test_live_telegram_send_ping_message(
    live_client: TelegramClient, live_credentials: tuple[str, str]
) -> None:
    """Verify outbound text message delivery to authorized chat."""
    _, chat_id = live_credentials
    result: dict[str, Any] = _probe(
        lambda: live_client.send_message(
            chat_id=chat_id,
            text="[AgentNest] Live Telegram probe ping: OK",
        )
    )
    _check(isinstance(result, dict))
    _check("message_id" in result)


def test_live_telegram_send_photo(
    live_client: TelegramClient, live_credentials: tuple[str, str]
) -> None:
    """Verify outbound photo delivery with caption to authorized chat."""
    _, chat_id = live_credentials

    # Create 100x100 test JPEG in memory
    img = Image.new("RGB", (100, 100), color="blue")
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    photo_bytes = buf.getvalue()

    result: dict[str, Any] = _probe(
        lambda: live_client.send_photo(
            chat_id=chat_id,
            photo=photo_bytes,
            caption="[AgentNest] Live Telegram probe photo: OK",
        )
    )
    _check(isinstance(result, dict))
    _check("message_id" in result)
