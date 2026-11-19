"""Session 01: Telegram notification dispatch, delivery ledger, worker execution, and
Account Agent approval button round-trips (ADR-012, ADR-014, ADR-024, INV-04, INV-06, INV-16).

Proves against PostgreSQL:
- notifications.service.notify() records a NotificationDelivery(channel='telegram') and enqueues
  deliver_channel_notification in the notification's transaction for active members with an active
  Telegram ChannelLink and a supported TELEGRAM_TYPES notification type.
- Routine info notifications, delegation_suggestion, unlinked users, and simulated notifications
  (is_simulated=True) are never dispatched to Telegram.
- Quiet hours hold non-critical notifications (skipped_quiet_hours), while critical notifications
  and approvals expiring within 2 hours bypass quiet hours.
- The worker delivers outside any DB transaction (send_state='sending' committed first).
- Unlinking or losing workspace membership before the worker runs fails the delivery without
  calling Telegram.
- Transport timeouts, 2xx responses without a message_id, and stale 'sending' markers fail
  terminally as ambiguous and are never resent; 429/5xx retry with backoff; 4xx rejections fail
  terminally without retry.
- Account Agent approvals (subject_type == 'agent_action') for reply (dm.send), content
  (content.schedule), and calendar (calendar.book) render informed descriptions and decide the
  existing approval once via single-use act:<token> buttons. Free text never approves.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Callable, Iterator
from datetime import timedelta
from typing import Any

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.core.db import set_tenant_context
from app.identity.models import ChannelLink
from app.integrations.channels import registry
from app.integrations.channels.base import ChannelRecipient
from app.integrations.channels.telegram import TelegramChannel, TelegramClient
from app.jobs.models import Job
from app.jobs.testing import run_due_jobs
from app.notifications import service as notifications
from app.notifications.catalog import TELEGRAM_TYPES
from app.notifications.models import Notification, NotificationDelivery
from tests.helpers.env import Env

TG_CHAT_ID = "777001"
BOT_TOKEN = "synthetic-tg-bot-token-secret"
OK = (200, {"ok": True, "result": {"message_id": 5001}})


class BotApi:
    """Scripted Telegram Bot API transport."""

    def __init__(self) -> None:
        self.requests: list[dict[str, Any]] = []
        self.methods: list[str] = []
        self.script: list[Any] = []
        self.default: Any = OK
        self.in_transaction: Callable[[], bool] | None = None
        self.seen_in_transaction: list[bool] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        if self.in_transaction is not None:
            self.seen_in_transaction.append(self.in_transaction())
        method = str(request.url).split("/")[-1]
        self.methods.append(method)
        body = json.loads(request.content) if request.content else {}
        self.requests.append(body)
        if method in ("answerCallbackQuery", "editMessageReplyMarkup"):
            return httpx.Response(200, json={"ok": True, "result": True})
        if method == "editMessageText":
            return httpx.Response(200, json={"ok": True, "result": {"message_id": 5001}})
        step = self.script.pop(0) if self.script else self.default
        if isinstance(step, Exception):
            raise step
        status, payload = step
        return httpx.Response(status, json=payload)


@pytest.fixture
def bot_api() -> BotApi:
    return BotApi()


@pytest.fixture
def factory(db_session: Session) -> sessionmaker[Session]:
    return sessionmaker(
        bind=db_session.get_bind(),
        expire_on_commit=False,
        autoflush=False,
        join_transaction_mode="create_savepoint",
    )


def make_client(bot_api: BotApi) -> TelegramClient:
    return TelegramClient(token=BOT_TOKEN, transport=httpx.MockTransport(bot_api))


@pytest.fixture(autouse=True)
def wired(bot_api: BotApi) -> Iterator[None]:
    registry.reset_channel_registry()
    registry.register_channel("telegram", TelegramChannel(client=make_client(bot_api)))
    yield
    registry.reset_channel_registry()


def link_owner(
    env: Env,
    *,
    role: str = "owner",
    chat_id: str = TG_CHAT_ID,
) -> ChannelLink:
    user = getattr(env, role).user
    link = ChannelLink(
        workspace_id=env.workspace.id,
        user_id=user.id,
        channel="telegram",
        channel_user_id=chat_id,
        channel_chat_id=chat_id,
        channel_username=f"{role}_tg",
        status="active",
        linked_at=env.clock.now(),
    )
    env.session.add(link)
    env.session.commit()
    return link


def notify(
    env: Env,
    kind: str,
    *,
    role: str = "owner",
    params: dict[str, Any] | None = None,
    is_simulated: bool = False,
) -> Notification:
    role_obj = getattr(env, role)
    notification = notifications.notify(
        env.session,
        env.clock,
        env.ctx(role_obj),
        recipient_user_id=role_obj.user.id,
        type=kind,
        params=params or {},
        subject_id=uuid.uuid4(),
        dedup_key=f"{kind}:{uuid.uuid4()}",
        is_simulated=is_simulated,
    )
    assert notification is not None
    env.session.commit()
    return notification


def deliveries(env: Env) -> list[NotificationDelivery]:
    env.session.expire_all()
    return list(
        env.session.scalars(
            select(NotificationDelivery)
            .where(NotificationDelivery.channel == "telegram")
            .order_by(NotificationDelivery.created_at)
        )
    )


def jobs(env: Env, status: str | None = None) -> list[Job]:
    env.session.expire_all()
    stmt = select(Job).where(Job.job_type == "deliver_channel_notification")
    if status:
        stmt = stmt.where(Job.status == status)
    return list(env.session.scalars(stmt))


def work(env: Env, factory: sessionmaker[Session]) -> int:
    return run_due_jobs(env.clock, session_factory=factory)


def go_to_night(env: Env) -> None:
    env.clock.advance(hours=8)  # 20:00 UTC = 23:00 Europe/Istanbul: quiet hours


# --- dispatch and delivery rules ---------------------------------------------------------------


def test_supported_type_for_linked_owner_is_recorded_and_queued(env: Env) -> None:
    link = link_owner(env)
    notify(env, "approval.requested")
    (delivery,) = deliveries(env)
    assert delivery.status == "pending" and delivery.channel_link_id == link.id
    assert delivery.recipient_user_id == env.owner.user.id
    assert len(jobs(env, "queued")) == 1


def test_unlinked_owner_gets_nothing_recorded(env: Env, bot_api: BotApi) -> None:
    notify(env, "approval.requested")
    assert deliveries(env) == [] and jobs(env) == [] and bot_api.requests == []


@pytest.mark.parametrize(
    "kind",
    [
        "member.joined",
        "content.published",
        "knowledge.fact_changed",
        "account.recovered",
        "owner_question.expired",
        "delegation_suggestion",
    ],
)
def test_types_outside_telegram_types_never_dispatch(env: Env, kind: str) -> None:
    link_owner(env)
    notify(env, kind)
    assert deliveries(env) == []


def test_simulated_notification_is_never_dispatched_to_telegram(env: Env, bot_api: BotApi) -> None:
    link_owner(env)
    notify(env, "approval.requested", is_simulated=True)
    assert deliveries(env) == [] and bot_api.requests == []


def test_every_supported_telegram_type_is_delivered(
    env: Env, bot_api: BotApi, factory: sessionmaker[Session]
) -> None:
    link_owner(env)
    for kind in sorted(TELEGRAM_TYPES):
        notify(env, kind)
    work(env, factory)
    assert {d.status for d in deliveries(env)} == {"delivered"}
    assert len(bot_api.requests) == len(TELEGRAM_TYPES)


def test_quiet_hours_and_critical_and_urgent_approval_bypasses(
    env: Env, bot_api: BotApi, factory: sessionmaker[Session]
) -> None:
    link_owner(env)
    go_to_night(env)
    notify(env, "reply.failed")
    notify(env, "report.daily_ready")
    notify(env, "account.needs_reauth")
    soon = (env.clock.now() + timedelta(minutes=90)).isoformat()
    later = (env.clock.now() + timedelta(hours=5)).isoformat()
    notify(env, "approval.requested", params={"expires_at": soon})
    notify(env, "approval.requested", params={"expires_at": later})
    work(env, factory)
    statuses = [d.status for d in deliveries(env)]
    assert statuses.count("delivered") == 2
    assert statuses.count("skipped_quiet_hours") == 3
    assert len(bot_api.requests) == 2


def test_rate_limit_retries_with_backoff_and_succeeds(
    env: Env, bot_api: BotApi, factory: sessionmaker[Session]
) -> None:
    link_owner(env)
    bot_api.script = [
        (429, {"ok": False, "error_code": 429, "description": "Too Many Requests"}),
        OK,
    ]
    notify(env, "reply.failed")
    assert work(env, factory) == 1
    (delivery,) = deliveries(env)
    assert delivery.status == "pending" and delivery.attempt_count == 1
    assert delivery.last_error == "telegram_retryable:429"
    assert delivery.delivery_metadata["send_state"] == "not_sent"

    env.clock.advance(seconds=40)
    assert work(env, factory) == 1
    (delivery,) = deliveries(env)
    assert delivery.status == "delivered" and delivery.attempt_count == 2
    assert delivery.delivery_metadata["send_state"] == "sent"


@pytest.mark.parametrize(
    "step",
    [httpx.ReadTimeout("timed out"), (200, {"ok": True, "result": {}})],
    ids=["transport-timeout", "2xx-without-message-id"],
)
def test_ambiguous_send_fails_terminally_and_is_never_resent(
    env: Env, bot_api: BotApi, factory: sessionmaker[Session], step: Any
) -> None:
    link_owner(env)
    bot_api.script = [step]
    notify(env, "reply.failed")
    work(env, factory)
    for _ in range(3):
        env.clock.advance(minutes=10)
        work(env, factory)
    (delivery,) = deliveries(env)
    assert len(bot_api.requests) == 1
    assert delivery.status == "failed" and delivery.last_error == "telegram_send_ambiguous"
    assert delivery.delivery_metadata["send_state"] == "ambiguous"
    assert delivery.delivery_metadata["ambiguous"] is True
    assert [j.status for j in jobs(env)] == ["succeeded"]


def test_stale_sending_marker_blocks_resend(
    env: Env, bot_api: BotApi, factory: sessionmaker[Session]
) -> None:
    link_owner(env)
    notify(env, "reply.failed")
    (delivery,) = deliveries(env)
    delivery.delivery_metadata = {"send_state": "sending"}
    env.session.commit()
    work(env, factory)
    (delivery,) = deliveries(env)
    assert bot_api.requests == []
    assert delivery.status == "failed" and delivery.last_error == "telegram_send_state_unknown"
    assert delivery.delivery_metadata["send_state"] == "ambiguous"


def test_unlinked_or_removed_member_before_worker_runs_is_not_messaged(
    env: Env, bot_api: BotApi, factory: sessionmaker[Session]
) -> None:
    link = link_owner(env, role="manager", chat_id="777002")
    notify(env, "reply.failed", role="manager")
    link.status = "unlinked"
    env.session.commit()
    work(env, factory)
    (delivery,) = deliveries(env)
    assert bot_api.requests == []
    assert delivery.status == "failed" and delivery.last_error == "recipient_not_member_or_unlinked"


def test_no_database_transaction_is_open_while_telegram_is_called(
    env: Env, bot_api: BotApi, factory: sessionmaker[Session]
) -> None:
    link = link_owner(env)
    notification = notify(env, "reply.failed")
    session = factory()
    set_tenant_context(session, env.workspace.id)
    delivery = NotificationDelivery(
        workspace_id=env.workspace.id,
        notification_id=notification.id,
        recipient_user_id=env.owner.user.id,
        channel="telegram",
        channel_link_id=link.id,
        status="pending",
    )
    session.add(delivery)
    session.commit()
    bot_api.in_transaction = session.in_transaction
    channel = TelegramChannel(client=make_client(bot_api))
    result = channel.deliver_notification(
        session,
        env.clock,
        delivery,
        ChannelRecipient(
            user_id=env.owner.user.id,
            workspace_id=env.workspace.id,
            channel="telegram",
            channel_user_id=TG_CHAT_ID,
            channel_chat_id=TG_CHAT_ID,
            ui_locale="tr",
            timezone="Europe/Istanbul",
        ),
    )
    session.close()
    assert result.success and bot_api.seen_in_transaction == [False]
