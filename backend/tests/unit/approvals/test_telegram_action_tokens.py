"""Unit and scenario tests for Telegram Approval Action Tokens & Owner Questions.

Phase 9 Session 06:
- ActionToken creation, cryptographic hashing, and single-use consumption.
- Telegram approval notification formatting with rich preview & inline keyboard buttons.
- Single-use button tap -> ApprovalService.decide execution -> send side effect (AC-1).
- Second tap replay -> 409 / ALREADY_DECIDED -> no duplicate execution (AC-1).
- Forwarded button pressed by unauthorized user -> FORBIDDEN / UNAUTHORIZED rejection.
- Expired action token rejection.
- Stale approval subject version mismatch rejection.
- Owner question notification delivery and inbound reply answering round-trip.
- Stale or closed owner question handling returning current state.

Invariants & Decisions:
- ADR-012, ADR-014, ADR-024, AC-1, INV-04, INV-06, INV-09, INV-16.
"""

from __future__ import annotations

import contextlib
import io
import json
import uuid
from datetime import timedelta
from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from PIL import Image
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent.models import AccountAgent, AgentSession, AgentThread
from app.approvals import service as approvals_service
from app.approvals.action_tokens import ActionTokenService
from app.approvals.models import ActionToken
from app.core.clock import FrozenClock
from app.core.context import ActorRef, WorkspaceContext
from app.core.db import set_tenant_context
from app.core.errors import AppError
from app.core.ids import new_id
from app.identity.channels import ChannelLinkService
from app.identity.models import ChannelLink
from app.inbox.models import Conversation, Message, ReplyDraft
from app.integrations.channels.base import ChannelRecipient
from app.integrations.channels.telegram import (
    TelegramClient,
    process_update,
)
from app.integrations.channels.telegram.adapter import TelegramChannel
from app.integrations.instagram.models import SocialAccount
from app.jobs.models import Job
from app.memory.models import CustomerIdentity
from app.notifications.models import Notification, NotificationDelivery
from app.owner_requests.models import OwnerAnswer, OwnerQuestion
from tests.factories import workspace_with_members


def _make_test_jpeg(width: int = 100, height: int = 100, color: str = "blue") -> bytes:
    img = Image.new("RGB", (width, height), color=color)
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


def _make_social_account(
    db_session: Session, ws_id: uuid.UUID, username: str = "gym"
) -> SocialAccount:
    social = SocialAccount(
        id=new_id(),
        workspace_id=ws_id,
        platform="instagram",
        provider_kind="mock",
        external_account_id=f"ext_{uuid.uuid4().hex[:12]}",
        username=username,
        status="connected",
        capabilities={},
        granted_scopes=[],
    )
    db_session.add(social)
    db_session.flush()

    agent = db_session.scalar(
        select(AccountAgent).where(
            AccountAgent.workspace_id == ws_id,
            AccountAgent.social_account_id == social.id,
        )
    )
    if agent is None:
        agent = AccountAgent(
            id=new_id(),
            workspace_id=ws_id,
            social_account_id=social.id,
            controller_mode="agent",
            state="active",
        )
        db_session.add(agent)
        db_session.flush()

    return social


class MockTelegramHandler:
    """Mock HTTP transport capturing outgoing Telegram Bot API requests."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

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

        return httpx.Response(200, json={"ok": True, "result": {}})


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


def _make_callback_query_update(
    update_id: int,
    callback_data: str,
    user_id: int = 99901,
    chat_id: int = 99901,
    message_id: int = 1001,
    message_text: str = "Test approval notification message",
) -> dict[str, Any]:
    return {
        "update_id": update_id,
        "callback_query": {
            "id": f"cb_{update_id}",
            "from": {
                "id": user_id,
                "is_bot": False,
                "first_name": "Test",
                "username": "test_owner",
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
    user_id: int = 99901,
    chat_id: int = 99901,
    reply_to_message: dict[str, Any] | None = None,
) -> dict[str, Any]:
    msg: dict[str, Any] = {
        "message_id": update_id * 10,
        "date": 1700000000,
        "chat": {"id": chat_id, "type": "private"},
        "from": {"id": user_id, "is_bot": False, "first_name": "Test"},
        "text": text,
    }
    if reply_to_message is not None:
        msg["reply_to_message"] = reply_to_message
    return {"update_id": update_id, "message": msg}


# =============================================================================
# 1. Action Token Service Unit Tests
# =============================================================================


def test_action_token_service_generate_and_consume(
    db_session: Session,
    clock: FrozenClock,
) -> None:
    """Action tokens are 16 bytes base64url, hashed with sha256, and consumed once (INV-16)."""
    ws, owner, link = _setup_linked_owner(db_session, clock, channel_user_id="99901")
    ctx = WorkspaceContext(
        workspace_id=ws.id,
        actor=ActorRef.user(owner.id),
        role="owner",
        timezone=ws.timezone,
        locale="tr",
        is_demo=False,
    )

    approval = approvals_service.request(
        db_session,
        clock,
        ctx,
        kind="confirmation",
        action="command.update_fact",
        subject_type="owner_command",
        subject_id=uuid.uuid4(),
        subject_version=1,
        payload={"amount": "5000"},
        summary={"label": "Fiyat güncelleme"},
        required_permission="knowledge.verify",
        expires_at=clock.now() + timedelta(hours=2),
    )
    db_session.flush()

    # Generate approve & reject tokens
    token_approve = ActionTokenService.create_action_token(
        db_session, clock, ctx, approval, decision="approved", user_id=owner.id
    )
    token_reject = ActionTokenService.create_action_token(
        db_session, clock, ctx, approval, decision="rejected", user_id=owner.id
    )
    db_session.flush()

    assert len(token_approve) >= 22
    assert len(token_reject) >= 22
    assert token_approve != token_reject

    # Tokens exist in DB with hashed storage
    records = db_session.scalars(
        select(ActionToken).where(ActionToken.approval_id == approval.id)
    ).all()
    assert len(records) == 2
    for r in records:
        assert r.workspace_id == ws.id
        assert r.user_id == owner.id
        assert r.used_at is None
        assert r.payload_hash == approval.payload_hash
        assert len(r.token_hash) == 64  # SHA-256 hex digest

    # Valid consumption
    consumed_approval, consumed_token = ActionTokenService.consume_action_token(
        db_session, clock, token_approve, channel_user_id="99901"
    )
    assert consumed_approval.id == approval.id
    assert consumed_token.decision == "approved"
    assert consumed_token.used_at == clock.now()

    # Replay of the exact same token raises APPROVAL_ALREADY_DECIDED
    with pytest.raises(AppError) as exc_info:
        ActionTokenService.consume_action_token(
            db_session, clock, token_approve, channel_user_id="99901"
        )
    assert exc_info.value.code == "APPROVAL_ALREADY_DECIDED"

    # User mismatch: wrong user cannot consume the reject token
    with pytest.raises(AppError) as exc_info2:
        ActionTokenService.consume_action_token(
            db_session, clock, token_reject, channel_user_id="99999_wrong"
        )
    assert exc_info2.value.code == "FORBIDDEN"

    # Expiry
    clock.advance(hours=3)
    with pytest.raises(AppError) as exc_info3:
        ActionTokenService.consume_action_token(
            db_session, clock, token_reject, channel_user_id="99901"
        )
    assert exc_info3.value.code == "APPROVAL_EXPIRED"


# =============================================================================
# 2. Telegram Approval Notification Delivery & Buttons
# =============================================================================


def test_telegram_approval_notification_delivery_and_inline_keyboard(
    db_session: Session,
    clock: FrozenClock,
) -> None:
    """Delivering approval.requested formats rich text and inline keyboard buttons."""
    ws, owner, link = _setup_linked_owner(db_session, clock, channel_user_id="99902")
    ctx = WorkspaceContext(
        workspace_id=ws.id,
        actor=ActorRef.user(owner.id),
        role="owner",
        timezone=ws.timezone,
        locale="tr",
        is_demo=False,
    )

    social = _make_social_account(db_session, ws.id, username="guzellik_merkezi")

    conv = Conversation(
        id=new_id(),
        workspace_id=ws.id,
        social_account_id=social.id,
        customer_external_id="cust_777",
        customer_handle="merve_y",
        handling_mode="automatic",
        attention="none",
        last_inbound_at=clock.now(),
        is_simulated=True,
    )
    db_session.add(conv)
    db_session.flush()

    msg = Message(
        id=new_id(),
        workspace_id=ws.id,
        social_account_id=social.id,
        conversation_id=conv.id,
        direction="inbound",
        sender_kind="customer",
        external_message_id="msg_777_1",
        text="Lazer epilasyon seans fiyatınız nedir?",
        provider_timestamp=clock.now(),
        is_simulated=True,
    )
    db_session.add(msg)
    db_session.flush()

    draft = ReplyDraft(
        id=new_id(),
        workspace_id=ws.id,
        conversation_id=conv.id,
        covers_through_message_id=msg.id,
        source="ai",
        origin="legacy",
        status="pending_approval",
        decision="approval_required",
        text="Merhaba Merve Hanım, tüm vücut lazer epilasyon seans ücretimiz 1.500 TL'dir.",
        version=1,
        created_by_actor_type="system",
        is_simulated=True,
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
        payload={"draft_id": str(draft.id), "text": draft.text},
        summary={"draft_id": str(draft.id), "proposed_text": draft.text},
        required_permission="reply.approve",
        expires_at=clock.now() + timedelta(hours=24),
        is_simulated=True,
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
        is_simulated=True,
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

    mock_tg = MockTelegramHandler()
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

    result = channel.deliver_notification(db_session, clock, delivery, recipient)
    assert result.success is True
    assert result.status == "delivered"

    assert len(mock_tg.calls) == 1
    sent_body = mock_tg.calls[0]["body"]
    sent_text = sent_body["text"]

    # Invariants & details verification
    assert "[SİMÜLASYON]" in sent_text  # INV-09
    assert "@guzellik_merkezi" in sent_text
    assert "@merve_y" in sent_text
    assert "Lazer epilasyon seans fiyatınız nedir?" in sent_text
    assert "1.500 TL" in sent_text

    # Buttons verification
    markup = sent_body.get("reply_markup", {})
    keyboard = markup.get("inline_keyboard", [])
    assert len(keyboard) == 2
    row1 = keyboard[0]
    assert len(row1) == 2
    assert row1[0]["text"] == "✅ Onayla"
    assert row1[0]["callback_data"].startswith("act:")
    assert row1[1]["text"] == "❌ Reddet"
    assert row1[1]["callback_data"].startswith("act:")
    row2 = keyboard[1]
    assert row2[0]["text"] == "📱 Uygulamada Aç"
    assert "/approvals" in row2[0]["url"]


# =============================================================================
# 3. Acceptance Criterion 1: Single-Use Button Tap -> Send -> Replay Blocked
# =============================================================================


def test_telegram_approval_button_single_use_and_replay_protection(
    db_session: Session,
    clock: FrozenClock,
) -> None:
    """AC-1: Owner approves via Telegram button -> reply sent -> second press is rejected."""
    ws, owner, link = _setup_linked_owner(db_session, clock, channel_user_id="99903")
    ctx = WorkspaceContext(
        workspace_id=ws.id,
        actor=ActorRef.user(owner.id),
        role="owner",
        timezone=ws.timezone,
        locale="tr",
        is_demo=False,
    )

    social = _make_social_account(db_session, ws.id, username="kuafortest")

    conv = Conversation(
        id=new_id(),
        workspace_id=ws.id,
        social_account_id=social.id,
        customer_external_id="cust_888",
        customer_handle="zeynep_b",
        handling_mode="automatic",
        attention="none",
        last_inbound_at=clock.now(),
        is_simulated=True,
    )
    db_session.add(conv)
    db_session.flush()

    msg = Message(
        id=new_id(),
        workspace_id=ws.id,
        social_account_id=social.id,
        conversation_id=conv.id,
        direction="inbound",
        sender_kind="customer",
        external_message_id="msg_888_1",
        text="Randevu alabilir miyim?",
        provider_timestamp=clock.now(),
        is_simulated=True,
    )
    db_session.add(msg)
    db_session.flush()

    draft = ReplyDraft(
        id=new_id(),
        workspace_id=ws.id,
        conversation_id=conv.id,
        covers_through_message_id=msg.id,
        source="ai",
        origin="legacy",
        status="pending_approval",
        decision="approval_required",
        text="Tabii ki Zeynep Hanım, hangi gün ve saat için istersiniz?",
        version=1,
        created_by_actor_type="system",
        is_simulated=True,
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
        is_simulated=True,
    )
    draft.approval_id = approval.id
    db_session.flush()

    # Create tokens
    token_approve = ActionTokenService.create_action_token(
        db_session, clock, ctx, approval, decision="approved", user_id=owner.id
    )
    token_reject = ActionTokenService.create_action_token(
        db_session, clock, ctx, approval, decision="rejected", user_id=owner.id
    )
    db_session.flush()

    mock_tg = MockTelegramHandler()
    tg_client = TelegramClient(
        token="TEST_BOT_TOKEN", transport=httpx.MockTransport(mock_tg.handle)
    )

    # 1. First button press: approve
    update_1 = _make_callback_query_update(
        update_id=101,
        callback_data=f"act:{token_approve}",
        user_id=int(link.channel_user_id),
        chat_id=int(link.channel_chat_id),
        message_id=505,
    )
    res_1 = process_update(db_session, clock, update_1, client=tg_client)

    assert res_1.status == "processed"
    assert res_1.action == "approval_decided"

    # Domain state verified
    db_session.refresh(approval)
    db_session.refresh(draft)
    assert approval.status == "approved"
    assert draft.status == "queued"

    # Outgoing send_reply job was enqueued (INV-15)
    enqueued_jobs = db_session.scalars(
        select(Job).where(Job.workspace_id == ws.id, Job.job_type == "send_reply")
    ).all()
    assert len(enqueued_jobs) == 1

    # Telegram acknowledged and updated message
    api_methods = [c["api_method"] for c in mock_tg.calls]
    assert "answerCallbackQuery" in api_methods
    assert "editMessageText" in api_methods

    # 2. Second button press: replay same token (AC-1)
    update_2 = _make_callback_query_update(
        update_id=102,
        callback_data=f"act:{token_approve}",
        user_id=int(link.channel_user_id),
        chat_id=int(link.channel_chat_id),
        message_id=505,
    )
    res_2 = process_update(db_session, clock, update_2, client=tg_client)

    assert res_2.status == "processed"
    assert res_2.action == "approval_already_decided"

    # Exactly 1 send_reply job in ledger: no second side-effect! (INV-06, AC-1)
    enqueued_jobs_after = db_session.scalars(
        select(Job).where(Job.workspace_id == ws.id, Job.job_type == "send_reply")
    ).all()
    assert len(enqueued_jobs_after) == 1

    # Alert shown to user in Telegram
    answer_calls = [c for c in mock_tg.calls if c["api_method"] == "answerCallbackQuery"]
    assert len(answer_calls) >= 1
    assert "zaten karara bağlandı / Already decided" in answer_calls[-1]["body"]["text"]
    assert answer_calls[-1]["body"]["show_alert"] is True

    # 3. Third press: sister token (reject button on same approved item)
    update_3 = _make_callback_query_update(
        update_id=103,
        callback_data=f"act:{token_reject}",
        user_id=int(link.channel_user_id),
        chat_id=int(link.channel_chat_id),
        message_id=505,
    )
    res_3 = process_update(db_session, clock, update_3, client=tg_client)
    assert res_3.action == "approval_already_decided"
    assert len(db_session.scalars(select(Job).where(Job.job_type == "send_reply")).all()) == 1


# =============================================================================
# 4. Security Tests: Wrong User, Expired, Stale Subject
# =============================================================================


def test_forwarded_button_wrong_user_rejected(
    db_session: Session,
    clock: FrozenClock,
) -> None:
    """A forwarded approval message pressed by another user is strictly rejected."""
    ws, owner, link = _setup_linked_owner(db_session, clock, channel_user_id="99904")
    # Setup second linked owner for a different user
    ws2, user2, link2 = _setup_linked_owner(
        db_session, clock, channel_user_id="99905", name="Second Salon"
    )

    ctx = WorkspaceContext(
        workspace_id=ws.id,
        actor=ActorRef.user(owner.id),
        role="owner",
        timezone=ws.timezone,
        locale="tr",
        is_demo=False,
    )

    approval = approvals_service.request(
        db_session,
        clock,
        ctx,
        kind="confirmation",
        action="command.update_fact",
        subject_type="owner_command",
        subject_id=uuid.uuid4(),
        subject_version=1,
        payload={"price": "100"},
        summary={"label": "Test"},
        required_permission="knowledge.verify",
        expires_at=clock.now() + timedelta(hours=2),
    )
    db_session.flush()

    token_approve = ActionTokenService.create_action_token(
        db_session, clock, ctx, approval, decision="approved", user_id=owner.id
    )
    db_session.flush()

    mock_tg = MockTelegramHandler()
    tg_client = TelegramClient(
        token="TEST_BOT_TOKEN", transport=httpx.MockTransport(mock_tg.handle)
    )

    # User 2 taps User 1's token
    update = _make_callback_query_update(
        update_id=201,
        callback_data=f"act:{token_approve}",
        user_id=int(link2.channel_user_id),
        chat_id=int(link2.channel_chat_id),
    )
    res = process_update(db_session, clock, update, client=tg_client)

    assert res.action == "approval_unauthorized"
    assert approval.status == "pending"
    last_call = mock_tg.calls[-1]
    assert "yetkiniz yok / Unauthorized" in last_call["body"]["text"]
    assert last_call["body"]["show_alert"] is True


def test_expired_approval_button_rejected(
    db_session: Session,
    clock: FrozenClock,
) -> None:
    """An action token tapped after approval expiry returns APPROVAL_EXPIRED with alert."""
    ws, owner, link = _setup_linked_owner(db_session, clock, channel_user_id="99906")
    ctx = WorkspaceContext(
        workspace_id=ws.id,
        actor=ActorRef.user(owner.id),
        role="owner",
        timezone=ws.timezone,
        locale="tr",
        is_demo=False,
    )

    approval = approvals_service.request(
        db_session,
        clock,
        ctx,
        kind="confirmation",
        action="command.update_fact",
        subject_type="owner_command",
        subject_id=uuid.uuid4(),
        subject_version=1,
        payload={"price": "100"},
        summary={"label": "Test"},
        required_permission="knowledge.verify",
        expires_at=clock.now() + timedelta(minutes=10),
    )
    db_session.flush()

    token_approve = ActionTokenService.create_action_token(
        db_session, clock, ctx, approval, decision="approved", user_id=owner.id
    )
    db_session.flush()

    # Advance clock past expiry
    clock.advance(minutes=15)

    mock_tg = MockTelegramHandler()
    tg_client = TelegramClient(
        token="TEST_BOT_TOKEN", transport=httpx.MockTransport(mock_tg.handle)
    )

    update = _make_callback_query_update(
        update_id=202,
        callback_data=f"act:{token_approve}",
        user_id=int(link.channel_user_id),
        chat_id=int(link.channel_chat_id),
    )
    res = process_update(db_session, clock, update, client=tg_client)

    assert res.action == "approval_expired"
    assert approval.status == "pending"  # not decided
    answer_calls = [c for c in mock_tg.calls if c["api_method"] == "answerCallbackQuery"]
    assert len(answer_calls) >= 1
    assert "süresi doldu / Approval expired" in answer_calls[-1]["body"]["text"]
    assert answer_calls[-1]["body"]["show_alert"] is True


def test_stale_approval_subject_edited_rejected(
    db_session: Session,
    clock: FrozenClock,
) -> None:
    """Editing the underlying subject makes existing tokens stale (INV-16)."""
    ws, owner, link = _setup_linked_owner(db_session, clock, channel_user_id="99907")
    ctx = WorkspaceContext(
        workspace_id=ws.id,
        actor=ActorRef.user(owner.id),
        role="owner",
        timezone=ws.timezone,
        locale="tr",
        is_demo=False,
    )

    social = _make_social_account(db_session, ws.id, username="stale_test")

    conv = Conversation(
        id=new_id(),
        workspace_id=ws.id,
        social_account_id=social.id,
        customer_external_id="cust_stale",
        customer_handle="stale_cust",
        handling_mode="automatic",
        attention="none",
        last_inbound_at=clock.now(),
        is_simulated=True,
    )
    db_session.add(conv)
    db_session.flush()

    msg = Message(
        id=new_id(),
        workspace_id=ws.id,
        social_account_id=social.id,
        conversation_id=conv.id,
        direction="inbound",
        sender_kind="customer",
        external_message_id="msg_stale_1",
        text="Saat kaçta açıksınız?",
        provider_timestamp=clock.now(),
        is_simulated=True,
    )
    db_session.add(msg)
    db_session.flush()

    draft = ReplyDraft(
        id=new_id(),
        workspace_id=ws.id,
        conversation_id=conv.id,
        covers_through_message_id=msg.id,
        source="ai",
        origin="legacy",
        status="pending_approval",
        decision="approval_required",
        text="Sabah 09:00'da açılıyoruz.",
        version=1,
        created_by_actor_type="system",
        is_simulated=True,
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
        payload={"draft_id": str(draft.id), "text": draft.text},
        summary={"draft_id": str(draft.id), "proposed_text": draft.text},
        required_permission="reply.approve",
        expires_at=clock.now() + timedelta(hours=24),
    )
    draft.approval_id = approval.id
    db_session.flush()

    token_approve = ActionTokenService.create_action_token(
        db_session, clock, ctx, approval, decision="approved", user_id=owner.id
    )
    db_session.flush()

    # Subject is edited: increments version
    draft.version = 2
    draft.text = "Sabah 08:30'da açılıyoruz."
    db_session.flush()

    mock_tg = MockTelegramHandler()
    tg_client = TelegramClient(
        token="TEST_BOT_TOKEN", transport=httpx.MockTransport(mock_tg.handle)
    )

    update = _make_callback_query_update(
        update_id=203,
        callback_data=f"act:{token_approve}",
        user_id=int(link.channel_user_id),
        chat_id=int(link.channel_chat_id),
    )
    res = process_update(db_session, clock, update, client=tg_client)

    assert res.action == "approval_stale"
    answer_calls = [c for c in mock_tg.calls if c["api_method"] == "answerCallbackQuery"]
    assert len(answer_calls) >= 1
    assert "içeriği değişti / Approval stale" in answer_calls[-1]["body"]["text"]
    assert answer_calls[-1]["body"]["show_alert"] is True


# =============================================================================
# 5. Phase 7.5 Owner Questions: Notification & Answering Round-Trip
# =============================================================================


def test_owner_question_delivery_and_answer_round_trip(
    db_session: Session,
    clock: FrozenClock,
) -> None:
    """Owner question delivered to Telegram and answered via inbound text (ADR-024)."""
    ws, owner, link = _setup_linked_owner(db_session, clock, channel_user_id="99908")

    social = _make_social_account(db_session, ws.id, username="soru_hesap")

    conv = Conversation(
        id=new_id(),
        workspace_id=ws.id,
        social_account_id=social.id,
        customer_external_id="cust_oq_1",
        customer_handle="emre_k",
        handling_mode="automatic",
        attention="none",
        last_inbound_at=clock.now(),
        is_simulated=True,
    )
    db_session.add(conv)
    db_session.flush()

    ident = CustomerIdentity(
        id=new_id(),
        workspace_id=ws.id,
        social_account_id=social.id,
        provider_subject_hash="hash_oq_1",
        evidence_kind="inbound",
        created_at=clock.now(),
    )
    db_session.add(ident)
    db_session.flush()

    thread = AgentThread(
        id=new_id(),
        workspace_id=ws.id,
        social_account_id=social.id,
        surface="dm",
        source_ref=str(conv.id),
        dm_conversation_id=conv.id,
        customer_identity_id=ident.id,
        state="waiting_owner",
        handling_mode="agent",
        event_cursor=1,
        thread_version=1,
        ownership_generation=1,
        deletion_generation=0,
        last_activity_at=clock.now(),
        created_at=clock.now(),
        updated_at=clock.now(),
    )
    db_session.add(thread)
    db_session.flush()

    session_obj = AgentSession(
        id=new_id(),
        workspace_id=ws.id,
        thread_id=thread.id,
        initiating_event_cursor=1,
        goal_key="event:1",
        status="waiting_owner",
        created_at=clock.now(),
        updated_at=clock.now(),
    )
    db_session.add(session_obj)
    db_session.flush()

    msg = Message(
        id=new_id(),
        workspace_id=ws.id,
        social_account_id=social.id,
        conversation_id=conv.id,
        direction="inbound",
        sender_kind="customer",
        external_message_id="msg_oq_1",
        text="Yarın manikür için müsait misiniz?",
        provider_timestamp=clock.now(),
        is_simulated=True,
    )
    db_session.add(msg)
    db_session.flush()

    # Create OwnerQuestion
    q = OwnerQuestion(
        id=new_id(),
        workspace_id=ws.id,
        social_account_id=social.id,
        thread_id=thread.id,
        session_id=session_obj.id,
        customer_identity_id=ident.id,
        source_message_id=msg.id,
        source_cursor=1,
        source_hash="oq_hash_1",
        knowledge_fence="kf_1",
        ownership_generation=1,
        deletion_generation=0,
        required_info="availability",
        visibility="customer_reply",
        continuation_key=f"cont_key_{uuid.uuid4()}",
        body="Yarın saat 14:00 manikür için müsait mi?",
        state="pending",
        version=1,
        created_at=clock.now(),
        expires_at=clock.now() + timedelta(days=2),
    )
    db_session.add(q)
    db_session.flush()

    # Deliver notification to Telegram
    notification = Notification(
        id=new_id(),
        workspace_id=ws.id,
        recipient_user_id=owner.id,
        type="owner_question.created",
        severity="attention",
        params={"question_id": str(q.id), "body": q.body},
        subject_type="owner_question",
        subject_id=q.id,
        dedup_key=f"oq-req:{q.id}",
        is_simulated=True,
        created_at=clock.now(),
    )
    db_session.add(notification)
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

    mock_tg = MockTelegramHandler()
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

    del_res = channel.deliver_notification(db_session, clock, delivery, recipient)
    assert del_res.success is True

    sent_text = mock_tg.calls[0]["body"]["text"]
    assert "Asistanınız Bilgi Bekliyor" in sent_text
    assert "Yarın saat 14:00 manikür için müsait mi?" in sent_text
    assert "Müsaitlik / Randevu" in sent_text
    assert "Bu mesaja yanıt vererek" in sent_text

    # Owner responds via Telegram
    reply_payload = _make_text_update(
        update_id=301,
        text="Evet, yarın 14:00 manikür için uygundur.",
        user_id=int(link.channel_user_id),
        chat_id=int(link.channel_chat_id),
    )
    proc_res = process_update(db_session, clock, reply_payload, client=tg_client)

    assert proc_res.status == "processed"
    assert proc_res.action == "owner_question_answered"

    # Verify OwnerQuestion updated and answer created
    db_session.refresh(q)
    assert q.state == "answered"
    assert q.answer_id is not None
    answer = db_session.get(OwnerAnswer, q.answer_id)
    assert answer is not None
    assert answer.body == "Evet, yarın 14:00 manikür için uygundur."
    assert answer.author_user_id == owner.id

    # Confirmation sent to Telegram
    confirm_text = mock_tg.calls[-1]["body"]["text"]
    assert "Bilgi kaydedildi ve asistana iletildi" in confirm_text


def test_closed_or_stale_owner_question_reports_state(
    db_session: Session,
    clock: FrozenClock,
) -> None:
    """Answering an already closed question reports current state without crashing."""
    ws, owner, link = _setup_linked_owner(db_session, clock, channel_user_id="99909")

    social = _make_social_account(db_session, ws.id, username="stale_q_hesap")

    conv = Conversation(
        id=new_id(),
        workspace_id=ws.id,
        social_account_id=social.id,
        customer_external_id="cust_closed_1",
        customer_handle="closed_cust",
        handling_mode="automatic",
        attention="none",
        last_inbound_at=clock.now(),
        is_simulated=True,
    )
    db_session.add(conv)
    db_session.flush()

    ident = CustomerIdentity(
        id=new_id(),
        workspace_id=ws.id,
        social_account_id=social.id,
        provider_subject_hash="hash_closed_1",
        evidence_kind="inbound",
        created_at=clock.now(),
    )
    db_session.add(ident)
    db_session.flush()

    thread = AgentThread(
        id=new_id(),
        workspace_id=ws.id,
        social_account_id=social.id,
        surface="dm",
        source_ref=str(conv.id),
        dm_conversation_id=conv.id,
        customer_identity_id=ident.id,
        state="waiting_owner",
        handling_mode="agent",
        event_cursor=1,
        thread_version=1,
        ownership_generation=1,
        deletion_generation=0,
        last_activity_at=clock.now(),
        created_at=clock.now(),
        updated_at=clock.now(),
    )
    db_session.add(thread)
    db_session.flush()

    session_obj = AgentSession(
        id=new_id(),
        workspace_id=ws.id,
        thread_id=thread.id,
        initiating_event_cursor=1,
        goal_key="event:1",
        status="waiting_owner",
        created_at=clock.now(),
        updated_at=clock.now(),
    )
    db_session.add(session_obj)
    db_session.flush()

    # Question already answered/closed
    q = OwnerQuestion(
        id=new_id(),
        workspace_id=ws.id,
        social_account_id=social.id,
        thread_id=thread.id,
        session_id=session_obj.id,
        customer_identity_id=ident.id,
        source_message_id=None,
        source_cursor=1,
        source_hash="oq_hash_2",
        knowledge_fence="kf_2",
        ownership_generation=1,
        deletion_generation=0,
        required_info="availability",
        visibility="customer_reply",
        continuation_key=f"cont_key_{uuid.uuid4()}",
        body="Eski soru?",
        state="answered",  # closed
        version=2,
        created_at=clock.now() - timedelta(hours=2),
        expires_at=clock.now() + timedelta(days=2),
    )
    db_session.add(q)
    db_session.flush()

    mock_tg = MockTelegramHandler()
    tg_client = TelegramClient(
        token="TEST_BOT_TOKEN", transport=httpx.MockTransport(mock_tg.handle)
    )

    # Owner tries to reply to closed question with prefix
    reply_payload = _make_text_update(
        update_id=302,
        text="Cevap: Ek bilgi vermek istiyorum",
        user_id=int(link.channel_user_id),
        chat_id=int(link.channel_chat_id),
    )
    proc_res = process_update(db_session, clock, reply_payload, client=tg_client)

    assert proc_res.action == "owner_question_stale"
    last_text = mock_tg.calls[-1]["body"]["text"]
    assert "Bu soru artık yanıt beklememektedir" in last_text
    assert "answered" in last_text
