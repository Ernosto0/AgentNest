"""Targeted unit/savepoint regression tests for hardened security and lifecycle fixes."""

from __future__ import annotations

import contextlib
import hashlib
import hmac
import json
import logging
import uuid
from datetime import timedelta
from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent.models import AccountAgent
from app.approvals import service as approvals_service
from app.approvals.action_tokens import ActionTokenService
from app.core.clock import FrozenClock
from app.core.config import Settings
from app.core.context import ActorRef, WorkspaceContext
from app.core.db import set_tenant_context
from app.core.email import email_outbox
from app.core.narrator import validate_metrics_grounding
from app.core.security import hash_password
from app.identity import invites
from app.identity.channels import ChannelLinkService
from app.identity.models import ChannelLinkCode, User
from app.inbox.models import Conversation, Message, ReplyDraft
from app.integrations.channels.telegram import TelegramClient, process_update
from app.integrations.instagram.models import SocialAccount
from app.operations.workspace_lifecycle import request_workspace_deletion
from tests.factories import workspace_with_members


class _MockTelegramHandler:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def handle(self, request: httpx.Request) -> httpx.Response:
        url_path = urlparse(str(request.url)).path
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
        self.calls.append({"api_method": method_name, "body": body})
        if method_name == "sendMessage":
            return httpx.Response(
                200,
                json={
                    "ok": True,
                    "result": {
                        "message_id": len(self.calls) + 10,
                        "chat": {"id": body.get("chat_id", 123456), "type": "private"},
                        "text": body.get("text", ""),
                        "date": 1700000000,
                    },
                },
            )
        return httpx.Response(200, json={"ok": True, "result": True})


def _owner_ctx(ws_id: uuid.UUID, user_id: uuid.UUID, tz: str) -> WorkspaceContext:
    return WorkspaceContext(
        workspace_id=ws_id,
        actor=ActorRef.user(user_id),
        role="owner",
        timezone=tz,
        locale="tr",
        is_demo=False,
    )


def test_blocker1_remove_member_revokes_telegram_link_and_blocks_owner_fallback(
    db_session: Session, clock: FrozenClock
) -> None:
    """Removed members lose active channel links, tokens, and never fall back to 'owner'."""
    ws, users = workspace_with_members(db_session, roles=("owner", "staff"), name="Salon Revoke")
    owner = users["owner"]
    staff = users["staff"]
    set_tenant_context(db_session, ws.id)

    owner_ctx = _owner_ctx(ws.id, owner.id, ws.timezone)
    staff_ctx = WorkspaceContext(
        workspace_id=ws.id,
        actor=ActorRef.user(staff.id),
        role="staff",
        timezone=ws.timezone,
        locale="tr",
        is_demo=False,
    )

    code, _ = ChannelLinkService.generate_link_code(
        db_session, clock, staff_ctx, channel="telegram"
    )
    link = ChannelLinkService.redeem_link_code(
        db_session,
        clock,
        channel="telegram",
        channel_user_id="91001",
        channel_chat_id="91001",
        raw_code=code,
        channel_username="ex_staff",
    )

    social = SocialAccount(
        id=uuid.uuid4(),
        workspace_id=ws.id,
        provider_kind="mock",
        external_account_id=uuid.uuid4().hex,
        username="salon_revoke",
        capabilities={"messaging": True},
        status="connected",
    )
    db_session.add(social)
    db_session.flush()

    conv = Conversation(
        id=uuid.uuid4(),
        workspace_id=ws.id,
        social_account_id=social.id,
        customer_external_id="cust-rev",
        customer_handle="cust_rev",
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
        external_message_id="msg-rev-1",
        text="Fiyat nedir?",
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
        version=1,
        decision="approval_required",
        text="Merhaba!",
        status="pending_approval",
        created_by_actor_type="system",
        is_simulated=True,
    )
    db_session.add(draft)
    db_session.flush()

    approval = approvals_service.request(
        db_session,
        clock,
        owner_ctx,
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

    token = ActionTokenService.create_action_token(
        db_session, clock, staff_ctx, approval, decision="approved", user_id=staff.id
    )
    db_session.flush()

    invites.remove_member(db_session, clock, owner_ctx, user_id=staff.id)

    db_session.refresh(link)
    assert link.status == "unlinked"
    assert link.unlinked_at is not None
    assert (
        ChannelLinkService.resolve_channel_user(
            db_session, channel="telegram", channel_user_id="91001"
        )
        is None
    )
    remaining_codes = db_session.scalars(
        select(ChannelLinkCode).where(
            ChannelLinkCode.workspace_id == ws.id, ChannelLinkCode.user_id == staff.id
        )
    ).all()
    assert remaining_codes == []

    mock_tg = _MockTelegramHandler()
    client = TelegramClient(token="BOT_TEST", transport=httpx.MockTransport(mock_tg.handle))

    # Removed user cannot approve using an old inline button
    cb_result = process_update(
        db_session,
        clock,
        {
            "update_id": 5001,
            "callback_query": {
                "id": "cb-removed",
                "from": {"id": 91001, "is_bot": False, "first_name": "ExStaff"},
                "message": {
                    "message_id": 42,
                    "date": 1700000000,
                    "chat": {"id": 91001, "type": "private"},
                },
                "data": f"act:{token}",
            },
        },
        client=client,
    )
    assert cb_result.status != "processed" or cb_result.action != "approval_approved"
    db_session.refresh(approval)
    assert approval.status == "pending"

    # Removed user cannot issue owner commands (no fallback to "owner")
    cmd_result = process_update(
        db_session,
        clock,
        {
            "update_id": 5002,
            "message": {
                "message_id": 43,
                "date": 1700000000,
                "chat": {"id": 91001, "type": "private"},
                "from": {"id": 91001, "is_bot": False, "first_name": "ExStaff"},
                "text": "Bugün kaç mesaj geldi?",
            },
        },
        client=client,
    )
    assert cmd_result.action == "unlinked_prompt"


def test_blocker3_request_workspace_deletion_pauses_account_agents(
    db_session: Session, clock: FrozenClock
) -> None:
    """KVKK workspace erasure pauses AccountAgent.state='paused' without SQL column error."""
    ws, users = workspace_with_members(db_session, name="Erasure Gym")
    set_tenant_context(db_session, ws.id)
    social = SocialAccount(
        id=uuid.uuid4(),
        workspace_id=ws.id,
        provider_kind="mock",
        external_account_id=uuid.uuid4().hex,
        username="erasure_gym",
        capabilities={"messaging": True},
        status="connected",
    )
    db_session.add(social)
    db_session.flush()

    agent = db_session.scalar(
        select(AccountAgent).where(AccountAgent.social_account_id == social.id)
    )
    assert agent is not None
    agent.state = "active"
    db_session.flush()

    ctx = _owner_ctx(ws.id, users["owner"].id, ws.timezone)
    result = request_workspace_deletion(db_session, clock, ctx, Settings(_env_file=None))
    db_session.flush()
    db_session.refresh(ws)
    db_session.refresh(agent)

    assert result["status"] == "deleting"
    assert ws.status == "deleting"
    assert agent.state == "paused"


def test_blocker4_instagram_webhook_never_logs_raw_body_or_message_text(
    make_client, caplog: pytest.LogCaptureFixture
) -> None:
    """Webhook ingestion logs byte size & counts at INFO/WARNING without raw message body."""
    client = make_client()
    secret_text = "CONFIDENTIAL_CUSTOMER_DM_BODY_98765"
    payload = {
        "object": "instagram",
        "entry": [
            {
                "id": "unknown-ig-account",
                "time": 1700000000,
                "messaging": [
                    {
                        "sender": {"id": "cust-privacy-1"},
                        "recipient": {"id": "unknown-ig-account"},
                        "timestamp": 1700000000000,
                        "message": {"mid": "m-privacy-1", "text": secret_text},
                    }
                ],
            }
        ],
    }
    raw_bytes = json.dumps(payload).encode("utf-8")

    # 1. Unauthenticated / invalid signature request
    with caplog.at_level(logging.INFO):
        res_bad = client.post(
            "/webhooks/instagram/mock",
            content=raw_bytes,
            headers={
                "Content-Type": "application/json",
                "X-Hub-Signature-256": "sha256=deadbeef",
            },
        )
    assert res_bad.status_code == 401
    assert secret_text not in caplog.text

    caplog.clear()

    # 2. Signed request with secret message text
    sig = hmac.new(b"dev-mock-instagram-app-secret", raw_bytes, hashlib.sha256).hexdigest()
    with caplog.at_level(logging.INFO):
        res_ok = client.post(
            "/webhooks/instagram/mock",
            content=raw_bytes,
            headers={
                "Content-Type": "application/json",
                "X-Hub-Signature-256": f"sha256={sig}",
            },
        )
    assert res_ok.status_code == 200
    assert secret_text not in caplog.text
    assert "webhook_received" in caplog.text


def test_serious12_password_reset_rate_limited_and_deferred_to_background_task(
    db_session: Session, make_client, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Password reset enforces IP/email throttle and schedules SMTP outside request handler."""
    email_outbox.clear()
    email = "reset-throttle@example.com"
    user = User(
        id=uuid.uuid4(),
        email=email,
        password_hash=hash_password("initial-secure-password-123"),
        display_name="Reset User",
        ui_locale="en",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()

    scheduled_tasks: list[tuple[Any, tuple[Any, ...], dict[str, Any]]] = []
    from fastapi import BackgroundTasks

    orig_add_task = BackgroundTasks.add_task

    def _spy_add_task(self: BackgroundTasks, func: Any, *args: Any, **kwargs: Any) -> None:
        scheduled_tasks.append((func, args, kwargs))
        orig_add_task(self, func, *args, **kwargs)

    monkeypatch.setattr(BackgroundTasks, "add_task", _spy_add_task)

    client = make_client()
    for i in range(5):
        resp = client.post("/api/v1/auth/password-reset/request", json={"email": email})
        assert resp.status_code == 202, f"attempt {i + 1} failed: {resp.text}"

    # Existing user scheduled password reset email as a BackgroundTask (not inline)
    assert len(scheduled_tasks) == 5
    assert len(email_outbox.get_messages()) == 5

    # 6th request trips RESET_REQUESTS_BEFORE_LOCKOUT (5) -> 429 RATE_LIMITED
    resp_locked = client.post("/api/v1/auth/password-reset/request", json={"email": email})
    assert resp_locked.status_code == 429
    assert resp_locked.json()["code"] == "RATE_LIMITED"


def test_smaller15_validate_metrics_grounding_binds_numbers_to_fields() -> None:
    """Narration grounding catches swapped metric numbers and ungrounded 0/1 values."""
    params = {"inbound_messages": 5, "replies_sent": 2}

    # Swapped metric numbers (2 inbound vs 5 replies)
    swapped = "Bugün 2 gelen mesaj aldık ve 5 yanıt gönderildi."
    problems = validate_metrics_grounding(swapped, params, "bugün durum ne?")
    assert problems != []

    # Ungrounded 0 or 1 not present in params or query
    ungrounded_small = "Bugün 5 gelen mesaj var, 1 hata oldu."
    assert validate_metrics_grounding(ungrounded_small, params, "durum ne?") != []

    # Matching numbers in correct metric clauses pass cleanly
    accurate = "Bugün 5 gelen mesaj aldık ve 2 yanıt gönderildi."
    assert validate_metrics_grounding(accurate, params, "durum ne?") == []
