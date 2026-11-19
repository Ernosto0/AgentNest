"""Offline unit tests for Session 01 Telegram notification dispatch, delivery ambiguity,
membership/link rechecks, and informed Account Agent approval descriptions.

These tests execute without a live PostgreSQL server (using MockTransport and in-memory stubs)
to verify:
- Explicit TELEGRAM_TYPES catalog coverage and exclusion of routine/suggestion types.
- dispatch_telegram eligibility (active link, active member, non-simulated, savepoint isolation).
- dispatch_channel_notification idempotency per (workspace_id, notification_id, user_id, channel).
- TelegramClient transport error redaction, retryable (429/5xx) vs ambiguous (timeout/malformed)
  vs terminal (4xx) classification.
- TelegramChannel send_state='sending' pre-commit marker, no open transaction during HTTP send,
  stale 'sending' marker refusal, and non-pending/expired approval skipping.
- Informed descriptions for Account Agent approvals (subject_type == 'agent_action'):
  dm.send (with D-01 fact sources), comment.reply, comment.private_reply,
  comment.hide/unhide/delete, content.prepare/schedule/publish/cancel,
  and calendar.book/reschedule/cancel.
"""

from __future__ import annotations

import contextlib
import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest

from app.agent.models import AgentAction
from app.approvals.action_tokens import ActionTokenService
from app.approvals.models import Approval
from app.comments.models import (
    PrivateReplyOpportunity,
    PublicComment,
    PublicMedia,
)
from app.content.models import ContentItem
from app.core.clock import FrozenClock
from app.core.context import ActorRef, WorkspaceContext
from app.core.errors import RetryableError
from app.identity.models import ChannelLink, User, Workspace, WorkspaceMember
from app.inbox.models import Conversation, Message, ReplyDraft
from app.integrations.calendar.models import CalendarAppointment
from app.integrations.channels.base import ChannelRecipient
from app.integrations.channels.registry import register_channel, reset_channel_registry
from app.integrations.channels.telegram.adapter import (
    TelegramChannel,
    _append_agent_action_lines,
    _format_notification_text,
)
from app.integrations.channels.telegram.client import TelegramApiError, TelegramClient
from app.integrations.instagram.models import SocialAccount
from app.jobs.registry import JobContext
from app.notifications.catalog import (
    CATALOG,
    PUSH_TYPES,
    TELEGRAM_TYPES,
    WHATSAPP_TYPES,
)
from app.notifications.delivery_ledger import (
    DeliverChannelNotificationPayload,
    dispatch_channel_notification,
)
from app.notifications.delivery_policy import (
    IMMEDIATE_TYPES,
    QUIET_HOURS_TYPES,
    ROUTINE_INFO_TYPES,
    evaluate_delivery_policy,
)
from app.notifications.jobs import deliver_channel_notification
from app.notifications.models import Notification, NotificationDelivery
from app.notifications.telegram_dispatch import dispatch_telegram

NOW = datetime(2026, 11, 19, 12, 0, tzinfo=UTC)
BOT_TOKEN = "123456:ABC-SECRET-BOT-TOKEN-XYZ"


class InMemoryStoreSession:
    """Minimal in-memory SQLAlchemy Session double for unit-testing delivery & adapter logic."""

    def __init__(self) -> None:
        self.by_key: dict[tuple[type[Any], Any], Any] = {}
        self.scalars_map: dict[type[Any], list[Any]] = {}
        self.added: list[Any] = []
        self.commits: int = 0
        self.flushes: int = 0
        self.in_tx: bool = True

    def put(self, obj: Any, key: Any | None = None) -> Any:
        k = key if key is not None else getattr(obj, "id", None)
        self.by_key[(type(obj), k)] = obj
        self.scalars_map.setdefault(type(obj), []).append(obj)
        return obj

    def get(self, model: type[Any], ident: Any, **_: Any) -> Any:
        self.in_tx = True
        return self.by_key.get((model, ident))

    def scalar(self, stmt: Any) -> Any:
        self.in_tx = True
        # Match the queried model from statement column descriptions
        for model, items in self.scalars_map.items():
            sql_str = str(stmt)
            table_name = getattr(model, "__tablename__", "")
            if table_name and f"FROM {table_name}" in sql_str:
                return items[0] if items else None
        return None

    def add(self, obj: Any) -> None:
        self.in_tx = True
        if getattr(obj, "id", None) is None:
            with contextlib.suppress(Exception):
                obj.id = uuid.uuid4()
        self.added.append(obj)
        self.put(obj)

    def flush(self) -> None:
        self.flushes += 1

    def commit(self) -> None:
        self.commits += 1
        self.in_tx = False

    def in_transaction(self) -> bool:
        return self.in_tx

    @contextlib.contextmanager
    def begin_nested(self) -> Any:
        yield self


# =============================================================================
# 1. Catalog & Delivery Policy Coverage for TELEGRAM_TYPES
# =============================================================================


def test_telegram_types_explicitly_defined_and_valid() -> None:
    assert set(TELEGRAM_TYPES) <= set(CATALOG)
    # Every Push and WhatsApp type is also supported on Telegram
    assert set(PUSH_TYPES) <= set(TELEGRAM_TYPES)
    assert set(WHATSAPP_TYPES) <= set(TELEGRAM_TYPES)
    # All required categories from Session 01 brief are present
    expected = {
        "approval.requested",
        "approval.expired",
        "owner_question.requested",
        "owner_question.window_closed",
        "content.failed",
        "content.on_hold",
        "reply.failed",
        "conversation.needs_human",
        "account.needs_reauth",
        "account.degraded",
        "account.permission_missing",
        "quota.warning",
        "quota.grace",
        "quota.paused",
        "report.daily_ready",
        "report.missed_customers_ready",
    }
    assert expected == TELEGRAM_TYPES
    # Routine info and weekly delegation suggestions are never pushed to Telegram
    excluded = {
        "content.published",
        "knowledge.fact_changed",
        "knowledge.promotion_expired",
        "account.recovered",
        "member.joined",
        "owner_question.expired",
        "delegation_suggestion",
    }
    assert TELEGRAM_TYPES.isdisjoint(excluded)
    assert TELEGRAM_TYPES.isdisjoint(ROUTINE_INFO_TYPES)
    assert TELEGRAM_TYPES <= (IMMEDIATE_TYPES | QUIET_HOURS_TYPES)


@pytest.mark.parametrize("notif_type", sorted(TELEGRAM_TYPES))
def test_every_telegram_type_delivers_during_daytime_and_respects_quiet_hours(
    notif_type: str,
) -> None:
    spec = CATALOG[notif_type]
    recipient = ChannelRecipient(
        user_id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        channel="telegram",
        timezone="Europe/Istanbul",
    )
    notif = Notification(
        id=uuid.uuid4(),
        workspace_id=recipient.workspace_id,
        recipient_user_id=recipient.user_id,
        type=notif_type,
        severity=spec.severity,
        params={},
    )
    # 12:00 UTC = 15:00 Europe/Istanbul (awake)
    day_clock = FrozenClock(NOW)
    day_decision = evaluate_delivery_policy(notif, recipient, day_clock, channel="telegram")
    assert day_decision.should_deliver is True
    assert day_decision.status == "pending"

    # 21:00 UTC = 00:00 Europe/Istanbul (quiet hours)
    night_clock = FrozenClock(datetime(2026, 11, 19, 21, 0, tzinfo=UTC))
    night_decision = evaluate_delivery_policy(notif, recipient, night_clock, channel="telegram")
    if spec.severity == "critical" or notif_type == "account.needs_reauth":
        assert night_decision.should_deliver is True
        assert night_decision.bypassed_quiet_hours is True
    else:
        assert night_decision.should_deliver is False
        assert night_decision.status == "skipped_quiet_hours"


# =============================================================================
# 2. TelegramClient Error Classification & Token Redaction
# =============================================================================


@pytest.mark.parametrize(
    ("status_code", "expected_retryable"),
    [
        (400, False),
        (401, False),
        (403, False),
        (404, False),
        (429, True),
        (500, True),
        (502, True),
        (503, True),
    ],
)
def test_telegram_client_classifies_http_status_codes_and_redacts_token(
    status_code: int,
    expected_retryable: bool,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status_code,
            json={
                "ok": False,
                "error_code": status_code,
                "description": f"Failed for token {BOT_TOKEN}",
            },
        )

    client = TelegramClient(token=BOT_TOKEN, transport=httpx.MockTransport(handler))
    with pytest.raises(TelegramApiError) as exc_info:
        client.send_message(chat_id="998877", text="Hello")

    err = exc_info.value
    assert err.status_code == status_code
    assert err.retryable is expected_retryable
    assert err.ambiguous is False
    assert BOT_TOKEN not in str(err)
    assert BOT_TOKEN not in (err.description or "")


@pytest.mark.parametrize("exc_cls", [httpx.ReadTimeout, httpx.WriteTimeout, httpx.ConnectError])
def test_telegram_client_transport_error_is_ambiguous_and_redacts_token(
    exc_cls: type[httpx.RequestError],
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise exc_cls(f"Timeout contacting {request.url}", request=request)

    client = TelegramClient(token=BOT_TOKEN, transport=httpx.MockTransport(handler))
    with pytest.raises(TelegramApiError) as exc_info:
        client.send_message(chat_id="998877", text="Hello")

    err = exc_info.value
    assert err.ambiguous is True
    assert err.retryable is False
    assert BOT_TOKEN not in str(err)


# =============================================================================
# 3. TelegramChannel Ambiguity Handling, Pre-Send Commit & Rechecks
# =============================================================================


def _seed_basic_world(
    *,
    notif_type: str = "reply.failed",
    is_simulated: bool = False,
    link_status: str = "active",
) -> tuple[InMemoryStoreSession, Workspace, User, ChannelLink, Notification, NotificationDelivery]:
    store = InMemoryStoreSession()
    ws = store.put(
        Workspace(
            id=uuid.uuid4(),
            name="Pilot Salon",
            slug="pilot-salon",
            timezone="Europe/Istanbul",
            default_locale="tr",
            currency="TRY",
            is_demo=False,
        )
    )
    user = store.put(
        User(
            id=uuid.uuid4(),
            email="owner@example.com",
            display_name="Ayşe Yılmaz",
            ui_locale="tr",
            is_active=True,
        )
    )
    store.put(
        WorkspaceMember(
            workspace_id=ws.id,
            user_id=user.id,
            role="owner",
        ),
        key=(ws.id, user.id),
    )
    link = store.put(
        ChannelLink(
            id=uuid.uuid4(),
            workspace_id=ws.id,
            user_id=user.id,
            channel="telegram",
            channel_user_id="777001",
            channel_chat_id="777001",
            channel_username="ayse_owner",
            status=link_status,
            linked_at=NOW,
        )
    )
    notif = store.put(
        Notification(
            id=uuid.uuid4(),
            workspace_id=ws.id,
            recipient_user_id=user.id,
            type=notif_type,
            severity=CATALOG[notif_type].severity,
            params={},
            is_simulated=is_simulated,
            created_at=NOW,
            updated_at=NOW,
        )
    )
    delivery = store.put(
        NotificationDelivery(
            id=uuid.uuid4(),
            workspace_id=ws.id,
            notification_id=notif.id,
            recipient_user_id=user.id,
            channel="telegram",
            channel_link_id=link.id,
            status="pending",
            attempt_count=0,
            delivery_metadata={},
        )
    )
    return store, ws, user, link, notif, delivery


def test_telegram_channel_commits_sending_marker_before_http_and_has_no_open_tx() -> None:
    store, ws, user, link, _notif, delivery = _seed_basic_world()
    seen_tx_states: list[bool] = []
    seen_send_states: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_tx_states.append(store.in_transaction())
        seen_send_states.append((delivery.delivery_metadata or {}).get("send_state"))
        return httpx.Response(200, json={"ok": True, "result": {"message_id": 4242}})

    client = TelegramClient(token=BOT_TOKEN, transport=httpx.MockTransport(handler))
    channel = TelegramChannel(client=client)
    recipient = ChannelRecipient(
        user_id=user.id,
        workspace_id=ws.id,
        channel="telegram",
        channel_user_id=link.channel_user_id,
        channel_chat_id=link.channel_chat_id,
        ui_locale="tr",
        timezone=ws.timezone,
    )

    result = channel.deliver_notification(store, FrozenClock(NOW), delivery, recipient)
    assert result.success is True
    assert result.status == "delivered"
    assert result.external_message_id == "4242"
    assert result.metadata["send_state"] == "sent"
    assert seen_tx_states == [False]
    assert seen_send_states == ["sending"]


def test_telegram_channel_timeout_or_missing_message_id_is_ambiguous_terminal_never_retried() -> (
    None
):
    for mode in ("timeout", "no_message_id"):
        store, ws, user, link, _notif, delivery = _seed_basic_world()
        calls: list[httpx.Request] = []

        def make_handler(m: str, c: list[httpx.Request]):
            def handler(request: httpx.Request) -> httpx.Response:
                c.append(request)
                if m == "timeout":
                    raise httpx.ReadTimeout("read timed out after sendMessage", request=request)
                return httpx.Response(200, json={"ok": True, "result": {}})

            return handler

        client = TelegramClient(
            token=BOT_TOKEN, transport=httpx.MockTransport(make_handler(mode, calls))
        )
        channel = TelegramChannel(client=client)
        recipient = ChannelRecipient(
            user_id=user.id,
            workspace_id=ws.id,
            channel="telegram",
            channel_user_id=link.channel_user_id,
            channel_chat_id=link.channel_chat_id,
            ui_locale="tr",
            timezone=ws.timezone,
        )

        res = channel.deliver_notification(store, FrozenClock(NOW), delivery, recipient)
        assert res.success is False
        assert res.error_message == "telegram_send_ambiguous"
        assert res.metadata.get("terminal") is True
        assert res.metadata.get("ambiguous") is True
        assert res.metadata.get("send_state") == "ambiguous"
        assert not res.metadata.get("retryable")
        assert len(calls) == 1


def test_telegram_channel_stale_sending_marker_blocks_duplicate_send() -> None:
    store, ws, user, link, _notif, delivery = _seed_basic_world()
    delivery.delivery_metadata = {"send_state": "sending"}
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json={"ok": True, "result": {"message_id": 999}})

    client = TelegramClient(token=BOT_TOKEN, transport=httpx.MockTransport(handler))
    channel = TelegramChannel(client=client)
    recipient = ChannelRecipient(
        user_id=user.id,
        workspace_id=ws.id,
        channel="telegram",
        channel_user_id=link.channel_user_id,
        channel_chat_id=link.channel_chat_id,
        ui_locale="tr",
        timezone=ws.timezone,
    )

    res = channel.deliver_notification(store, FrozenClock(NOW), delivery, recipient)
    assert res.success is False
    assert res.error_message == "telegram_send_state_unknown"
    assert res.metadata.get("terminal") is True
    assert res.metadata.get("ambiguous") is True
    assert calls == []


def test_telegram_channel_429_and_503_are_retryable_while_403_is_terminal() -> None:
    for status_code, is_retryable in ((429, True), (503, True), (403, False)):
        store, ws, user, link, _notif, delivery = _seed_basic_world()

        def handler(request: httpx.Request, code: int = status_code) -> httpx.Response:
            return httpx.Response(
                code,
                json={"ok": False, "error_code": code, "description": "Telegram error"},
            )

        client = TelegramClient(token=BOT_TOKEN, transport=httpx.MockTransport(handler))
        channel = TelegramChannel(client=client)
        recipient = ChannelRecipient(
            user_id=user.id,
            workspace_id=ws.id,
            channel="telegram",
            channel_user_id=link.channel_user_id,
            channel_chat_id=link.channel_chat_id,
            ui_locale="tr",
            timezone=ws.timezone,
        )

        res = channel.deliver_notification(store, FrozenClock(NOW), delivery, recipient)
        assert res.success is False
        assert res.metadata.get("send_state") == "not_sent"
        if is_retryable:
            assert res.metadata.get("retryable") is True
            assert res.error_message == f"telegram_retryable:{status_code}"
        else:
            assert res.metadata.get("terminal") is True
            assert res.error_message == f"telegram_rejected:{status_code}"


def test_telegram_channel_refuses_unlinked_or_foreign_link_or_decided_approval() -> None:
    # 1. Unlinked link on delivery
    store, ws, user, link, _notif, delivery = _seed_basic_world(link_status="unlinked")
    calls: list[httpx.Request] = []
    client = TelegramClient(
        token=BOT_TOKEN,
        transport=httpx.MockTransport(
            lambda r: (
                calls.append(r)
                or httpx.Response(200, json={"ok": True, "result": {"message_id": 1}})
            )
        ),
    )
    channel = TelegramChannel(client=client)
    recipient = ChannelRecipient(
        user_id=user.id,
        workspace_id=ws.id,
        channel="telegram",
        channel_user_id=link.channel_user_id,
        channel_chat_id=link.channel_chat_id,
        ui_locale="tr",
        timezone=ws.timezone,
    )
    res = channel.deliver_notification(store, FrozenClock(NOW), delivery, recipient)
    assert res.success is False and res.error_message == "recipient_not_linked"
    assert calls == []

    # 2. Already decided approval is not announced
    store2, ws2, user2, link2, notif2, delivery2 = _seed_basic_world(
        notif_type="approval.requested"
    )
    approval = store2.put(
        Approval(
            id=uuid.uuid4(),
            workspace_id=ws2.id,
            kind="authorization",
            action="reply.send",
            subject_type="reply_draft",
            subject_id=uuid.uuid4(),
            subject_version=1,
            payload_hash="a" * 64,
            summary={},
            required_permission="reply.approve",
            status="approved",
            requested_by_actor_type="agent",
            expires_at=NOW + timedelta(hours=2),
            created_at=NOW,
        )
    )
    notif2.subject_type = "approval"
    notif2.subject_id = approval.id
    recipient2 = ChannelRecipient(
        user_id=user2.id,
        workspace_id=ws2.id,
        channel="telegram",
        channel_user_id=link2.channel_user_id,
        channel_chat_id=link2.channel_chat_id,
        ui_locale="tr",
        timezone=ws2.timezone,
    )
    res2 = channel.deliver_notification(store2, FrozenClock(NOW), delivery2, recipient2)
    assert res2.success is False and res2.error_message == "approval_not_pending"
    assert calls == []


# =============================================================================
# 4. dispatch_telegram & Worker Job Recheck Unit Tests
# =============================================================================


def test_dispatch_telegram_skips_simulated_unsupported_and_unlinked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store, ws, user, link, notif, _delivery = _seed_basic_world(notif_type="approval.requested")
    ctx = WorkspaceContext(
        workspace_id=ws.id,
        actor=ActorRef.user(user.id),
        role="owner",
        timezone=ws.timezone,
        locale="tr",
        is_demo=False,
    )
    clock = FrozenClock(NOW)

    # 1. Simulated notification -> None
    notif.is_simulated = True
    assert dispatch_telegram(store, clock, ctx, notif) is None

    # 2. Unsupported routine notification -> None
    notif.is_simulated = False
    notif.type = "content.published"
    assert dispatch_telegram(store, clock, ctx, notif) is None

    # 3. Unlinked channel link -> None
    notif.type = "approval.requested"
    link.status = "unlinked"
    store.scalars_map[ChannelLink] = []
    assert dispatch_telegram(store, clock, ctx, notif) is None

    # 4. Active link -> dispatches through dispatch_channel_notification
    link.status = "active"
    store.scalars_map[ChannelLink] = [link]
    dispatched: list[dict[str, Any]] = []

    def fake_dispatch(session: Any, clk: Any, **kwargs: Any) -> NotificationDelivery:
        dispatched.append(kwargs)
        return NotificationDelivery(
            id=uuid.uuid4(),
            workspace_id=kwargs["workspace_id"],
            notification_id=kwargs["notification"].id,
            recipient_user_id=kwargs["recipient"].user_id,
            channel=kwargs["channel"],
            channel_link_id=kwargs["channel_link_id"],
            status="pending",
            attempt_count=0,
        )

    monkeypatch.setattr(
        "app.notifications.telegram_dispatch.dispatch_channel_notification",
        fake_dispatch,
    )
    res = dispatch_telegram(store, clock, ctx, notif)
    assert res is not None
    assert len(dispatched) == 1
    assert dispatched[0]["channel"] == "telegram"
    assert dispatched[0]["channel_link_id"] == link.id


def test_dispatch_channel_notification_idempotent_for_same_notification_recipient_channel(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store, ws, user, link, notif, existing_delivery = _seed_basic_world(
        notif_type="approval.requested"
    )
    enqueued: list[Any] = []
    monkeypatch.setattr(
        "app.notifications.delivery_ledger.enqueue",
        lambda *a, **kw: enqueued.append((a, kw)) or uuid.uuid4(),
    )
    recipient = ChannelRecipient(
        user_id=user.id,
        workspace_id=ws.id,
        channel="telegram",
        channel_user_id=link.channel_user_id,
        channel_chat_id=link.channel_chat_id,
        timezone=ws.timezone,
    )
    # First call sees existing NotificationDelivery in store.scalars_map
    returned = dispatch_channel_notification(
        store,  # type: ignore[arg-type]
        FrozenClock(NOW),
        workspace_id=ws.id,
        notification=notif,
        recipient=recipient,
        channel="telegram",
        channel_link_id=link.id,
    )
    assert returned.id == existing_delivery.id
    assert enqueued == []


def test_deliver_channel_notification_worker_blocks_simulated_and_handles_ambiguous_vs_retryable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.notifications.jobs.set_tenant_context", lambda *_a, **_kw: None)

    # Case A: Simulated notification in worker -> fails with simulated_notification_not_sent
    store_sim, ws_sim, _u, _l, _n, del_sim = _seed_basic_world(
        notif_type="approval.requested", is_simulated=True
    )

    @contextlib.contextmanager
    def sim_factory() -> Any:
        yield store_sim

    job_ctx_sim = JobContext(
        job_id=uuid.uuid4(),
        job_type="deliver_channel_notification",
        workspace_id=ws_sim.id,
        correlation_id=None,
        payload=DeliverChannelNotificationPayload(delivery_id=del_sim.id),
        attempt=1,
        max_attempts=3,
        session_factory=sim_factory,  # type: ignore[arg-type]
        clock=FrozenClock(NOW),
        _heartbeat=lambda: None,
    )
    deliver_channel_notification(job_ctx_sim)
    assert del_sim.status == "failed"
    assert del_sim.last_error == "simulated_notification_not_sent"

    # Case B: Ambiguous timeout during Telegram send -> terminal failed, no RetryableError raised
    store_amb, ws_amb, _u2, _l2, _n2, del_amb = _seed_basic_world(notif_type="reply.failed")

    def timeout_handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timeout after send", request=request)

    reset_channel_registry()
    register_channel(
        "telegram",
        TelegramChannel(
            client=TelegramClient(token=BOT_TOKEN, transport=httpx.MockTransport(timeout_handler))
        ),
    )

    @contextlib.contextmanager
    def amb_factory() -> Any:
        yield store_amb

    job_ctx_amb = JobContext(
        job_id=uuid.uuid4(),
        job_type="deliver_channel_notification",
        workspace_id=ws_amb.id,
        correlation_id=None,
        payload=DeliverChannelNotificationPayload(delivery_id=del_amb.id),
        attempt=1,
        max_attempts=3,
        session_factory=amb_factory,  # type: ignore[arg-type]
        clock=FrozenClock(NOW),
        _heartbeat=lambda: None,
    )
    deliver_channel_notification(job_ctx_amb)
    assert del_amb.status == "failed"
    assert del_amb.last_error == "telegram_send_ambiguous"
    assert del_amb.delivery_metadata["send_state"] == "ambiguous"
    assert del_amb.delivery_metadata["ambiguous"] is True

    # Case C: HTTP 429 rate-limit -> leaves delivery pending and raises RetryableError
    store_ret, ws_ret, _u3, _l3, _n3, del_ret = _seed_basic_world(notif_type="reply.failed")

    def rate_limit_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            429, json={"ok": False, "error_code": 429, "description": "Too Many Requests"}
        )

    register_channel(
        "telegram",
        TelegramChannel(
            client=TelegramClient(
                token=BOT_TOKEN, transport=httpx.MockTransport(rate_limit_handler)
            )
        ),
    )

    @contextlib.contextmanager
    def ret_factory() -> Any:
        yield store_ret

    job_ctx_ret = JobContext(
        job_id=uuid.uuid4(),
        job_type="deliver_channel_notification",
        workspace_id=ws_ret.id,
        correlation_id=None,
        payload=DeliverChannelNotificationPayload(delivery_id=del_ret.id),
        attempt=1,
        max_attempts=3,
        session_factory=ret_factory,  # type: ignore[arg-type]
        clock=FrozenClock(NOW),
        _heartbeat=lambda: None,
    )
    with pytest.raises(RetryableError):
        deliver_channel_notification(job_ctx_ret)
    assert del_ret.status == "pending"
    assert del_ret.last_error == "telegram_retryable:429"
    assert del_ret.delivery_metadata["send_state"] == "not_sent"
    reset_channel_registry()


# =============================================================================
# 5. Informed Descriptions for Account Agent Approvals (subject_type == 'agent_action')
# =============================================================================


def test_agent_action_dm_send_renders_informed_reply_and_fact_sources(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store, ws, user, link, notif, delivery = _seed_basic_world(notif_type="approval.requested")
    account = store.put(
        SocialAccount(
            id=uuid.uuid4(),
            workspace_id=ws.id,
            platform="instagram",
            provider_kind="mock",
            external_account_id="ig_salon_1",
            username="studio.golkent",
            status="connected",
            capabilities={"messaging": True},
            granted_scopes=[],
        )
    )
    conv = store.put(
        Conversation(
            id=uuid.uuid4(),
            workspace_id=ws.id,
            social_account_id=account.id,
            customer_external_id="cust_1",
            customer_handle="zeynep_k",
            handling_mode="automatic",
            attention="none",
            last_inbound_at=NOW,
            is_simulated=False,
        )
    )
    inbound = store.put(
        Message(
            id=uuid.uuid4(),
            workspace_id=ws.id,
            social_account_id=account.id,
            conversation_id=conv.id,
            direction="inbound",
            sender_kind="customer",
            external_message_id="mid_1",
            text="Merhaba, aylık üyelik fiyatınız nedir?",
            provider_timestamp=NOW,
            is_simulated=False,
        )
    )
    action_id = uuid.uuid4()
    draft = store.put(
        ReplyDraft(
            id=uuid.uuid4(),
            workspace_id=ws.id,
            conversation_id=conv.id,
            covers_through_message_id=inbound.id,
            source="ai",
            origin="agent",
            agent_action_id=action_id,
            status="pending_approval",
            decision="approval_required",
            text="Merhaba Zeynep Hanım! Aylık üyelik ücretimiz 6.000 ₺ / ay'dır.",
            validation={
                "passed": True,
                "issues": [],
                "rendered": [
                    {
                        "key": "pricing.monthly",
                        "fact_id": str(uuid.uuid4()),
                        "version": 1,
                        "display": "6.000 ₺ / ay",
                    }
                ],
            },
            version=1,
            created_by_actor_type="agent",
            is_simulated=False,
        )
    )
    action = store.put(
        AgentAction(
            id=action_id,
            workspace_id=ws.id,
            social_account_id=account.id,
            thread_id=uuid.uuid4(),
            session_id=uuid.uuid4(),
            intent_key="dm.send:1",
            action_type="dm.send",
            payload_ref=draft.id,
            payload_hash="b" * 64,
            version=1,
            target_ref=str(conv.id),
            initiating_cursor=1,
            status="waiting_approval",
        )
    )
    approval = store.put(
        Approval(
            id=uuid.uuid4(),
            workspace_id=ws.id,
            kind="authorization",
            action="reply.send",
            subject_type="agent_action",
            subject_id=action.id,
            subject_version=1,
            payload_hash=action.payload_hash,
            summary={
                "action_type": "dm.send",
                "target_ref": str(conv.id),
                "payload_hash": action.payload_hash,
            },
            required_permission="reply.approve",
            status="pending",
            requested_by_actor_type="agent",
            expires_at=NOW + timedelta(hours=24),
            created_at=NOW,
        )
    )
    notif.subject_type = "approval"
    notif.subject_id = approval.id

    monkeypatch.setattr(
        ActionTokenService,
        "create_action_token",
        staticmethod(lambda *_a, **kw: f"tok_{kw['decision']}"),
    )
    monkeypatch.setattr(
        "app.integrations.channels.telegram.adapter._fact_source_lines",
        lambda *_a, **_kw: [
            "<b>Değerlerin kaynağı:</b>",
            "• <b>6.000 ₺ / ay</b> — kaynak: Aylık üyelik, doğrulandı 2026-11-19",
        ],
    )

    sent_payloads: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent_payloads.append(json.loads(request.content))
        return httpx.Response(200, json={"ok": True, "result": {"message_id": 701}})

    channel = TelegramChannel(
        client=TelegramClient(token=BOT_TOKEN, transport=httpx.MockTransport(handler))
    )
    recipient = ChannelRecipient(
        user_id=user.id,
        workspace_id=ws.id,
        channel="telegram",
        channel_user_id=link.channel_user_id,
        channel_chat_id=link.channel_chat_id,
        ui_locale="tr",
        timezone=ws.timezone,
    )

    res = channel.deliver_notification(store, FrozenClock(NOW), delivery, recipient)
    assert res.success is True
    assert len(sent_payloads) == 1
    text = sent_payloads[0]["text"]
    assert "Onay İsteği: Müşteri Yanıtı" in text
    assert "@studio.golkent" in text
    assert "@zeynep_k" in text
    assert "Merhaba, aylık üyelik fiyatınız nedir?" in text
    assert "6.000 ₺ / ay" in text
    assert "Değerlerin kaynağı:" in text
    assert "payload_hash" not in text
    buttons = sent_payloads[0]["reply_markup"]["inline_keyboard"][0]
    assert buttons[0]["callback_data"] == "act:tok_approved"
    assert buttons[1]["callback_data"] == "act:tok_rejected"


def test_agent_action_content_and_calendar_and_comment_informed_descriptions() -> None:
    store, ws, user, link, _notif, _delivery = _seed_basic_world(notif_type="approval.requested")
    account = store.put(
        SocialAccount(
            id=uuid.uuid4(),
            workspace_id=ws.id,
            platform="instagram",
            provider_kind="mock",
            external_account_id="ig_salon_2",
            username="studio.golkent",
            status="connected",
            capabilities={},
            granted_scopes=[],
        )
    )
    recipient = ChannelRecipient(
        user_id=user.id,
        workspace_id=ws.id,
        channel="telegram",
        channel_user_id=link.channel_user_id,
        channel_chat_id=link.channel_chat_id,
        ui_locale="tr",
        timezone="Europe/Istanbul",
    )

    # A. Content schedule agent_action
    item = store.put(
        ContentItem(
            id=uuid.uuid4(),
            workspace_id=ws.id,
            social_account_id=account.id,
            content_type="feed_image",
            status="draft",
            version=1,
            title="Kasım Kampanyası",
            caption="Yeni sezon pilates derslerimiz başladı!",
            scheduled_at=datetime(2026, 11, 20, 16, 0, tzinfo=UTC),
            is_simulated=False,
        )
    )
    content_action = store.put(
        AgentAction(
            id=uuid.uuid4(),
            workspace_id=ws.id,
            social_account_id=account.id,
            thread_id=uuid.uuid4(),
            session_id=uuid.uuid4(),
            intent_key="content.schedule:v1",
            action_type="content.schedule",
            payload_ref=item.id,
            content_intent={
                "payload": {
                    "content_type": "feed_image",
                    "caption": item.caption,
                    "scheduled_at": "2026-11-20T16:00:00+00:00",
                }
            },
            payload_hash="c" * 64,
            version=1,
            target_ref=str(item.id),
            initiating_cursor=1,
            status="waiting_approval",
        )
    )
    content_approval = Approval(
        id=uuid.uuid4(),
        workspace_id=ws.id,
        kind="authorization",
        action="content.schedule",
        subject_type="agent_action",
        subject_id=content_action.id,
        subject_version=1,
        payload_hash=content_action.payload_hash,
        summary={"action_type": "content.schedule", "target_ref": str(item.id)},
        required_permission="content.approve",
        status="pending",
        requested_by_actor_type="agent",
        expires_at=NOW + timedelta(hours=24),
        created_at=NOW,
    )
    content_lines: list[str] = []
    _append_agent_action_lines(
        store,  # type: ignore[arg-type]
        content_lines,
        approval=content_approval,
        recipient=recipient,
        is_tr=True,
        sim_badge="",
    )
    content_text = "\n".join(content_lines)
    assert "Onay İsteği: Paylaşım Planı" in content_text
    assert "@studio.golkent" in content_text
    assert "Feed Image" in content_text
    assert "Kasım Kampanyası" in content_text
    assert "Yeni sezon pilates derslerimiz başladı!" in content_text
    assert "2026-11-20 19:00" in content_text  # 16:00 UTC in Europe/Istanbul (+3)

    # B. Calendar book & reschedule agent_action
    existing_appt = store.put(
        CalendarAppointment(
            id=uuid.uuid4(),
            workspace_id=ws.id,
            calendar_connection_id=uuid.uuid4(),
            title="Lazer Epilasyon Seansı",
            customer_name="Elif Demir",
            customer_contact="@elif_d",
            start_at=datetime(2026, 11, 21, 11, 0, tzinfo=UTC),
            end_at=datetime(2026, 11, 21, 11, 45, tzinfo=UTC),
            timezone="Europe/Istanbul",
            status="scheduled",
            created_by_source="customer",
            is_simulated=False,
            version=1,
        )
    )
    cal_action = store.put(
        AgentAction(
            id=uuid.uuid4(),
            workspace_id=ws.id,
            social_account_id=account.id,
            thread_id=uuid.uuid4(),
            session_id=uuid.uuid4(),
            intent_key="calendar.reschedule:1",
            action_type="calendar.reschedule",
            payload_ref=existing_appt.id,
            content_intent={
                "appointment_id": str(existing_appt.id),
                "title": "Lazer Epilasyon Seansı",
                "customer_name": "Elif Demir",
                "customer_contact": "@elif_d",
                "local_date": "2026-11-22",
                "local_time": "15:30",
                "duration_minutes": 45,
                "timezone": "Europe/Istanbul",
                "reason": "Müşteri pazar gününe almak istedi",
            },
            payload_hash="d" * 64,
            version=1,
            target_ref=f"appointment:{existing_appt.id}:v1",
            initiating_cursor=1,
            status="waiting_approval",
        )
    )
    cal_approval = Approval(
        id=uuid.uuid4(),
        workspace_id=ws.id,
        kind="authorization",
        action="calendar.reschedule",
        subject_type="agent_action",
        subject_id=cal_action.id,
        subject_version=1,
        payload_hash=cal_action.payload_hash,
        summary={"action_type": "calendar.reschedule"},
        required_permission="reply.approve",
        status="pending",
        requested_by_actor_type="agent",
        expires_at=NOW + timedelta(hours=24),
        created_at=NOW,
    )
    cal_lines: list[str] = []
    _append_agent_action_lines(
        store,  # type: ignore[arg-type]
        cal_lines,
        approval=cal_approval,
        recipient=recipient,
        is_tr=True,
        sim_badge="",
    )
    cal_text = "\n".join(cal_lines)
    assert "Onay İsteği: Randevu Değişikliği" in cal_text
    assert "Lazer Epilasyon Seansı" in cal_text
    assert "Elif Demir (@elif_d)" in cal_text
    assert "2026-11-21 14:00 → 2026-11-22 15:30 (Europe/Istanbul)" in cal_text
    assert "45 dk" in cal_text
    assert "Müşteri pazar gününe almak istedi" in cal_text

    # C. Comment private reply & public comment reply agent_action
    media = store.put(
        PublicMedia(
            id=uuid.uuid4(),
            workspace_id=ws.id,
            social_account_id=account.id,
            external_id="media_1",
            caption="Kış bakım paketi duyurusu",
            state="visible",
            ownership_state="verified_provider",
            version=1,
            provider_version=1,
            updated_at=NOW,
            is_simulated=False,
        )
    )
    comment = store.put(
        PublicComment(
            id=uuid.uuid4(),
            workspace_id=ws.id,
            social_account_id=account.id,
            media_id=media.id,
            thread_id=uuid.uuid4(),
            external_id="comm_1",
            author_external_id="auth_1",
            text="Fiyat bilgisi alabilir miyim?",
            state="visible",
            version=1,
            provider_version=1,
            updated_at=NOW,
            is_owner=False,
            is_simulated=False,
        )
    )
    priv_action_id = uuid.uuid4()
    opp = store.put(
        PrivateReplyOpportunity(
            id=uuid.uuid4(),
            workspace_id=ws.id,
            social_account_id=account.id,
            comment_id=comment.id,
            agent_action_id=priv_action_id,
            comment_version=1,
            media_version=1,
            text="Merhaba! Kış bakım paketimiz 3.500 TL'dir, DM'den detayları paylaştık.",
            proposal={},
            status="reserved",
            eligibility_expires_at=NOW + timedelta(days=5),
            created_at=NOW,
        )
    )
    priv_action = store.put(
        AgentAction(
            id=priv_action_id,
            workspace_id=ws.id,
            social_account_id=account.id,
            thread_id=uuid.uuid4(),
            session_id=uuid.uuid4(),
            intent_key="private_invitation",
            action_type="comment.private_reply",
            payload_ref=opp.id,
            payload_hash="e" * 64,
            version=1,
            target_ref=str(comment.id),
            initiating_cursor=1,
            status="waiting_approval",
        )
    )
    priv_approval = Approval(
        id=uuid.uuid4(),
        workspace_id=ws.id,
        kind="authorization",
        action="comments.approve",
        subject_type="agent_action",
        subject_id=priv_action.id,
        subject_version=1,
        payload_hash=priv_action.payload_hash,
        summary={"action_type": "comment.private_reply"},
        required_permission="comments.approve",
        status="pending",
        requested_by_actor_type="agent",
        expires_at=NOW + timedelta(hours=24),
        created_at=NOW,
    )
    priv_lines: list[str] = []
    _append_agent_action_lines(
        store,  # type: ignore[arg-type]
        priv_lines,
        approval=priv_approval,
        recipient=recipient,
        is_tr=True,
        sim_badge="",
    )
    priv_text = "\n".join(priv_lines)
    assert "Onay İsteği: Yorumdan Özel Yanıt (DM)" in priv_text
    assert "Kış bakım paketi duyurusu" in priv_text
    assert "Fiyat bilgisi alabilir miyim?" in priv_text
    assert "Merhaba! Kış bakım paketimiz 3.500 TL" in priv_text


def test_format_notification_text_uses_localized_copy_when_params_lack_title() -> None:
    notif = Notification(
        id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        recipient_user_id=uuid.uuid4(),
        type="account.needs_reauth",
        severity="critical",
        params={},
        is_simulated=False,
    )
    tr_text = _format_notification_text(notif, "tr")
    en_text = _format_notification_text(notif, "en")
    assert "Instagram bağlantısı yenilenmeli" in tr_text
    assert "Instagram needs to be reconnected" in en_text


def test_telegram_dispatch_savepoint_error_never_breaks_in_app_notification(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store, ws, user, _link, notif, _delivery = _seed_basic_world(notif_type="approval.requested")
    ctx = WorkspaceContext(
        workspace_id=ws.id,
        actor=ActorRef.user(user.id),
        role="owner",
        timezone=ws.timezone,
        locale="tr",
        is_demo=False,
    )

    def boom(*_a: Any, **_kw: Any) -> Any:
        raise RuntimeError("simulated DB savepoint failure")

    monkeypatch.setattr(
        "app.notifications.telegram_dispatch.dispatch_channel_notification",
        boom,
    )
    # Must swallow and return None so notify() still returns the in-app Notification
    res = dispatch_telegram(store, FrozenClock(NOW), ctx, notif)
    assert res is None


def test_complete_queued_delivered_and_button_decided_pipeline_and_free_text_never_approves(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Proves the full notification -> queued -> delivered -> button-decided path for reply,
    content, and calendar approvals:
    - Each approval renders an informed description and single-use act:<token> buttons.
    - First tap decides the approval once.
    - Second tap (replay) or sibling reject tap returns approval_already_decided with 0 second
      decisions.
    - Free text containing 'approve', 'onayla', or even the raw 'act:<token>' string never calls
      consume_action_token or ApprovalService.decide.
    """
    from app.approvals.models import ActionToken
    from app.integrations.channels.telegram.handlers import (
        handle_approval_callback,
        handle_linked_message,
    )
    from app.integrations.channels.telegram.webhook_format import (
        CallbackQuery,
        TelegramChat,
        TelegramMessage,
        TelegramUser,
    )

    store, ws, user, link, notif, delivery = _seed_basic_world(notif_type="approval.requested")
    account = store.put(
        SocialAccount(
            id=uuid.uuid4(),
            workspace_id=ws.id,
            platform="instagram",
            provider_kind="mock",
            external_account_id="ig_pipeline_1",
            username="studio.golkent",
            status="connected",
            capabilities={"messaging": True},
            granted_scopes=[],
        )
    )
    cal_action = store.put(
        AgentAction(
            id=uuid.uuid4(),
            workspace_id=ws.id,
            social_account_id=account.id,
            thread_id=uuid.uuid4(),
            session_id=uuid.uuid4(),
            intent_key="calendar.book:2026-11-23:11:00",
            action_type="calendar.book",
            payload_ref=uuid.uuid4(),
            content_intent={
                "title": "Cilt Bakımı",
                "customer_name": "Selin Kaya",
                "local_date": "2026-11-23",
                "local_time": "11:00",
                "duration_minutes": 60,
                "timezone": "Europe/Istanbul",
            },
            payload_hash="f" * 64,
            version=1,
            target_ref="calendar:conn:2026-11-23T11:00",
            initiating_cursor=1,
            status="waiting_approval",
        )
    )
    approval = store.put(
        Approval(
            id=uuid.uuid4(),
            workspace_id=ws.id,
            kind="authorization",
            action="calendar.book",
            subject_type="agent_action",
            subject_id=cal_action.id,
            subject_version=1,
            payload_hash=cal_action.payload_hash,
            summary={"action_type": "calendar.book"},
            required_permission="reply.approve",
            status="pending",
            requested_by_actor_type="agent",
            expires_at=NOW + timedelta(hours=24),
            created_at=NOW,
        )
    )
    notif.subject_type = "approval"
    notif.subject_id = approval.id

    minted_tokens: dict[str, ActionToken] = {}

    def fake_create_token(
        session: Any,
        clock: Any,
        ctx: Any,
        appr: Approval,
        decision: str,
        user_id: uuid.UUID,
    ) -> str:
        raw = f"tok_{decision}_{uuid.uuid4().hex[:8]}"
        minted_tokens[raw] = ActionToken(
            id=uuid.uuid4(),
            workspace_id=appr.workspace_id,
            approval_id=appr.id,
            user_id=user_id,
            decision=decision,
            payload_hash=appr.payload_hash,
            token_hash=raw,
            expires_at=appr.expires_at,
            used_at=None,
            created_at=clock.now(),
        )
        return raw

    def fake_consume_token(
        db: Any,
        clock: Any,
        token_str: str,
        channel_user_id: str,
        channel: str = "telegram",
    ) -> tuple[Approval, ActionToken]:
        from app.core.errors import AppError

        tok = minted_tokens.get(token_str)
        if tok is None:
            raise AppError("NOT_FOUND")
        if channel_user_id != link.channel_user_id:
            raise AppError("FORBIDDEN")
        if tok.used_at is not None or approval.status != "pending":
            raise AppError("APPROVAL_ALREADY_DECIDED")
        if tok.expires_at <= clock.now():
            raise AppError("APPROVAL_EXPIRED")
        tok.used_at = clock.now()
        return approval, tok

    decisions_made: list[tuple[uuid.UUID, str, str]] = []

    def fake_decide(
        session: Any,
        clock: Any,
        ctx: Any,
        approval_id: uuid.UUID,
        *,
        decision: str,
        payload_hash: str,
        note: str | None = None,
        channel: str = "web",
    ) -> Approval:
        from app.core.errors import AppError

        if approval.status != "pending":
            raise AppError("APPROVAL_ALREADY_DECIDED")
        if payload_hash != approval.payload_hash:
            raise AppError("APPROVAL_STALE")
        approval.status = "approved" if decision == "approve" else "rejected"
        cal_action.status = "authorized" if decision == "approve" else "cancelled"
        decisions_made.append((approval_id, decision, channel))
        return approval

    monkeypatch.setattr(ActionTokenService, "create_action_token", staticmethod(fake_create_token))
    monkeypatch.setattr(
        ActionTokenService, "consume_action_token", staticmethod(fake_consume_token)
    )
    monkeypatch.setattr("app.approvals.service.ApprovalService.decide", staticmethod(fake_decide))
    monkeypatch.setattr("app.notifications.jobs.set_tenant_context", lambda *_a, **_kw: None)

    api_calls: list[tuple[str, dict[str, Any]]] = []

    def tg_handler(request: httpx.Request) -> httpx.Response:
        method = str(request.url).split("/")[-1]
        body = json.loads(request.content) if request.content else {}
        api_calls.append((method, body))
        return httpx.Response(200, json={"ok": True, "result": {"message_id": 888}})

    tg_client = TelegramClient(token=BOT_TOKEN, transport=httpx.MockTransport(tg_handler))
    reset_channel_registry()
    register_channel("telegram", TelegramChannel(client=tg_client))

    @contextlib.contextmanager
    def factory() -> Any:
        yield store

    # 1. Worker delivers queued notification
    job_ctx = JobContext(
        job_id=uuid.uuid4(),
        job_type="deliver_channel_notification",
        workspace_id=ws.id,
        correlation_id=None,
        payload=DeliverChannelNotificationPayload(delivery_id=delivery.id),
        attempt=1,
        max_attempts=3,
        session_factory=factory,  # type: ignore[arg-type]
        clock=FrozenClock(NOW),
        _heartbeat=lambda: None,
    )
    deliver_channel_notification(job_ctx)
    assert delivery.status == "delivered"
    assert len(api_calls) == 1
    sent_method, sent_body = api_calls[0]
    assert sent_method == "sendMessage"
    assert "Onay İsteği: Randevu Oluşturma" in sent_body["text"]
    assert "Cilt Bakımı" in sent_body["text"]
    assert "Selin Kaya" in sent_body["text"]
    assert "2026-11-23 11:00" in sent_body["text"]

    kb = sent_body["reply_markup"]["inline_keyboard"][0]
    approve_cb = kb[0]["callback_data"]
    reject_cb = kb[1]["callback_data"]
    assert approve_cb.startswith("act:") and reject_cb.startswith("act:")
    approve_token = approve_cb[4:]
    reject_token = reject_cb[4:]

    # 2. Free text NEVER approves (even if owner types 'onayla', 'approve', or raw 'act:<token>')
    monkeypatch.setattr(
        "app.integrations.channels.telegram.handlers._handle_general_command",
        lambda **_kw: "owner_command",
    )
    monkeypatch.setattr(
        "app.integrations.channels.telegram.handlers.get_pending_media",
        lambda *_a, **_kw: None,
    )
    for free_text in ("onayla", "approve", approve_cb, approve_token):
        msg = TelegramMessage(
            message_id=10,
            date=1700000000,
            chat=TelegramChat(id=777001, type="private"),
            from_=TelegramUser(id=777001, is_bot=False, first_name="Ayşe"),
            text=free_text,
        )
        handle_linked_message(
            store,  # type: ignore[arg-type]
            FrozenClock(NOW),
            user,
            ws,
            link,
            msg,
            tg_client,
        )
    assert approval.status == "pending"
    assert decisions_made == []

    # 3. Single-use button tap approves once
    cb_query = CallbackQuery(
        id="cb_1",
        from_=TelegramUser(id=777001, is_bot=False, first_name="Ayşe"),
        message=TelegramMessage(
            message_id=888,
            date=1700000000,
            chat=TelegramChat(id=777001, type="private"),
            text=sent_body["text"],
        ),
        data=approve_cb,
    )
    outcome_1 = handle_approval_callback(
        store,  # type: ignore[arg-type]
        FrozenClock(NOW),
        cb_query,
        approve_token,
        tg_client,
    )
    assert outcome_1 == "approval_decided"
    assert approval.status == "approved"
    assert cal_action.status == "authorized"
    assert decisions_made == [(approval.id, "approve", "telegram")]

    # 4. Replay of same button or sibling reject button is rejected with 0 duplicate decisions
    outcome_2 = handle_approval_callback(
        store,  # type: ignore[arg-type]
        FrozenClock(NOW),
        cb_query,
        approve_token,
        tg_client,
    )
    outcome_3 = handle_approval_callback(
        store,  # type: ignore[arg-type]
        FrozenClock(NOW),
        cb_query,
        reject_token,
        tg_client,
    )
    assert outcome_2 == "approval_already_decided"
    assert outcome_3 == "approval_already_decided"
    assert len(decisions_made) == 1
    reset_channel_registry()
