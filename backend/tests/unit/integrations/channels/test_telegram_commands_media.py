"""Unit and workflow tests for Telegram Command Dispatch, Photo Ingestion & Owner Tasks.

ADR-012, ADR-014, ADR-024, ADR-025, AC-2, AC-3, INV-04, INV-11.
"""

from __future__ import annotations

import contextlib
import io
import json
from datetime import timedelta
from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx
from PIL import Image
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent.models import AccountAgent, OwnerTask
from app.audit.models import AuditLog
from app.commands.models import OwnerCommand
from app.content.models import ContentItem, MediaAsset
from app.core.clock import FrozenClock
from app.core.context import ActorRef, WorkspaceContext
from app.core.db import set_tenant_context
from app.identity.channels import ChannelLinkService
from app.identity.models import ChannelLink
from app.integrations.channels.telegram import (
    TelegramClient,
    process_update,
)
from app.integrations.channels.telegram.handlers import get_pending_media
from app.integrations.instagram.models import SocialAccount
from app.reporting.service import get_daily_summary
from tests.factories import workspace_with_members
from tests.helpers.reporting import Builder


def _make_test_jpeg(width: int = 100, height: int = 100, color: str = "blue") -> bytes:
    """Generate valid in-memory JPEG bytes for testing image processing."""
    img = Image.new("RGB", (width, height), color=color)
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


class MockTelegramHandler:
    """Mock HTTP transport for Telegram Bot API calls."""

    def __init__(self, photo_bytes: bytes | None = None) -> None:
        self.calls: list[dict[str, Any]] = []
        self.photo_bytes = photo_bytes or _make_test_jpeg()
        self.file_size_override: int | None = None

    def handle(self, request: httpx.Request) -> httpx.Response:
        url_str = str(request.url)
        url_path = urlparse(url_str).path
        method_name = url_path.split("/")[-1]

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
            "url": url_str,
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

        if method_name == "getFile":
            file_sz = (
                self.file_size_override
                if self.file_size_override is not None
                else len(self.photo_bytes)
            )
            return httpx.Response(
                200,
                json={
                    "ok": True,
                    "result": {
                        "file_id": body.get("file_id", "photo_123"),
                        "file_unique_id": "u123",
                        "file_size": file_sz,
                        "file_path": "photos/test_photo.jpg",
                    },
                },
            )

        if "file/bot" in url_str:
            return httpx.Response(200, content=self.photo_bytes)

        if method_name == "answerCallbackQuery":
            return httpx.Response(200, json={"ok": True, "result": True})

        return httpx.Response(200, json={"ok": True, "result": {}})


def _make_text_update(
    update_id: int,
    text: str,
    user_id: int = 99901,
    chat_id: int = 99901,
    username: str = "test_owner",
) -> dict[str, Any]:
    return {
        "update_id": update_id,
        "message": {
            "message_id": update_id * 10,
            "date": 1700000000,
            "chat": {"id": chat_id, "type": "private"},
            "from": {"id": user_id, "is_bot": False, "first_name": "Test", "username": username},
            "text": text,
        },
    }


def _make_photo_update(
    update_id: int,
    file_id: str = "photo_abc",
    file_size: int = 1024,
    caption: str | None = None,
    user_id: int = 99901,
    chat_id: int = 99901,
) -> dict[str, Any]:
    return {
        "update_id": update_id,
        "message": {
            "message_id": update_id * 10,
            "date": 1700000000,
            "chat": {"id": chat_id, "type": "private"},
            "from": {"id": user_id, "is_bot": False, "first_name": "Test"},
            "photo": [
                {
                    "file_id": file_id,
                    "file_unique_id": f"uniq_{file_id}",
                    "width": 800,
                    "height": 600,
                    "file_size": file_size,
                }
            ],
            "caption": caption,
        },
    }


def _setup_linked_owner(
    db_session: Session,
    clock: FrozenClock,
    channel_user_id: str = "99901",
    name: str = "Test Salon",
) -> tuple[Any, Any, ChannelLink]:
    """Helper to create workspace, owner, and active ChannelLink."""
    ws, users = workspace_with_members(db_session, name=name)
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
    link = ChannelLinkService.redeem_link_code(
        db_session,
        clock,
        channel="telegram",
        channel_user_id=channel_user_id,
        channel_chat_id=channel_user_id,
        raw_code=code,
        channel_username="test_owner",
    )
    return ws, owner, link


# =============================================================================
# 1. Reporting Query Tests (AC-2)
# =============================================================================


def test_telegram_reporting_query_exact_matching_counts(
    db_session: Session,
    clock: FrozenClock,
) -> None:
    """AC-2: 'Bugün kaç DM geldi?' in Telegram returns exact matching count as reporting."""
    ws, owner, _ = _setup_linked_owner(db_session, clock, channel_user_id="99901")

    # Use Builder to seed social account, conversations and messages for today
    now = clock.now()
    seed_time = now - timedelta(minutes=5)
    builder = Builder(db_session, ws, owner, simulated=False)
    conv1 = builder.conversation(seed_time)
    conv2 = builder.conversation(seed_time)
    for _ in range(3):
        builder.message(conv1, "inbound", seed_time)
    for _ in range(2):
        builder.message(conv2, "inbound", seed_time)
    db_session.commit()

    # Query daily summary directly to establish ground truth
    actor = ActorRef.user(owner.id)
    ctx = WorkspaceContext(
        workspace_id=ws.id,
        actor=actor,
        role="owner",
        timezone=ws.timezone,
        locale="tr",
        is_demo=False,
    )
    summary = get_daily_summary(db_session, clock, ctx)
    assert summary["inbound_messages"] == 5

    mock_tg = MockTelegramHandler()
    client = TelegramClient(token="TEST_BOT_TOKEN", transport=httpx.MockTransport(mock_tg.handle))

    # Send "Bugün kaç DM geldi?"
    payload = _make_text_update(update_id=1001, text="Bugün kaç DM geldi?", user_id=99901)
    res = process_update(db_session, clock, payload, client=client)

    assert res.status == "processed"
    assert res.action == "reporting_query"
    assert len(mock_tg.calls) == 1
    sent_text = mock_tg.calls[0]["body"]["text"]
    assert "<b>5</b>" in sent_text
    assert "Gelen Mesajlar" in sent_text

    # Also test "Bugünkü özet"
    payload_summary = _make_text_update(update_id=1002, text="Bugünkü özet", user_id=99901)
    res_summary = process_update(db_session, clock, payload_summary, client=client)
    assert res_summary.status == "processed"
    assert res_summary.action == "reporting_query"
    summary_text = mock_tg.calls[-1]["body"]["text"]
    assert "Bugünkü Özet" in summary_text
    assert "5" in summary_text


# =============================================================================
# 2. Inbound Photo Ingestion & 20 MB Limit (AC-3, INV-11)
# =============================================================================


def test_telegram_photo_ingestion_20mb_limit_rejection(
    db_session: Session,
    clock: FrozenClock,
) -> None:
    """INV-11: Upload exceeding 20 MB is immediately rejected and recorded in audit log."""
    ws, _, _ = _setup_linked_owner(db_session, clock, channel_user_id="99902")

    mock_tg = MockTelegramHandler()
    client = TelegramClient(token="TEST_BOT_TOKEN", transport=httpx.MockTransport(mock_tg.handle))

    # Update with photo.file_size = 21 MB (21 * 1024 * 1024)
    oversized_bytes = 21 * 1024 * 1024
    payload = _make_photo_update(
        update_id=2001,
        file_id="huge_photo",
        file_size=oversized_bytes,
        user_id=99902,
        chat_id=99902,
    )

    result = process_update(db_session, clock, payload, client=client)
    assert result.status == "processed"
    assert result.action == "photo_rejected_size"

    # Verify rejection message sent
    assert len(mock_tg.calls) == 1
    assert "20 MB" in mock_tg.calls[0]["body"]["text"]

    # Verify audit rejection record (INV-11)
    audit_row = db_session.scalar(
        select(AuditLog).where(
            AuditLog.workspace_id == ws.id,
            AuditLog.action == "media.rejected",
        )
    )
    assert audit_row is not None
    assert audit_row.metadata_.get("reason") == "too_large"
    assert audit_row.metadata_.get("byte_size") == oversized_bytes

    # Verify no MediaAsset was created
    assert db_session.scalar(select(MediaAsset).where(MediaAsset.workspace_id == ws.id)) is None


def test_telegram_photo_ingestion_no_caption_cached(
    db_session: Session,
    clock: FrozenClock,
) -> None:
    """Photo without caption is ingested, stored, and cached for pending intake."""
    ws, owner, _ = _setup_linked_owner(db_session, clock, channel_user_id="99903")

    valid_jpeg = _make_test_jpeg(width=200, height=200, color="green")
    mock_tg = MockTelegramHandler(photo_bytes=valid_jpeg)
    client = TelegramClient(token="TEST_BOT_TOKEN", transport=httpx.MockTransport(mock_tg.handle))

    payload = _make_photo_update(
        update_id=2002,
        file_id="valid_photo_1",
        file_size=len(valid_jpeg),
        caption=None,
        user_id=99903,
        chat_id=99903,
    )

    result = process_update(db_session, clock, payload, client=client)
    assert result.status == "processed"
    assert result.action == "photo_cached"

    # Verify media asset created
    asset = db_session.scalar(select(MediaAsset).where(MediaAsset.workspace_id == ws.id))
    assert asset is not None
    assert asset.status == "ready"
    assert asset.mime_type == "image/jpeg"

    # Verify message sent to telegram prompting user
    send_calls = [c for c in mock_tg.calls if c["api_method"] == "sendMessage"]
    assert len(send_calls) == 1
    assert "Fotoğraf Alındı" in send_calls[0]["body"]["text"]

    # Verify cached in pending media
    cached_asset_id = get_pending_media(owner.id, clock.now())
    assert cached_asset_id == asset.id


# =============================================================================
# 3. Photo with Caption Creates Story Draft with Approval (AC-3, INV-04)
# =============================================================================


def test_telegram_photo_with_caption_creates_story_draft_approval_required(
    db_session: Session,
    clock: FrozenClock,
) -> None:
    """AC-3, INV-04: Photo with caption creates story draft requiring approval."""
    ws, _, _ = _setup_linked_owner(db_session, clock, channel_user_id="99904")

    valid_jpeg = _make_test_jpeg(width=300, height=300, color="red")
    mock_tg = MockTelegramHandler(photo_bytes=valid_jpeg)
    client = TelegramClient(token="TEST_BOT_TOKEN", transport=httpx.MockTransport(mock_tg.handle))

    payload = _make_photo_update(
        update_id=3001,
        file_id="story_photo_1",
        file_size=len(valid_jpeg),
        caption="bu story'yi 19:00'da paylaş",
        user_id=99904,
        chat_id=99904,
    )

    result = process_update(db_session, clock, payload, client=client)
    assert result.status == "processed"
    assert result.action == "photo_draft_created"

    # Verify ContentItem draft created
    item = db_session.scalar(select(ContentItem).where(ContentItem.workspace_id == ws.id))
    assert item is not None
    assert item.content_type == "story_image"
    assert item.caption == "bu story'yi 19:00'da paylaş"
    assert item.media_asset_id is not None
    # Crucial INV-04: free text NEVER directly publishes
    assert item.status in ("draft", "pending_approval")
    assert item.status != "published"

    # Verify Telegram notification confirms draft and mentions approval policy
    send_calls = [c for c in mock_tg.calls if c["api_method"] == "sendMessage"]
    assert len(send_calls) == 1
    confirm_text = send_calls[0]["body"]["text"]
    assert "Story Taslağı Oluşturuldu" in confirm_text
    assert "19:00" in confirm_text
    assert "INV-04" in confirm_text


# =============================================================================
# 4. Owner Task Routing to Account Agent (ADR-024)
# =============================================================================


def test_telegram_owner_task_routed_to_active_agent(
    db_session: Session,
    clock: FrozenClock,
) -> None:
    """When workspace account has active agent, instructions route to owner_tasks.submit."""
    ws, owner, _ = _setup_linked_owner(db_session, clock, channel_user_id="99905")

    # Connect social account (PostgreSQL trigger initializes AccountAgent row)
    now = clock.now()
    social_account = SocialAccount(
        workspace_id=ws.id,
        platform="instagram",
        provider_kind="mock",
        external_account_id="ig_agent_456",
        username="agent_salon",
        status="connected",
        created_at=now,
        updated_at=now,
    )
    db_session.add(social_account)
    db_session.flush()

    # Query auto-created AccountAgent and promote to active agent mode
    agent = db_session.scalar(
        select(AccountAgent).where(AccountAgent.social_account_id == social_account.id)
    )
    assert agent is not None
    agent.controller_mode = "agent"
    agent.state = "active"
    agent.controller_epoch = 1
    db_session.commit()

    mock_tg = MockTelegramHandler()
    client = TelegramClient(token="TEST_BOT_TOKEN", transport=httpx.MockTransport(mock_tg.handle))

    # Send owner instruction
    instruction = "Ahmet Bey'e randevu için dönüş yap"
    payload = _make_text_update(update_id=4001, text=instruction, user_id=99905)
    result = process_update(db_session, clock, payload, client=client)

    assert result.status == "processed"
    assert result.action == "agent_task"

    # Verify OwnerTask was created in database with source_channel='telegram'
    task = db_session.scalar(
        select(OwnerTask).where(
            OwnerTask.workspace_id == ws.id,
            OwnerTask.social_account_id == social_account.id,
        )
    )
    assert task is not None
    assert task.request_text == instruction
    assert task.source_channel == "telegram"
    assert task.requester_user_id == owner.id

    # Verify confirmation message to Telegram
    assert len(mock_tg.calls) == 1
    reply_text = mock_tg.calls[0]["body"]["text"]
    assert "Talimat Alındı" in reply_text
    assert "Ahmet Bey" in reply_text


# =============================================================================
# 5. Free-Text Command Submission to CommandService (INV-04)
# =============================================================================


def test_telegram_free_text_general_command_submission(
    db_session: Session,
    clock: FrozenClock,
) -> None:
    """General text commands are routed to CommandService.submit with source 'telegram'."""
    ws, owner, _ = _setup_linked_owner(db_session, clock, channel_user_id="99906")

    mock_tg = MockTelegramHandler()
    client = TelegramClient(token="TEST_BOT_TOKEN", transport=httpx.MockTransport(mock_tg.handle))

    cmd_text = "çalışma saatleri nedir?"
    payload = _make_text_update(update_id=5001, text=cmd_text, user_id=99906)
    result = process_update(db_session, clock, payload, client=client)

    assert result.status == "processed"
    assert result.action == "owner_command"

    # Verify OwnerCommand record created in database
    command = db_session.scalar(
        select(OwnerCommand).where(
            OwnerCommand.workspace_id == ws.id,
            OwnerCommand.user_id == owner.id,
        )
    )
    assert command is not None
    assert command.raw_text == cmd_text
    assert command.channel == "telegram"
    assert command.client_request_id == "tg:5001"

    # Verify acknowledgment to Telegram
    assert len(mock_tg.calls) == 1
    assert "Komut Alındı" in mock_tg.calls[0]["body"]["text"]


def test_telegram_free_text_never_directly_publishes(
    db_session: Session,
    clock: FrozenClock,
) -> None:
    """INV-04: Free text command saying 'bu postu hemen yayınla' cannot bypass approval."""
    ws, _, _ = _setup_linked_owner(db_session, clock, channel_user_id="99907")

    mock_tg = MockTelegramHandler()
    client = TelegramClient(token="TEST_BOT_TOKEN", transport=httpx.MockTransport(mock_tg.handle))

    # Imperative command trying to directly publish
    payload = _make_text_update(
        update_id=6001,
        text="Bu postu onaysız hemen yayınla ve gönder",
        user_id=99907,
    )
    result = process_update(db_session, clock, payload, client=client)
    assert result.status == "processed"

    # No published content items exist
    published_items = db_session.scalars(
        select(ContentItem).where(
            ContentItem.workspace_id == ws.id,
            ContentItem.status == "published",
        )
    ).all()
    assert len(published_items) == 0
