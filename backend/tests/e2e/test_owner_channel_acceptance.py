"""End-to-end acceptance tests for Phase 9 Owner Messaging Channel (Telegram).

Verifies the four canonical Acceptance Criteria defined in
docs/implementation/phases/phase-09-owner-channel.md:

1. AC-1: A linked owner receives an `approval.requested` message for a reply draft
   with the exact text, approves with an inline button (`act:<token>`), and the reply
   is sent (queued in job ledger). A second press reports "already decided" with no
   second send (INV-06, INV-16).
2. AC-2: "Bugün kaç DM geldi?" in Telegram returns the exact same number as the web
   report (`get_daily_summary`).
3. AC-3: Sending a photo with "bu story'yi 19:00'da paylaş" creates a story draft with
   that media and a schedule proposal requiring explicit approval (never auto-scheduled
   from free text, INV-04).
4. AC-4: No core module imports the Telegram adapter except the channel registry
   (and webhook router).
"""

from __future__ import annotations

import ast
import contextlib
import html
import io
import json
import uuid
from datetime import timedelta
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx
from PIL import Image
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.approvals import service as approvals_service
from app.content.models import ContentItem, MediaAsset
from app.core.clock import FrozenClock
from app.core.context import ActorRef, WorkspaceContext
from app.core.db import set_tenant_context
from app.core.ids import new_id
from app.identity.channels import ChannelLinkService
from app.identity.models import ChannelLink, User
from app.inbox.models import Conversation, Message, ReplyDraft
from app.integrations.channels.base import ChannelRecipient
from app.integrations.channels.telegram import (
    TelegramClient,
    process_update,
)
from app.integrations.channels.telegram.adapter import TelegramChannel
from app.integrations.instagram.models import SocialAccount
from app.jobs.models import Job
from app.notifications.models import Notification, NotificationDelivery
from app.reporting.service import get_daily_summary
from tests.factories import workspace_with_members
from tests.helpers.reporting import Builder


def _make_test_jpeg(width: int = 120, height: int = 120, color: str = "coral") -> bytes:
    img = Image.new("RGB", (width, height), color=color)
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


class MockTelegramTransport:
    """Mock HTTP transport capturing all outbound Telegram Bot API requests."""

    def __init__(self, photo_bytes: bytes | None = None) -> None:
        self.calls: list[dict[str, Any]] = []
        self.photo_bytes = photo_bytes or _make_test_jpeg()

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

        self.calls.append(
            {
                "method": request.method,
                "url": url_str,
                "api_method": method_name,
                "body": body,
            }
        )

        if method_name in ("sendMessage", "editMessageText"):
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

        if method_name in ("answerCallbackQuery", "editMessageReplyMarkup"):
            return httpx.Response(200, json={"ok": True, "result": True})

        if method_name == "getFile":
            return httpx.Response(
                200,
                json={
                    "ok": True,
                    "result": {
                        "file_id": body.get("file_id", "photo_file_123"),
                        "file_unique_id": "u_photo_123",
                        "file_size": len(self.photo_bytes),
                        "file_path": "photos/acceptance_photo.jpg",
                    },
                },
            )

        if "file/bot" in url_str:
            return httpx.Response(200, content=self.photo_bytes)

        return httpx.Response(200, json={"ok": True, "result": {}})


def _setup_linked_owner(
    db_session: Session,
    clock: FrozenClock,
    channel_user_id: str = "88801",
    name: str = "E2E Salon",
) -> tuple[Any, User, ChannelLink]:
    """Helper to provision workspace, owner, and active ChannelLink."""
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
        channel_username="owner_acceptance",
    )
    return ws, owner, link


def _make_callback_query_update(
    update_id: int,
    callback_data: str,
    user_id: int,
    chat_id: int,
    message_id: int = 1001,
    message_text: str = "Onay talebi",
) -> dict[str, Any]:
    return {
        "update_id": update_id,
        "callback_query": {
            "id": f"cb_{update_id}",
            "from": {
                "id": user_id,
                "is_bot": False,
                "first_name": "Acceptance",
                "username": "owner_acceptance",
            },
            "message": {
                "message_id": message_id,
                "date": 1700000000,
                "chat": {"id": chat_id, "type": "private"},
                "text": message_text,
            },
            "data": callback_data,
        },
    }


def _make_text_update(
    update_id: int,
    text: str,
    user_id: int,
    chat_id: int,
) -> dict[str, Any]:
    return {
        "update_id": update_id,
        "message": {
            "message_id": update_id * 10,
            "date": 1700000000,
            "chat": {"id": chat_id, "type": "private"},
            "from": {"id": user_id, "is_bot": False, "first_name": "Acceptance"},
            "text": text,
        },
    }


def _make_photo_update(
    update_id: int,
    caption: str,
    user_id: int,
    chat_id: int,
    file_id: str = "photo_story_123",
) -> dict[str, Any]:
    return {
        "update_id": update_id,
        "message": {
            "message_id": update_id * 10,
            "date": 1700000000,
            "chat": {"id": chat_id, "type": "private"},
            "from": {"id": user_id, "is_bot": False, "first_name": "Acceptance"},
            "caption": caption,
            "photo": [
                {
                    "file_id": f"{file_id}_thumb",
                    "file_unique_id": "thumb_1",
                    "width": 100,
                    "height": 100,
                    "file_size": 1500,
                },
                {
                    "file_id": file_id,
                    "file_unique_id": "orig_1",
                    "width": 800,
                    "height": 800,
                    "file_size": 45000,
                },
            ],
        },
    }


# =============================================================================
# AC-1: Outbound approval request, inline decision button, replay protection
# =============================================================================


def test_ac1_owner_approval_workflow_reply_draft_single_use_send(
    db_session: Session,
    clock: FrozenClock,
) -> None:
    """AC-1: Linked owner receives approval.requested message for reply draft with exact

    text, approves with inline button (act:<token>), and reply is sent. Second press
    reports 'already decided' with no second send.
    """
    ws, owner, link = _setup_linked_owner(db_session, clock, channel_user_id="88801")
    ctx = WorkspaceContext(
        workspace_id=ws.id,
        actor=ActorRef.user(owner.id),
        role="owner",
        timezone=ws.timezone,
        locale="tr",
        is_demo=False,
    )

    now = clock.now()
    social = SocialAccount(
        id=uuid.uuid4(),
        workspace_id=ws.id,
        platform="instagram",
        provider_kind="mock",
        external_account_id="ig_e2e_ac1",
        username="ac1_salon",
        status="connected",
        created_at=now,
        updated_at=now,
    )
    db_session.add(social)
    db_session.flush()

    conv = Conversation(
        id=new_id(),
        workspace_id=ws.id,
        social_account_id=social.id,
        customer_external_id="cust_ac1_99",
        customer_handle="tugba_k",
        handling_mode="automatic",
        attention="none",
        last_inbound_at=clock.now(),
        is_simulated=False,
    )
    db_session.add(conv)
    db_session.flush()

    customer_msg = Message(
        id=new_id(),
        workspace_id=ws.id,
        social_account_id=social.id,
        conversation_id=conv.id,
        direction="inbound",
        sender_kind="customer",
        external_message_id="msg_ac1_inbound",
        text="Lazer epilasyon seans ücretiniz nedir?",
        provider_timestamp=clock.now(),
        is_simulated=False,
    )
    db_session.add(customer_msg)
    db_session.flush()

    exact_reply_text = "Merhaba Tuğba Hanım, tüm vücut lazer epilasyon seansımız 1.500 TL'dir."
    draft = ReplyDraft(
        id=new_id(),
        workspace_id=ws.id,
        conversation_id=conv.id,
        covers_through_message_id=customer_msg.id,
        source="ai",
        origin="legacy",
        status="pending_approval",
        decision="approval_required",
        text=exact_reply_text,
        version=1,
        created_by_actor_type="system",
        is_simulated=False,
    )
    db_session.add(draft)
    db_session.flush()

    approval = approvals_service.request(
        db_session,
        clock,
        ctx,
        kind="authorization",
        action="reply.send",
        subject_type="reply_draft",
        subject_id=draft.id,
        subject_version=draft.version,
        payload={"reply_draft_id": str(draft.id), "text": draft.text},
        summary={"draft_id": str(draft.id), "proposed_text": draft.text},
        required_permission="reply.approve",
        expires_at=clock.now() + timedelta(hours=24),
        is_simulated=False,
    )
    draft.approval_id = approval.id
    db_session.flush()

    notification = Notification(
        id=new_id(),
        workspace_id=ws.id,
        recipient_user_id=owner.id,
        type="approval.requested",
        severity="critical",
        params={"action": approval.action, "summary": approval.summary},
        subject_type="approval",
        subject_id=approval.id,
        dedup_key=f"approval-req:{approval.id}",
        is_simulated=False,
        created_at=clock.now(),
    )
    db_session.add(notification)
    db_session.flush()

    delivery = NotificationDelivery(
        id=new_id(),
        workspace_id=ws.id,
        notification_id=notification.id,
        recipient_user_id=owner.id,
        channel="telegram",
        channel_link_id=link.id,
        status="pending",
    )
    db_session.add(delivery)
    db_session.flush()

    mock_tg = MockTelegramTransport()
    tg_client = TelegramClient(
        token="TEST_BOT_TOKEN", transport=httpx.MockTransport(mock_tg.handle)
    )
    channel = TelegramChannel(client=tg_client)

    recipient = ChannelRecipient(
        user_id=owner.id,
        workspace_id=ws.id,
        channel="telegram",
        channel_user_id=link.channel_user_id,
        channel_chat_id=link.channel_chat_id,
        channel_username=link.channel_username,
        ui_locale="tr",
        timezone=ws.timezone,
    )

    # 1. Delivery to Telegram
    delivery_result = channel.deliver_notification(db_session, clock, delivery, recipient)
    assert delivery_result.success is True
    assert delivery_result.status == "delivered"

    # Verify message sent to Telegram with EXACT draft text
    send_calls = [c for c in mock_tg.calls if c["api_method"] == "sendMessage"]
    assert len(send_calls) == 1
    sent_body = send_calls[0]["body"]
    assert (
        exact_reply_text in sent_body["text"] or html.escape(exact_reply_text) in sent_body["text"]
    )
    assert "@ac1_salon" in sent_body["text"]
    assert "@tugba_k" in sent_body["text"]

    # Verify inline keyboard buttons with act:<token>
    keyboard = sent_body["reply_markup"]["inline_keyboard"]
    approve_button = None
    reject_button = None
    for row in keyboard:
        for btn in row:
            if "Onayla" in btn["text"]:
                approve_button = btn
            elif "Reddet" in btn["text"]:
                reject_button = btn
    assert approve_button is not None
    assert reject_button is not None
    assert approve_button["callback_data"].startswith("act:")
    assert reject_button["callback_data"].startswith("act:")

    approve_token = approve_button["callback_data"].split("act:")[1]
    reject_token = reject_button["callback_data"].split("act:")[1]

    # 2. Owner taps inline approve button
    approve_update = _make_callback_query_update(
        update_id=1001,
        callback_data=f"act:{approve_token}",
        user_id=int(link.channel_user_id),
        chat_id=int(link.channel_chat_id),
        message_id=200,
        message_text=sent_body["text"],
    )
    result_1 = process_update(db_session, clock, approve_update, client=tg_client)
    assert result_1.status == "processed"
    assert result_1.action == "approval_decided"

    # Verify approval state transitions to approved
    db_session.refresh(approval)
    assert approval.status == "approved"
    assert approval.decided_by_user_id == owner.id

    # Verify reply draft state transitions to queued
    db_session.refresh(draft)
    assert draft.status == "queued"

    # Verify reply send side-effect: exactly 1 send_reply job is enqueued in the job ledger (INV-15)
    enqueued_jobs = db_session.scalars(
        select(Job).where(Job.workspace_id == ws.id, Job.job_type == "send_reply")
    ).all()
    assert len(enqueued_jobs) == 1
    assert enqueued_jobs[0].payload.get("reply_draft_id") == str(draft.id)

    # 3. Second press: owner taps the same approve button again (Replay attack / double-tap)
    replay_update = _make_callback_query_update(
        update_id=1002,
        callback_data=f"act:{approve_token}",
        user_id=int(link.channel_user_id),
        chat_id=int(link.channel_chat_id),
        message_id=200,
        message_text=sent_body["text"],
    )
    result_2 = process_update(db_session, clock, replay_update, client=tg_client)
    assert result_2.status == "processed"
    assert result_2.action == "approval_already_decided"

    # Telegram user receives alert modal: "already decided"
    answer_calls = [c for c in mock_tg.calls if c["api_method"] == "answerCallbackQuery"]
    assert len(answer_calls) >= 2
    last_answer = answer_calls[-1]["body"]
    assert "zaten karara bağlandı / Already decided" in last_answer["text"]
    assert last_answer["show_alert"] is True

    # Crucial INV-06: exactly 1 send_reply job remains in the queue — NO second send!
    enqueued_jobs_after = db_session.scalars(
        select(Job).where(Job.workspace_id == ws.id, Job.job_type == "send_reply")
    ).all()
    assert len(enqueued_jobs_after) == 1

    # 4. Third press: owner taps sibling reject button
    reject_update = _make_callback_query_update(
        update_id=1003,
        callback_data=f"act:{reject_token}",
        user_id=int(link.channel_user_id),
        chat_id=int(link.channel_chat_id),
        message_id=200,
        message_text=sent_body["text"],
    )
    result_3 = process_update(db_session, clock, reject_update, client=tg_client)
    assert result_3.status == "processed"
    assert result_3.action == "approval_already_decided"

    # Still strictly 1 send_reply job in ledger
    enqueued_jobs_final = db_session.scalars(
        select(Job).where(Job.workspace_id == ws.id, Job.job_type == "send_reply")
    ).all()
    assert len(enqueued_jobs_final) == 1


# =============================================================================
# AC-2: "Bugün kaç DM geldi?" returns exact same number as web report
# =============================================================================


def test_ac2_telegram_daily_summary_matches_web_report(
    db_session: Session,
    clock: FrozenClock,
) -> None:
    """AC-2: 'Bugün kaç DM geldi?' in Telegram returns the exact same number as the web

    report (get_daily_summary).
    """
    ws, owner, link = _setup_linked_owner(db_session, clock, channel_user_id="88802")
    ctx = WorkspaceContext(
        workspace_id=ws.id,
        actor=ActorRef.user(owner.id),
        role="owner",
        timezone=ws.timezone,
        locale="tr",
        is_demo=False,
    )

    # Seed inbound customer DMs for today using test Builder
    now = clock.now()
    seed_time = now - timedelta(minutes=5)
    builder = Builder(db_session, ws, owner, simulated=False)
    conv1 = builder.conversation(seed_time)
    conv2 = builder.conversation(seed_time)
    for _ in range(4):
        builder.message(conv1, "inbound", seed_time)
    for _ in range(2):
        builder.message(conv2, "inbound", seed_time)
    db_session.commit()

    # 1. Fetch web summary directly via domain reporting service
    web_summary = get_daily_summary(db_session, clock, ctx)
    expected_inbound_count = web_summary["inbound_messages"]
    assert expected_inbound_count == 6

    # 2. Ask Telegram bot: "Bugün kaç DM geldi?"
    mock_tg = MockTelegramTransport()
    tg_client = TelegramClient(
        token="TEST_BOT_TOKEN", transport=httpx.MockTransport(mock_tg.handle)
    )

    query_update = _make_text_update(
        update_id=2001,
        text="Bugün kaç DM geldi?",
        user_id=int(link.channel_user_id),
        chat_id=int(link.channel_chat_id),
    )
    result = process_update(db_session, clock, query_update, client=tg_client)

    assert result.status == "processed"
    assert result.action == "reporting_query"

    # Verify Telegram reply contains exact count matching web report
    send_calls = [c for c in mock_tg.calls if c["api_method"] == "sendMessage"]
    assert len(send_calls) == 1
    sent_text = send_calls[0]["body"]["text"]
    assert f"<b>{expected_inbound_count}</b>" in sent_text
    assert "Gelen Mesajlar" in sent_text

    # Also verify with "Bugünkü özet"
    query_summary_update = _make_text_update(
        update_id=2002,
        text="Bugünkü özet",
        user_id=int(link.channel_user_id),
        chat_id=int(link.channel_chat_id),
    )
    result_summary = process_update(db_session, clock, query_summary_update, client=tg_client)
    assert result_summary.status == "processed"
    assert result_summary.action == "reporting_query"
    sent_text_2 = mock_tg.calls[-1]["body"]["text"]
    assert f"Gelen DM / Mesaj:</b> {expected_inbound_count}" in sent_text_2


# =============================================================================
# AC-3: Photo + "bu story'yi 19:00'da paylaş" creates draft with schedule proposal
# =============================================================================


def test_ac3_photo_with_schedule_caption_creates_story_draft_not_auto_scheduled(
    db_session: Session,
    clock: FrozenClock,
) -> None:
    """AC-3: Sending a photo with "bu story'yi 19:00'da paylaş" creates a story draft with

    that media and a schedule proposal requiring explicit approval (never auto-scheduled
    from free text, INV-04).
    """
    ws, owner, link = _setup_linked_owner(db_session, clock, channel_user_id="88803")

    test_image_bytes = _make_test_jpeg(width=400, height=400, color="teal")
    mock_tg = MockTelegramTransport(photo_bytes=test_image_bytes)
    tg_client = TelegramClient(
        token="TEST_BOT_TOKEN", transport=httpx.MockTransport(mock_tg.handle)
    )

    instruction = "bu story'yi 19:00'da paylaş"
    photo_update = _make_photo_update(
        update_id=3001,
        caption=instruction,
        user_id=int(link.channel_user_id),
        chat_id=int(link.channel_chat_id),
        file_id="photo_story_e2e_3001",
    )

    result = process_update(db_session, clock, photo_update, client=tg_client)
    assert result.status == "processed"
    assert result.action == "photo_draft_created"

    # Verify story draft item created in database
    item = db_session.scalar(select(ContentItem).where(ContentItem.workspace_id == ws.id))
    assert item is not None
    assert item.content_type == "story_image"
    assert item.caption == instruction
    assert item.media_asset_id is not None

    # Verify media asset stored and linked
    asset = db_session.scalar(select(MediaAsset).where(MediaAsset.id == item.media_asset_id))
    assert asset is not None
    assert asset.workspace_id == ws.id
    assert asset.byte_size > 0

    # Invariant INV-04: free text NEVER directly publishes or auto-schedules
    assert item.status in ("draft", "pending_approval")
    assert item.status != "published"

    # Verify confirmation sent back to owner on Telegram
    send_calls = [c for c in mock_tg.calls if c["api_method"] == "sendMessage"]
    assert len(send_calls) == 1
    sent_text = send_calls[0]["body"]["text"]
    assert "Story Taslağı Oluşturuldu" in sent_text
    assert "19:00" in sent_text
    assert "INV-04" in sent_text
    assert "onayınız gerekmektedir" in sent_text


# =============================================================================
# AC-4: Architectural isolation: only channel registry and router import adapter
# =============================================================================


def test_ac4_core_architectural_isolation_import_linter() -> None:
    """AC-4: No core module imports the Telegram adapter except the channel registry

    and webhook router.
    """
    backend_root = Path(__file__).resolve().parents[2]
    app_dir = backend_root / "app"
    assert app_dir.is_dir(), f"app directory not found at {app_dir}"

    core_packages = [
        "commands",
        "approvals",
        "inbox",
        "policy",
        "identity",
        "knowledge",
        "core",
        "audit",
        "jobs",
        "ai",
        "notifications",
        "operations",
        "content",
        "reporting",
        "activity",
        "retention",
    ]

    forbidden_pattern = "app.integrations.channels.telegram"

    violations: list[str] = []

    for pkg_name in core_packages:
        pkg_dir = app_dir / pkg_name
        if not pkg_dir.exists():
            continue

        for py_file in pkg_dir.rglob("*.py"):
            with open(py_file, encoding="utf-8") as f:
                try:
                    tree = ast.parse(f.read(), filename=str(py_file))
                except SyntaxError:
                    continue

            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if forbidden_pattern in alias.name:
                            violations.append(
                                f"{py_file.relative_to(backend_root)}: import {alias.name}"
                            )
                elif isinstance(node, ast.ImportFrom):
                    mod = node.module or ""
                    if forbidden_pattern in mod:
                        violations.append(
                            f"{py_file.relative_to(backend_root)}: from {mod} import ..."
                        )

    assert violations == [], (
        "AC-4 Violation: Core modules directly imported Telegram adapter:\n" + "\n".join(violations)
    )

    # Verify that pyproject.toml explicitly configures the contract for CI
    pyproject_path = backend_root / "pyproject.toml"
    assert pyproject_path.exists()
    content = pyproject_path.read_text(encoding="utf-8")
    expected_rule = (
        "only channel registry and telegram webhook router import telegram channel adapter (AC-4)"
    )
    assert expected_rule in content
