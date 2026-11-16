"""F-01, Session 04: the Web Push owner channel, through the delivery ledger and the job queue.

Proves: a push is recorded and sent only for opted-in users with a device and only for the
supported types; the quiet-hours policy and critical bypass apply; delivery runs in the worker
(job ``deliver_channel_notification``) outside the request; a 404/410 revokes the device; 5xx, 429
and timeouts retry with backoff and the last attempt is visible as a dead job; a user who left the
workspace or opted out in the meantime is not pushed; another user's, another workspace's devices
are never used; the payload carries no customer text; and no log line holds the endpoint or keys.

The push service is replaced by a fake sender (no network); the real sender is covered, against a
fake transport, in ``tests/unit/integrations/channels/test_web_push_sender.py``.
"""

import base64
import json
import uuid
from collections.abc import Iterator
from datetime import timedelta
from typing import Any

import pytest
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker
from structlog.testing import capture_logs

from app.audit.models import AuditLog
from app.core.config import Settings
from app.core.security import generate_vapid_keys
from app.identity.models import User, WorkspaceMember
from app.integrations.channels import registry
from app.integrations.channels.base import ChannelRecipient
from app.integrations.channels.web_push.adapter import WebPushChannel
from app.integrations.channels.web_push.sender import SendOutcome, send_web_push
from app.jobs.models import Job
from app.jobs.testing import run_due_jobs
from app.notifications import push_preferences, push_subscriptions
from app.notifications import service as notifications
from app.notifications.catalog import PUSH_CATEGORIES, PUSH_TYPES
from app.notifications.models import Notification, NotificationDelivery, PushSubscription
from tests.factories import add_member, create_workspace, knowledge_ctx
from tests.helpers.env import Env

PUBLIC, PRIVATE = generate_vapid_keys()
TOKEN_KEYS = "k1:" + base64.b64encode(b"7" * 32).decode()
FCM_ONE = "https://fcm.googleapis.com/fcm/send/device-one-secret-token"
FCM_TWO = "https://updates.push.services.mozilla.com/wpush/v2/device-two-secret-token"


def b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


P256DH = b64(b"\x04" + b"p" * 64)
AUTH = b64(b"a" * 16)


class FakeSender:
    """Records every send; ``script`` maps an endpoint to an outcome (default: sent)."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.script: dict[str, list[SendOutcome]] = {}
        self.default = SendOutcome("sent", status_code=201)

    def __call__(self, **kwargs: Any) -> SendOutcome:
        self.calls.append(kwargs)
        queue = self.script.get(kwargs["endpoint"])
        if queue:
            return queue.pop(0) if len(queue) > 1 else queue[0]
        return self.default

    def payloads(self) -> list[dict[str, Any]]:
        return [json.loads(call["payload"]) for call in self.calls]


GONE = SendOutcome("gone", "subscription_gone", 410)
RETRY = SendOutcome("retry", "push_service_unavailable", 503)


@pytest.fixture
def push_settings(settings: Settings) -> Settings:
    return settings.model_copy(
        update={
            "web_push_vapid_public_key": PUBLIC,
            "web_push_vapid_private_key": SecretStr(PRIVATE),
            "web_push_subject": "mailto:ops@example.com",
            "token_encryption_keys": SecretStr(TOKEN_KEYS),
            "token_encryption_active_key_id": "k1",
        }
    )


@pytest.fixture
def sender() -> FakeSender:
    return FakeSender()


@pytest.fixture(autouse=True)
def wired(
    monkeypatch: pytest.MonkeyPatch, push_settings: Settings, sender: FakeSender
) -> Iterator[None]:
    """Push on for ``notify``, and the registry's web_push channel using the fake sender."""
    monkeypatch.setattr("app.notifications.push_dispatch.get_settings", lambda: push_settings)
    registry.reset_channel_registry()
    registry.register_channel("web_push", WebPushChannel(sender=sender, settings=push_settings))
    yield
    registry.reset_channel_registry()


@pytest.fixture
def factory(db_session: Session) -> sessionmaker[Session]:
    return sessionmaker(
        bind=db_session.get_bind(),
        expire_on_commit=False,
        autoflush=False,
        join_transaction_mode="create_savepoint",
    )


def add_device(
    env: Env,
    settings: Settings,
    *,
    role: str = "owner",
    endpoint: str = FCM_ONE,
    categories: tuple[str, ...] = PUSH_CATEGORIES,
) -> PushSubscription:
    user = getattr(env, role).user
    ctx = env.ctx(getattr(env, role))
    row, _ = push_subscriptions.subscribe(
        env.session,
        env.clock,
        settings,
        ctx,
        user.id,
        endpoint=endpoint,
        p256dh=P256DH,
        auth=AUTH,
        user_agent=None,
        label=None,
    )
    if categories:
        push_preferences.set_preferences(
            env.session, env.clock, ctx, user.id, dict.fromkeys(categories, True)
        )
    return row


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
        env.session.scalars(select(NotificationDelivery).order_by(NotificationDelivery.created_at))
    )


def jobs(env: Env, status: str | None = None) -> list[Job]:
    env.session.expire_all()
    stmt = select(Job).where(Job.job_type == "deliver_channel_notification")
    if status:
        stmt = stmt.where(Job.status == status)
    return list(env.session.scalars(stmt))


def work(env: Env, factory: sessionmaker[Session]) -> int:
    return run_due_jobs(env.clock, session_factory=factory)


def subscription(env: Env, sub_id: uuid.UUID) -> PushSubscription:
    env.session.expire_all()
    row = env.session.get(PushSubscription, sub_id)
    assert row is not None
    return row


# --- when a push is recorded at all ------------------------------------------------------------


def test_a_supported_type_for_an_opted_in_user_with_a_device_is_recorded_and_queued(
    env: Env, push_settings: Settings
) -> None:
    add_device(env, push_settings)
    notify(env, "approval.requested")
    (delivery,) = deliveries(env)
    assert delivery.channel == "web_push" and delivery.status == "pending"
    assert delivery.recipient_user_id == env.owner.user.id
    assert len(jobs(env, "queued")) == 1


def test_nothing_is_recorded_without_opt_in(env: Env, push_settings: Settings) -> None:
    add_device(env, push_settings, categories=())
    notify(env, "approval.requested")
    assert deliveries(env) == [] and jobs(env) == []


def test_nothing_is_recorded_without_a_device(env: Env, push_settings: Settings) -> None:
    push_preferences.set_preferences(
        env.session, env.clock, env.ctx(env.owner), env.owner.user.id, {"approvals": True}
    )
    notify(env, "approval.requested")
    assert deliveries(env) == [] and jobs(env) == []


def test_nothing_is_recorded_when_push_is_not_configured(
    env: Env, push_settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    add_device(env, push_settings)
    off = push_settings.model_copy(update={"web_push_vapid_private_key": SecretStr("")})
    monkeypatch.setattr("app.notifications.push_dispatch.get_settings", lambda: off)
    notify(env, "approval.requested")
    assert deliveries(env) == []


@pytest.mark.parametrize("kind", ["report.daily_ready", "member.joined", "content.published"])
def test_types_outside_the_push_list_never_push(
    env: Env, push_settings: Settings, kind: str
) -> None:
    add_device(env, push_settings)
    notify(env, kind)
    assert deliveries(env) == []


def test_opt_in_is_per_category(env: Env, push_settings: Settings) -> None:
    add_device(env, push_settings, categories=("failures",))
    notify(env, "approval.requested")
    notify(env, "owner_question.requested")
    assert deliveries(env) == []
    notify(env, "reply.failed")
    notify(env, "content.failed")
    notify(env, "account.needs_reauth")
    assert len(deliveries(env)) == 3


def test_every_supported_type_is_a_catalog_type_in_a_known_category() -> None:
    from app.notifications.catalog import CATALOG

    assert set(PUSH_TYPES) <= set(CATALOG)
    assert set(PUSH_TYPES.values()) == set(PUSH_CATEGORIES)


# --- delivery ----------------------------------------------------------------------------------


def test_a_push_is_delivered_by_the_worker_and_recorded(
    env: Env, push_settings: Settings, sender: FakeSender, factory: sessionmaker[Session]
) -> None:
    device = add_device(env, push_settings)
    notify(env, "approval.requested")
    assert sender.calls == []  # the request path sends nothing

    assert work(env, factory) == 1
    (delivery,) = deliveries(env)
    assert delivery.status == "delivered" and delivery.last_error is None
    assert delivery.sent_at == env.clock.now() and delivery.attempt_count == 1
    assert subscription(env, device.id).last_success_at == env.clock.now()
    (call,) = sender.calls
    assert call["endpoint"] == FCM_ONE and call["p256dh"] == P256DH and call["auth"] == AUTH
    assert call["vapid_subject"] == "mailto:ops@example.com"
    assert call["urgency"] == "normal" and call["ttl"] == 3600
    (payload,) = sender.payloads()
    assert set(payload) == {"title", "body", "url", "tag"}
    assert payload["url"] == f"/w/{env.workspace.id}/approvals"
    assert [j.status for j in jobs(env)] == ["succeeded"]


def test_a_critical_notification_is_sent_with_high_urgency(
    env: Env, push_settings: Settings, sender: FakeSender, factory: sessionmaker[Session]
) -> None:
    add_device(env, push_settings)
    notify(env, "account.needs_reauth")
    work(env, factory)
    assert sender.calls[0]["urgency"] == "high"


def test_no_database_transaction_is_open_while_the_push_service_is_called(
    env: Env, push_settings: Settings, factory: sessionmaker[Session]
) -> None:
    """The adapter ends its read transaction before the first send (INV: no external call in a
    transaction): the session it was handed reports no open transaction inside the sender."""
    device = add_device(env, push_settings)
    notification = notify(env, "approval.requested")
    seen: list[bool] = []
    holder: dict[str, Session] = {}

    def spying(**kwargs: Any) -> SendOutcome:
        seen.append(holder["s"].in_transaction())
        return SendOutcome("sent", status_code=201)

    channel = WebPushChannel(sender=spying, settings=push_settings)
    session = factory()
    holder["s"] = session
    from app.core.db import set_tenant_context

    set_tenant_context(session, env.workspace.id)
    delivery = NotificationDelivery(
        workspace_id=env.workspace.id,
        notification_id=notification.id,
        recipient_user_id=env.owner.user.id,
        channel="web_push",
        status="pending",
    )
    session.add(delivery)
    session.commit()
    result = channel.deliver_notification(
        session,
        env.clock,
        delivery,
        ChannelRecipient(
            user_id=env.owner.user.id, workspace_id=env.workspace.id, channel="web_push"
        ),
    )
    assert result.success and seen == [False]
    assert subscription(env, device.id).last_success_at == env.clock.now()


@pytest.mark.parametrize("gone", [404, 410])
def test_a_gone_device_is_revoked_and_audited(
    env: Env,
    push_settings: Settings,
    sender: FakeSender,
    factory: sessionmaker[Session],
    gone: int,
) -> None:
    device = add_device(env, push_settings)
    sender.default = SendOutcome("gone", "subscription_gone", gone)
    notify(env, "approval.requested")
    work(env, factory)

    row = subscription(env, device.id)
    assert row.revoked_at == env.clock.now() and row.last_success_at is None
    (delivery,) = deliveries(env)
    assert delivery.status == "failed" and delivery.last_error == "subscription_gone"
    assert [j.status for j in jobs(env)] == ["succeeded"]  # a gone device is not a worker crash
    entries = list(
        env.session.scalars(select(AuditLog).where(AuditLog.action == "push_subscription.revoked"))
    )
    assert len(entries) == 1
    assert entries[0].resource_id == device.id and entries[0].actor_type == "system"
    assert entries[0].metadata_["reason"] == "subscription_gone"

    # No device left: the next notification is not even recorded.
    notify(env, "approval.requested")
    assert len(deliveries(env)) == 1


def test_one_gone_device_does_not_stop_the_other_and_the_push_counts_as_delivered(
    env: Env, push_settings: Settings, sender: FakeSender, factory: sessionmaker[Session]
) -> None:
    dead = add_device(env, push_settings, endpoint=FCM_ONE)
    alive = add_device(env, push_settings, endpoint=FCM_TWO)
    sender.script[FCM_ONE] = [GONE]
    notify(env, "approval.requested")
    work(env, factory)
    assert len(sender.calls) == 2
    assert subscription(env, dead.id).revoked_at is not None
    assert subscription(env, alive.id).revoked_at is None
    assert subscription(env, alive.id).last_success_at == env.clock.now()
    assert deliveries(env)[0].status == "delivered"


def test_a_transient_failure_is_retried_with_backoff_and_then_delivered(
    env: Env, push_settings: Settings, sender: FakeSender, factory: sessionmaker[Session]
) -> None:
    device = add_device(env, push_settings)
    sender.script[FCM_ONE] = [RETRY, SendOutcome("sent", status_code=201)]
    notify(env, "approval.requested")

    assert work(env, factory) == 1
    (delivery,) = deliveries(env)
    assert delivery.status == "pending" and delivery.attempt_count == 1  # not failed yet
    assert delivery.last_error == "push_service_unavailable"
    assert [j.status for j in jobs(env)] == ["queued"] and jobs(env)[0].attempts == 1
    assert subscription(env, device.id).last_success_at is None
    assert work(env, factory) == 0  # backoff: not due yet

    env.clock.advance(seconds=40)
    assert work(env, factory) == 1
    (delivery,) = deliveries(env)
    assert delivery.status == "delivered" and delivery.attempt_count == 2
    assert delivery.last_error is None
    assert [j.status for j in jobs(env)] == ["succeeded"]
    assert subscription(env, device.id).last_success_at is not None


def test_when_every_attempt_fails_the_delivery_fails_and_the_job_is_dead(
    env: Env, push_settings: Settings, sender: FakeSender, factory: sessionmaker[Session]
) -> None:
    add_device(env, push_settings)
    sender.default = RETRY
    notify(env, "approval.requested")
    for _ in range(3):
        work(env, factory)
        env.clock.advance(minutes=5)
    (delivery,) = deliveries(env)
    assert delivery.status == "failed" and delivery.attempt_count == 3
    assert [j.status for j in jobs(env)] == ["dead"]  # visible, not silent
    assert len(sender.calls) == 3


def test_a_push_service_refusing_the_vapid_key_fails_without_retry_or_revocation(
    env: Env, push_settings: Settings, sender: FakeSender, factory: sessionmaker[Session]
) -> None:
    device = add_device(env, push_settings)
    sender.default = SendOutcome("failed", "push_service_rejected_vapid", 403)
    notify(env, "approval.requested")
    work(env, factory)
    assert len(sender.calls) == 1
    assert subscription(env, device.id).revoked_at is None
    assert deliveries(env)[0].last_error == "push_service_rejected_vapid"


def test_the_ssrf_guard_applies_through_the_channel(
    env: Env,
    push_settings: Settings,
    factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An endpoint that resolves inward is refused without being sent to, and the device is
    kept; an endpoint outside the allowlist can never work, so the device is revoked."""
    import socket

    def inward(host: str, port: int, **_: Any) -> list[tuple[Any, ...]]:
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.7", port))]

    posts: list[str] = []

    def push_fn(**kwargs: Any) -> Any:
        posts.append(kwargs["subscription_info"]["endpoint"])
        raise AssertionError("must not be sent")

    def guarded(**kwargs: Any) -> SendOutcome:
        return send_web_push(**kwargs, resolver=inward, push_fn=push_fn)

    registry.register_channel("web_push", WebPushChannel(sender=guarded, settings=push_settings))
    good = add_device(env, push_settings, endpoint=FCM_ONE)
    foreign = add_device(env, push_settings, endpoint="https://evil.example.com/push/abc")
    notify(env, "approval.requested")
    work(env, factory)
    assert posts == []
    assert subscription(env, good.id).revoked_at is None  # transient: may resolve properly later
    assert subscription(env, foreign.id).revoked_at is not None  # never allowed
    (delivery,) = deliveries(env)
    assert delivery.status == "failed"


# --- quiet hours and critical bypass -----------------------------------------------------------


def go_to_night(env: Env) -> None:
    env.clock.advance(hours=8)  # 20:00 UTC = 23:00 Europe/Istanbul: quiet hours


def test_quiet_hours_hold_an_ordinary_notification(
    env: Env, push_settings: Settings, sender: FakeSender, factory: sessionmaker[Session]
) -> None:
    add_device(env, push_settings)
    go_to_night(env)
    notify(env, "reply.failed")
    notify(env, "owner_question.requested")
    work(env, factory)
    assert [d.status for d in deliveries(env)] == ["skipped_quiet_hours"] * 2
    assert jobs(env) == [] and sender.calls == []


def test_a_critical_notification_bypasses_quiet_hours(
    env: Env, push_settings: Settings, sender: FakeSender, factory: sessionmaker[Session]
) -> None:
    add_device(env, push_settings)
    go_to_night(env)
    notify(env, "account.needs_reauth")
    work(env, factory)
    assert deliveries(env)[0].status == "delivered" and len(sender.calls) == 1


def test_an_approval_expiring_within_two_hours_bypasses_quiet_hours(
    env: Env, push_settings: Settings, sender: FakeSender, factory: sessionmaker[Session]
) -> None:
    add_device(env, push_settings)
    go_to_night(env)
    soon = (env.clock.now() + timedelta(minutes=90)).isoformat()
    later = (env.clock.now() + timedelta(hours=5)).isoformat()
    notify(env, "approval.requested", params={"expires_at": later})
    notify(env, "approval.requested", params={"expires_at": soon})
    work(env, factory)
    assert sorted(d.status for d in deliveries(env)) == ["delivered", "skipped_quiet_hours"]
    assert len(sender.calls) == 1


def test_daytime_delivers_ordinary_notifications(
    env: Env, push_settings: Settings, sender: FakeSender, factory: sessionmaker[Session]
) -> None:
    add_device(env, push_settings)
    notify(env, "reply.failed")
    work(env, factory)
    assert deliveries(env)[0].status == "delivered"


# --- who is pushed -----------------------------------------------------------------------------


def test_a_member_who_left_the_workspace_is_not_pushed(
    env: Env, push_settings: Settings, sender: FakeSender, factory: sessionmaker[Session]
) -> None:
    device = add_device(env, push_settings, role="manager")
    notify(env, "approval.requested", role="manager")
    member = env.session.get(WorkspaceMember, (env.workspace.id, env.manager.user.id))
    env.session.delete(member)
    env.session.commit()
    work(env, factory)
    assert sender.calls == []
    assert deliveries(env)[0].status == "failed"
    assert subscription(env, device.id).last_success_at is None


def test_the_channel_itself_skips_a_user_who_is_no_longer_an_active_member(
    env: Env, push_settings: Settings, sender: FakeSender
) -> None:
    add_device(env, push_settings, role="manager")
    notification = notify(env, "approval.requested", role="manager")
    delivery = NotificationDelivery(
        workspace_id=env.workspace.id,
        notification_id=notification.id,
        recipient_user_id=env.manager.user.id,
        channel="web_push",
        status="pending",
    )
    env.session.add(delivery)
    env.session.commit()
    recipient = ChannelRecipient(
        user_id=env.manager.user.id, workspace_id=env.workspace.id, channel="web_push"
    )
    channel = WebPushChannel(sender=sender, settings=push_settings)

    env.session.get(User, env.manager.user.id).is_active = False  # type: ignore[union-attr]
    env.session.commit()
    result = channel.deliver_notification(env.session, env.clock, delivery, recipient)
    assert not result.success and result.error_message == "recipient_not_member"
    assert result.metadata["terminal"] and sender.calls == []


def test_a_user_who_opts_out_before_the_send_is_not_pushed(
    env: Env, push_settings: Settings, sender: FakeSender, factory: sessionmaker[Session]
) -> None:
    add_device(env, push_settings)
    notify(env, "approval.requested")
    push_preferences.set_preferences(
        env.session, env.clock, env.ctx(env.owner), env.owner.user.id, {"approvals": False}
    )
    work(env, factory)
    assert sender.calls == []
    (delivery,) = deliveries(env)
    assert delivery.status == "failed" and delivery.last_error == "not_opted_in"
    assert [j.status for j in jobs(env)] == ["succeeded"]


def test_only_the_recipients_own_devices_are_used(
    env: Env, push_settings: Settings, sender: FakeSender, factory: sessionmaker[Session]
) -> None:
    add_device(env, push_settings, role="owner", endpoint=FCM_ONE)
    add_device(env, push_settings, role="manager", endpoint=FCM_TWO)
    notify(env, "approval.requested", role="owner")
    work(env, factory)
    assert [c["endpoint"] for c in sender.calls] == [FCM_ONE]


def test_a_device_registered_in_another_workspace_is_never_used(
    env: Env, push_settings: Settings, sender: FakeSender, factory: sessionmaker[Session]
) -> None:
    """The owner is also a member of workspace B and registered a device only there."""
    other = create_workspace(env.session, name="Other", slug="other-ws")
    add_member(env.session, other, env.owner.user, "owner")
    other_ctx = knowledge_ctx(other, env.owner.user, "owner")
    push_subscriptions.subscribe(
        env.session,
        env.clock,
        push_settings,
        other_ctx,
        env.owner.user.id,
        endpoint=FCM_TWO,
        p256dh=P256DH,
        auth=AUTH,
        user_agent=None,
        label=None,
    )
    push_preferences.set_preferences(
        env.session, env.clock, other_ctx, env.owner.user.id, {"approvals": True}
    )
    # Workspace A: the owner has opted in nowhere and has no device there.
    notify(env, "approval.requested")
    assert deliveries(env) == []
    # Even with the opt-in in A, B's device is not A's.
    push_preferences.set_preferences(
        env.session, env.clock, env.ctx(env.owner), env.owner.user.id, {"approvals": True}
    )
    notify(env, "approval.requested")
    assert deliveries(env) == []
    work(env, factory)
    assert sender.calls == []


def test_a_member_of_another_workspace_cannot_be_reached_through_a_foreign_delivery(
    env: Env, push_settings: Settings, sender: FakeSender
) -> None:
    """A ledger row whose notification belongs to someone else is refused, not sent."""
    add_device(env, push_settings)
    add_device(env, push_settings, role="manager", endpoint=FCM_TWO)
    notification = notify(env, "approval.requested", role="manager")
    delivery = NotificationDelivery(
        workspace_id=env.workspace.id,
        notification_id=notification.id,
        recipient_user_id=env.owner.user.id,  # not the notification's recipient
        channel="web_push",
        status="pending",
    )
    env.session.add(delivery)
    env.session.commit()
    channel = WebPushChannel(sender=sender, settings=push_settings)
    result = channel.deliver_notification(
        env.session,
        env.clock,
        delivery,
        ChannelRecipient(
            user_id=env.owner.user.id, workspace_id=env.workspace.id, channel="web_push"
        ),
    )
    assert not result.success and sender.calls == []


# --- logs --------------------------------------------------------------------------------------


def test_no_log_line_carries_the_endpoint_the_keys_or_the_payload(
    env: Env, push_settings: Settings, sender: FakeSender, factory: sessionmaker[Session]
) -> None:
    add_device(env, push_settings, endpoint=FCM_ONE)
    add_device(env, push_settings, endpoint=FCM_TWO)
    sender.script[FCM_ONE] = [GONE]
    sender.script[FCM_TWO] = [RETRY]
    with capture_logs() as logs:
        notify(env, "approval.requested")
        work(env, factory)
        env.clock.advance(minutes=5)
        sender.script[FCM_TWO] = [SendOutcome("sent", status_code=201)]
        work(env, factory)
    text = json.dumps(logs, default=str)
    assert "web_push_subscription_revoked" in text  # we did log, with ids only
    for secret in (FCM_ONE, FCM_TWO, "secret-token", P256DH, AUTH, PRIVATE, "fcm.googleapis"):
        assert secret not in text


# --- registry ----------------------------------------------------------------------------------


def test_the_channel_is_registered_lazily_in_the_registry() -> None:
    registry.reset_channel_registry()
    channel = registry.get_channel("web_push")
    assert isinstance(channel, WebPushChannel) and channel.name == "web_push"
    assert registry.get_channel("web_push") is channel
    registry.reset_channel_registry()


def test_a_second_user_in_the_same_workspace_keeps_their_own_preferences(
    env: Env, push_settings: Settings
) -> None:
    push_preferences.set_preferences(
        env.session, env.clock, env.ctx(env.owner), env.owner.user.id, {"approvals": True}
    )
    assert push_preferences.get_preferences(env.session, env.workspace.id, env.owner.user.id) == {
        "approvals": True,
        "questions": False,
        "failures": False,
    }
    assert push_preferences.get_preferences(env.session, env.workspace.id, env.manager.user.id) == {
        "approvals": False,
        "questions": False,
        "failures": False,
    }


def test_unknown_categories_are_rejected(env: Env) -> None:
    from app.core.errors import AppError

    with pytest.raises(AppError):
        push_preferences.set_preferences(
            env.session, env.clock, env.ctx(env.owner), env.owner.user.id, {"everything": True}
        )
