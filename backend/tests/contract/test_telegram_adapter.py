"""Contract and unit tests for Telegram Adapter, Webhook, and Polling Harness.

ADR-012, Phase 9 Session 04.

Covers:
- Secret token header validation (valid, invalid, missing).
- Duplicate update_id rejection (INV-06).
- Telegram bot base command handlers (/start, /link <code>, /unlink, /status, unlinked prompt).
- TelegramClient API methods with MockTransport (sendMessage, sendPhoto, callback queries).
- TelegramChannel.deliver_notification protocol conformance and message delivery.
- CLI long-polling runner with synthetic/mock updates.
"""

from __future__ import annotations

import contextlib
import json
from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.api.deps import get_app_settings, get_clock
from app.api.v1.telegram_webhook_router import get_telegram_client
from app.core.clock import FrozenClock
from app.core.config import Settings
from app.core.context import ActorRef, WorkspaceContext
from app.core.db import set_tenant_context
from app.identity.channels import ChannelLinkService
from app.identity.models import ChannelLink
from app.integrations.channels.base import ChannelRecipient
from app.integrations.channels.telegram import (
    TelegramApiError,
    TelegramChannel,
    TelegramClient,
    process_update,
)
from app.integrations.channels.telegram.models import TelegramUpdate
from app.notifications.models import Notification, NotificationDelivery
from tests.factories import workspace_with_members


class MockTelegramHandler:
    """Captures outgoing Telegram Bot API HTTP requests and returns configurable responses."""

    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []
        self.calls: list[dict[str, Any]] = []
        self.updates_queue: list[list[dict[str, Any]]] = []

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        url_path = urlparse(str(request.url)).path
        method_name = url_path.split("/")[-1]

        # Parse request body or params
        body: dict[str, Any] = {}
        if request.headers.get("content-type", "").startswith("application/json"):
            body = json.loads(request.content.decode("utf-8"))
        elif request.content:
            with contextlib.suppress(Exception):
                body = {
                    k: v[0]
                    for k, v in parse_qs(request.content.decode("utf-8", errors="ignore")).items()
                }

        call_record = {
            "method": request.method,
            "url": str(request.url),
            "api_method": method_name,
            "body": body,
        }
        self.calls.append(call_record)

        if method_name == "sendMessage":
            return httpx.Response(
                200,
                json={
                    "ok": True,
                    "result": {
                        "message_id": len(self.calls) + 100,
                        "chat": {"id": body.get("chat_id", 123456), "type": "private"},
                        "text": body.get("text", ""),
                        "date": 1700000000,
                    },
                },
            )

        if method_name == "sendPhoto":
            return httpx.Response(
                200,
                json={
                    "ok": True,
                    "result": {
                        "message_id": len(self.calls) + 200,
                        "chat": {"id": 123456, "type": "private"},
                        "photo": [{"file_id": "photo_123", "width": 800, "height": 600}],
                    },
                },
            )

        if method_name == "answerCallbackQuery":
            return httpx.Response(200, json={"ok": True, "result": True})

        if method_name == "editMessageText":
            return httpx.Response(
                200,
                json={
                    "ok": True,
                    "result": {
                        "message_id": body.get("message_id", 100),
                        "chat": {"id": body.get("chat_id", 123456)},
                        "text": body.get("text", ""),
                    },
                },
            )

        if method_name == "editMessageReplyMarkup":
            return httpx.Response(
                200,
                json={
                    "ok": True,
                    "result": {
                        "message_id": body.get("message_id", 100),
                        "chat": {"id": body.get("chat_id", 123456)},
                    },
                },
            )

        if method_name == "getFile":
            return httpx.Response(
                200,
                json={
                    "ok": True,
                    "result": {
                        "file_id": body.get("file_id", "f123"),
                        "file_unique_id": "u123",
                        "file_size": 1024,
                        "file_path": "photos/file_0.jpg",
                    },
                },
            )

        if "file/bot" in str(request.url):
            return httpx.Response(200, content=b"FAKE_PHOTO_DATA_BYTES")

        if method_name == "getUpdates":
            updates = self.updates_queue.pop(0) if self.updates_queue else []
            return httpx.Response(200, json={"ok": True, "result": updates})

        return httpx.Response(
            404, json={"ok": False, "error_code": 404, "description": "Not Found"}
        )


@pytest.fixture
def mock_tg() -> MockTelegramHandler:
    return MockTelegramHandler()


@pytest.fixture
def mock_tg_client(mock_tg: MockTelegramHandler) -> TelegramClient:
    transport = httpx.MockTransport(mock_tg.handle)
    return TelegramClient(token="TEST_BOT_TOKEN", transport=transport)


def _make_update(
    update_id: int,
    text: str,
    user_id: int = 777123,
    chat_id: int = 777123,
    username: str = "testowner",
) -> dict[str, Any]:
    return {
        "update_id": update_id,
        "message": {
            "message_id": 1,
            "date": 1700000000,
            "chat": {
                "id": chat_id,
                "type": "private",
                "username": username,
            },
            "from": {
                "id": user_id,
                "is_bot": False,
                "first_name": "Test",
                "last_name": "Owner",
                "username": username,
            },
            "text": text,
        },
    }


# =========================================================================
# 1. Secret Token Header Validation Tests
# =========================================================================


def test_telegram_webhook_secret_token_validation(
    client: TestClient,
    clock: FrozenClock,
    mock_tg_client: TelegramClient,
) -> None:
    test_secret = "super-secret-token-12345"
    test_settings = Settings(
        _env_file=None,
        telegram_webhook_secret=SecretStr(test_secret),
        telegram_bot_token=SecretStr("TEST_BOT_TOKEN"),
    )
    client.app.dependency_overrides[get_app_settings] = lambda: test_settings
    client.app.dependency_overrides[get_clock] = lambda: clock
    client.app.dependency_overrides[get_telegram_client] = lambda: mock_tg_client

    valid_payload = _make_update(update_id=101, text="/start")

    # Case A: Missing header -> 401
    res = client.post("/webhooks/telegram", json=valid_payload)
    assert res.status_code == 401
    assert "Invalid or missing secret token" in res.json().get("error", "")

    # Case B: Invalid header -> 401
    res = client.post(
        "/webhooks/telegram",
        json=valid_payload,
        headers={"X-Telegram-Bot-Api-Secret-Token": "wrong-secret"},
    )
    assert res.status_code == 401

    # Case C: Valid header -> 200
    res = client.post(
        "/webhooks/telegram",
        json=valid_payload,
        headers={"X-Telegram-Bot-Api-Secret-Token": test_secret},
    )
    assert res.status_code == 200
    assert res.json()["status"] == "ok"

    # Case D: Alias /api/v1/webhooks/telegram also works without CSRF
    res_alias = client.post(
        "/api/v1/webhooks/telegram",
        json=_make_update(update_id=102, text="/start"),
        headers={"X-Telegram-Bot-Api-Secret-Token": test_secret},
    )
    assert res_alias.status_code == 200
    assert res_alias.json()["status"] == "ok"


# =========================================================================
# 2. Duplicate update_id Rejection (INV-06)
# =========================================================================


def test_telegram_webhook_duplicate_update_rejection(
    client: TestClient,
    db_session: Session,
    clock: FrozenClock,
    mock_tg_client: TelegramClient,
) -> None:
    test_secret = "secret-token-dedup"
    test_settings = Settings(
        _env_file=None,
        telegram_webhook_secret=SecretStr(test_secret),
        telegram_bot_token=SecretStr("TEST_BOT_TOKEN"),
    )
    client.app.dependency_overrides[get_app_settings] = lambda: test_settings
    client.app.dependency_overrides[get_clock] = lambda: clock
    client.app.dependency_overrides[get_telegram_client] = lambda: mock_tg_client

    payload = _make_update(update_id=20001, text="/start")
    headers = {"X-Telegram-Bot-Api-Secret-Token": test_secret}

    # First delivery: processed
    res1 = client.post("/webhooks/telegram", json=payload, headers=headers)
    assert res1.status_code == 200
    assert res1.json()["status"] == "ok"

    # Second delivery with identical update_id: rejected immediately as duplicate
    res2 = client.post("/webhooks/telegram", json=payload, headers=headers)
    assert res2.status_code == 200
    assert res2.json()["status"] == "duplicate"

    # Verify database ledger has exactly one row
    rows = db_session.scalars(select(TelegramUpdate).where(TelegramUpdate.update_id == 20001)).all()
    assert len(rows) == 1
    assert rows[0].status == "processed"


# =========================================================================
# 3. Base Command Handlers (/start, /link, /unlink, /status, unlinked prompt)
# =========================================================================


def test_telegram_dispatcher_start_command(
    db_session: Session,
    clock: FrozenClock,
    mock_tg: MockTelegramHandler,
    mock_tg_client: TelegramClient,
) -> None:
    payload = _make_update(update_id=301, text="/start")

    result = process_update(db_session, clock, payload, client=mock_tg_client)
    assert result.status == "processed"
    assert result.action == "start"

    # Verify outgoing message to Telegram
    assert len(mock_tg.calls) == 1
    call = mock_tg.calls[0]
    assert call["api_method"] == "sendMessage"
    assert "Welcome to AgentNest" in call["body"]["text"]
    assert "/link" in call["body"]["text"]


def test_telegram_dispatcher_link_and_unlink_lifecycle(
    db_session: Session,
    clock: FrozenClock,
    mock_tg: MockTelegramHandler,
    mock_tg_client: TelegramClient,
) -> None:
    ws, users = workspace_with_members(db_session, name="Owner Salon")
    owner = users["owner"]
    set_tenant_context(db_session, ws.id)

    ctx = WorkspaceContext(
        workspace_id=ws.id,
        actor=ActorRef.user(owner.id),
        role="owner",
        timezone=ws.timezone,
        locale="tr",
        is_demo=False,
    )

    # 1. User generates a link code from web settings
    code, _ = ChannelLinkService.generate_link_code(db_session, clock, ctx, channel="telegram")

    # 2. User tries /link without code
    res_no_code = process_update(
        db_session,
        clock,
        _make_update(update_id=401, text="/link"),
        client=mock_tg_client,
    )
    assert res_no_code.action == "link_missing_code"
    assert "Please provide your 8-character link code" in mock_tg.calls[-1]["body"]["text"]

    # 3. User tries /link with invalid code
    res_bad_code = process_update(
        db_session,
        clock,
        _make_update(update_id=402, text="/link BADCODE1"),
        client=mock_tg_client,
    )
    assert "link_failed" in (res_bad_code.action or "")
    assert "Invalid link code" in mock_tg.calls[-1]["body"]["text"]

    # 4. User redeems valid link code
    res_valid = process_update(
        db_session,
        clock,
        _make_update(update_id=403, text=f"/link {code}", user_id=888123, username="tg_owner"),
        client=mock_tg_client,
    )
    assert res_valid.action == "link_success"
    assert "Successfully linked" in mock_tg.calls[-1]["body"]["text"]
    assert "Owner Salon" in mock_tg.calls[-1]["body"]["text"]

    # Verify link record in DB
    link = db_session.scalar(
        select(ChannelLink).where(
            ChannelLink.channel == "telegram",
            ChannelLink.channel_user_id == "888123",
            ChannelLink.status == "active",
        )
    )
    assert link is not None
    assert link.workspace_id == ws.id
    assert link.user_id == owner.id

    # 5. User checks /status while linked
    res_status = process_update(
        db_session,
        clock,
        _make_update(update_id=404, text="/status", user_id=888123),
        client=mock_tg_client,
    )
    assert res_status.action == "status"
    status_text = mock_tg.calls[-1]["body"]["text"]
    assert "Owner Salon" in status_text
    assert "Active notifications:" in status_text
    assert "0" in status_text

    # 6. User sends /unlink
    res_unlink = process_update(
        db_session,
        clock,
        _make_update(update_id=405, text="/unlink", user_id=888123),
        client=mock_tg_client,
    )
    assert res_unlink.action == "unlink"
    assert "unlinked from AgentNest" in mock_tg.calls[-1]["body"]["text"]

    # Verify link is unlinked in DB
    db_session.refresh(link)
    assert link.status == "unlinked"

    # 7. User checks /status after unlinking -> prompts to link
    res_status_unlinked = process_update(
        db_session,
        clock,
        _make_update(update_id=406, text="/status", user_id=888123),
        client=mock_tg_client,
    )
    assert res_status_unlinked.action == "status"
    assert "not linked to any AgentNest workspace" in mock_tg.calls[-1]["body"]["text"]


def test_telegram_dispatcher_unlinked_user_message_prompts_link(
    db_session: Session,
    clock: FrozenClock,
    mock_tg: MockTelegramHandler,
    mock_tg_client: TelegramClient,
) -> None:
    # Unknown/unlinked user sends arbitrary text
    payload = _make_update(update_id=501, text="Hello bot! Can you help me?", user_id=999999)

    result = process_update(db_session, clock, payload, client=mock_tg_client)
    assert result.status == "processed"
    assert result.action == "unlinked_prompt"

    assert len(mock_tg.calls) == 1
    assert "You have not linked your Telegram account yet" in mock_tg.calls[0]["body"]["text"]
    assert "/link" in mock_tg.calls[0]["body"]["text"]
    assert "CODE" in mock_tg.calls[0]["body"]["text"]


def test_telegram_dispatcher_linked_user_non_command_hook(
    db_session: Session,
    clock: FrozenClock,
    mock_tg: MockTelegramHandler,
    mock_tg_client: TelegramClient,
) -> None:
    ws, users = workspace_with_members(db_session)
    owner = users["owner"]
    set_tenant_context(db_session, ws.id)

    ctx = WorkspaceContext(
        workspace_id=ws.id,
        actor=ActorRef.user(owner.id),
        role="owner",
        timezone=ws.timezone,
        locale="tr",
        is_demo=False,
    )

    code, _ = ChannelLinkService.generate_link_code(db_session, clock, ctx, channel="telegram")
    ChannelLinkService.redeem_link_code(
        db_session,
        clock,
        channel="telegram",
        channel_user_id="12345",
        channel_chat_id="12345",
        raw_code=code,
    )

    hook_called: list[str] = []

    def custom_hook(session, clk, user, workspace, link, msg, client):
        hook_called.append(msg.text or "")
        client.send_message(chat_id=msg.chat.id, text=f"Echo: {msg.text}")

    payload = _make_update(update_id=601, text="Publish new photo", user_id=12345, chat_id=12345)
    result = process_update(
        db_session,
        clock,
        payload,
        client=mock_tg_client,
        on_linked_message=custom_hook,
    )

    assert result.status == "processed"
    assert result.action == "linked_message"
    assert hook_called == ["Publish new photo"]
    assert "Echo: Publish new photo" in mock_tg.calls[-1]["body"]["text"]


# =========================================================================
# 4. TelegramClient API Methods & Transport Tests
# =========================================================================


def test_telegram_client_api_methods(
    mock_tg: MockTelegramHandler,
    mock_tg_client: TelegramClient,
) -> None:
    # 1. sendMessage
    msg = mock_tg_client.send_message(
        chat_id=12345,
        text="Hello world",
        parse_mode="HTML",
    )
    assert msg["message_id"] >= 100
    assert mock_tg.calls[-1]["api_method"] == "sendMessage"

    # 2. sendPhoto
    photo = mock_tg_client.send_photo(
        chat_id=12345,
        photo=b"BINARY_PHOTO_DATA",
        caption="Photo caption",
    )
    assert photo["photo"][0]["file_id"] == "photo_123"
    assert mock_tg.calls[-1]["api_method"] == "sendPhoto"

    # 3. answerCallbackQuery
    ack = mock_tg_client.answer_callback_query("cb_123", text="Action acknowledged")
    assert ack is True
    assert mock_tg.calls[-1]["api_method"] == "answerCallbackQuery"

    # 4. editMessageText
    edited = mock_tg_client.edit_message_text(chat_id=12345, message_id=100, text="Updated text")
    assert edited["text"] == "Updated text"
    assert mock_tg.calls[-1]["api_method"] == "editMessageText"

    # 5. editMessageReplyMarkup
    markup = mock_tg_client.edit_message_reply_markup(
        chat_id=12345,
        message_id=100,
        reply_markup={"inline_keyboard": []},
    )
    assert markup["message_id"] == 100

    # 6. getFile & downloadFile
    f_info = mock_tg_client.get_file("f123")
    assert f_info["file_path"] == "photos/file_0.jpg"

    content = mock_tg_client.download_file("photos/file_0.jpg")
    assert content == b"FAKE_PHOTO_DATA_BYTES"


def test_telegram_client_error_handling() -> None:
    def error_transport_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            400,
            json={"ok": False, "error_code": 400, "description": "Bad Request: chat not found"},
        )

    client = TelegramClient(
        token="BAD_TOKEN", transport=httpx.MockTransport(error_transport_handler)
    )
    with pytest.raises(TelegramApiError) as exc_info:
        client.send_message(chat_id=999999, text="Will fail")

    assert exc_info.value.status_code == 400
    assert exc_info.value.error_code == 400
    assert "chat not found" in exc_info.value.description


# =========================================================================
# 5. TelegramChannel.deliver_notification Tests
# =========================================================================


def test_telegram_channel_deliver_notification_success(
    db_session: Session,
    clock: FrozenClock,
    mock_tg: MockTelegramHandler,
    mock_tg_client: TelegramClient,
) -> None:
    ws, users = workspace_with_members(db_session)
    owner = users["owner"]
    set_tenant_context(db_session, ws.id)

    # Create notification
    notif = Notification(
        workspace_id=ws.id,
        recipient_user_id=owner.id,
        type="approval.requested",
        severity="attention",
        params={"title": "Review Urgent Reply", "message": "Customer asks for business hours."},
    )
    db_session.add(notif)
    db_session.flush()

    delivery = NotificationDelivery(
        workspace_id=ws.id,
        notification_id=notif.id,
        recipient_user_id=owner.id,
        channel="telegram",
        status="pending",
    )
    db_session.add(delivery)
    db_session.flush()

    channel = TelegramChannel(client=mock_tg_client)
    recipient = ChannelRecipient(
        user_id=owner.id,
        workspace_id=ws.id,
        channel="telegram",
        channel_chat_id="998877",
        ui_locale="en",
    )

    result = channel.deliver_notification(db_session, clock, delivery, recipient)

    assert result.success is True
    assert result.status == "delivered"
    assert result.delivered_at == clock.now()
    assert result.external_message_id is not None

    # Verify formatted text in Telegram call
    assert len(mock_tg.calls) == 1
    call = mock_tg.calls[0]
    assert call["api_method"] == "sendMessage"
    assert call["body"]["chat_id"] == "998877"
    assert "Review Urgent Reply" in call["body"]["text"]
    assert "Customer asks for business hours" in call["body"]["text"]
    assert "⚠️" in call["body"]["text"]  # Attention icon


def test_telegram_channel_deliver_notification_missing_chat_id(
    db_session: Session,
    clock: FrozenClock,
    mock_tg_client: TelegramClient,
) -> None:
    ws, users = workspace_with_members(db_session)
    owner = users["owner"]
    set_tenant_context(db_session, ws.id)

    notif = Notification(
        workspace_id=ws.id,
        recipient_user_id=owner.id,
        type="account.recovered",
        severity="info",
        params={},
    )
    db_session.add(notif)
    db_session.flush()

    delivery = NotificationDelivery(
        workspace_id=ws.id,
        notification_id=notif.id,
        recipient_user_id=owner.id,
        channel="telegram",
        status="pending",
    )
    db_session.add(delivery)
    db_session.flush()

    channel = TelegramChannel(client=mock_tg_client)
    # Recipient without chat_id or user_id
    recipient = ChannelRecipient(
        user_id=owner.id,
        workspace_id=ws.id,
        channel="telegram",
        channel_chat_id=None,
        channel_user_id=None,
    )

    result = channel.deliver_notification(db_session, clock, delivery, recipient)
    assert result.success is False
    assert result.status == "failed"
    assert "missing Telegram chat ID" in result.error_message


# =========================================================================
# 6. CLI Long-Polling Runner Tests
# =========================================================================


def test_telegram_polling_runner_processes_updates(
    shared_session_factory: sessionmaker[Session],
    clock: FrozenClock,
    mock_tg: MockTelegramHandler,
    mock_tg_client: TelegramClient,
) -> None:
    from app.cli import run_telegram_polling

    # Queue 2 updates on first call, empty on second call
    mock_tg.updates_queue = [
        [
            _make_update(update_id=7001, text="/start"),
            _make_update(update_id=7002, text="/status"),
        ],
        [],
    ]

    test_settings = Settings(_env_file=None)

    exit_code = run_telegram_polling(
        session_factory=shared_session_factory,
        clock=clock,
        settings=test_settings,
        client=mock_tg_client,
        timeout=1,
        max_iterations=2,
    )

    assert exit_code == 0

    # Both updates should be recorded in telegram_updates ledger
    with shared_session_factory() as session:
        updates = session.scalars(
            select(TelegramUpdate).where(TelegramUpdate.update_id.in_([7001, 7002]))
        ).all()
        assert len(updates) == 2
        update_ids = {u.update_id for u in updates}
        assert update_ids == {7001, 7002}
