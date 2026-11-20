"""F-06, Feature Phase 5 Session 02: WhatsApp notifications through the delivery ledger.

Proves: a message is recorded only for an owner with an active WhatsApp link and a supported type;
the quiet-hours policy and critical bypass apply; a session message is sent inside the 24-hour
window and an approved template outside it (both boundaries); an unapproved template is never
sent; cost metadata (category, template or session, an unverified-price note) is kept on the ledger
row; 429 and 5xx retry with backoff; a rejected message fails without retry; an ambiguous send
(timeout, 2xx without an id, a stale "sending" marker) is never re-sent; the daily summary carries
numbers only; no customer text reaches the provider; no transaction is open during the HTTP call;
and the webhook moves the window and records the provider's status and billing flags.

The Cloud API is replaced by ``httpx.MockTransport`` (no network).
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Callable, Iterator
from datetime import timedelta
from typing import Any

import httpx
import pytest
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.core.db import set_tenant_context
from app.identity.models import ChannelLink
from app.integrations.channels import registry
from app.integrations.channels.base import ChannelRecipient
from app.integrations.channels.whatsapp import templates, window
from app.integrations.channels.whatsapp.adapter import WhatsAppChannel
from app.integrations.channels.whatsapp.client import WhatsAppClient
from app.integrations.channels.whatsapp.dispatcher import process_webhook
from app.jobs.models import Job
from app.jobs.testing import run_due_jobs
from app.notifications import service as notifications
from app.notifications.catalog import WHATSAPP_TYPES
from app.notifications.models import Notification, NotificationDelivery
from tests.helpers.env import Env
from tests.unit.integrations.channels.test_whatsapp_webhook_format import envelope

WA_ID = "905550000001"
TOKEN = "synthetic-wa-token-private"
OK = (200, {"messaging_product": "whatsapp", "messages": [{"id": "wamid.OUT1"}]})


class Cloud:
    """A scripted Cloud API: records each request body; answers from `script`, then `default`."""

    def __init__(self) -> None:
        self.requests: list[dict[str, Any]] = []
        self.script: list[Any] = []
        self.default: Any = OK
        self.in_transaction: Callable[[], bool] | None = None
        self.seen_in_transaction: list[bool] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        if self.in_transaction is not None:
            self.seen_in_transaction.append(self.in_transaction())
        self.requests.append(json.loads(request.content))
        step = self.script.pop(0) if self.script else self.default
        if isinstance(step, Exception):
            raise step
        status, body = step
        return httpx.Response(status, json=body)

    @property
    def kinds(self) -> list[str]:
        return [r["type"] for r in self.requests]


@pytest.fixture
def cloud() -> Cloud:
    return Cloud()


@pytest.fixture
def wa_settings(settings: Settings) -> Settings:
    return settings.model_copy(
        update={
            "whatsapp_access_token": SecretStr(TOKEN),
            "whatsapp_app_secret": SecretStr("synthetic-wa-app-secret"),
            "whatsapp_webhook_verify_token": SecretStr("verify"),
            "whatsapp_phone_number_id": "123",
            "whatsapp_display_phone_number": "905551112233",
            "whatsapp_templates_approved": True,
        }
    )


@pytest.fixture
def factory(db_session: Session) -> sessionmaker[Session]:
    return sessionmaker(
        bind=db_session.get_bind(),
        expire_on_commit=False,
        autoflush=False,
        join_transaction_mode="create_savepoint",
    )


def make_client(cloud: Cloud) -> WhatsAppClient:
    return WhatsAppClient(
        access_token=SecretStr(TOKEN),
        phone_number_id="123",
        transport=httpx.MockTransport(cloud),
    )


@pytest.fixture(autouse=True)
def wired(monkeypatch: pytest.MonkeyPatch, wa_settings: Settings, cloud: Cloud) -> Iterator[None]:
    monkeypatch.setattr("app.notifications.whatsapp_dispatch.get_settings", lambda: wa_settings)
    registry.reset_channel_registry()
    registry.register_channel(
        "whatsapp", WhatsAppChannel(client=make_client(cloud), settings=wa_settings)
    )
    yield
    registry.reset_channel_registry()


def link_owner(
    env: Env,
    *,
    role: str = "owner",
    inbound_ago: timedelta | None = timedelta(hours=1),
    wa_id: str = WA_ID,
) -> ChannelLink:
    user = getattr(env, role).user
    link = ChannelLink(
        workspace_id=env.workspace.id,
        user_id=user.id,
        channel="whatsapp",
        channel_user_id=wa_id,
        channel_chat_id=wa_id,
        status="active",
        linked_at=env.clock.now(),
        last_inbound_at=None if inbound_ago is None else env.clock.now() - inbound_ago,
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
            .where(NotificationDelivery.channel == "whatsapp")
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


# --- when a message is recorded at all ---------------------------------------------------------


def test_a_supported_type_for_a_linked_owner_is_recorded_and_queued(env: Env) -> None:
    link = link_owner(env)
    notify(env, "approval.requested")
    (delivery,) = deliveries(env)
    assert delivery.status == "pending" and delivery.channel_link_id == link.id
    assert delivery.recipient_user_id == env.owner.user.id
    assert len(jobs(env, "queued")) == 1


def test_an_unlinked_owner_gets_nothing_recorded(env: Env, cloud: Cloud) -> None:
    notify(env, "approval.requested")
    assert deliveries(env) == [] and jobs(env) == [] and cloud.requests == []


def test_only_the_linked_member_of_the_workspace_is_messaged(env: Env) -> None:
    link_owner(env, role="owner")
    notify(env, "approval.requested", role="manager")
    assert deliveries(env) == []
    notify(env, "approval.requested", role="owner")
    assert len(deliveries(env)) == 1


def test_an_unlinked_link_is_not_used(env: Env) -> None:
    link = link_owner(env)
    link.status = "unlinked"
    env.session.commit()
    notify(env, "approval.requested")
    assert deliveries(env) == []


def test_nothing_is_recorded_when_whatsapp_is_not_configured(
    env: Env, wa_settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    link_owner(env)
    off = wa_settings.model_copy(update={"whatsapp_access_token": None})
    monkeypatch.setattr("app.notifications.whatsapp_dispatch.get_settings", lambda: off)
    notify(env, "approval.requested")
    assert deliveries(env) == []


@pytest.mark.parametrize("kind", ["member.joined", "content.published", "knowledge.fact_changed"])
def test_types_outside_the_list_never_go_to_whatsapp(env: Env, kind: str) -> None:
    link_owner(env)
    notify(env, kind)
    assert deliveries(env) == []


def test_a_simulated_notification_is_never_sent(env: Env, cloud: Cloud) -> None:
    link_owner(env)
    notify(env, "approval.requested", is_simulated=True)
    assert deliveries(env) == [] and cloud.requests == []


def test_every_supported_type_is_delivered_with_its_template_text(
    env: Env, cloud: Cloud, factory: sessionmaker[Session]
) -> None:
    link_owner(env)
    summary = {
        "local_date": "2026-11-18",
        "inbound_messages": 3,
        "replies_sent": 2,
        "pending_approvals": 1,
    }
    for kind in sorted(WHATSAPP_TYPES):
        notify(env, kind, params=summary if kind == "report.daily_ready" else None)
    work(env, factory)
    assert {d.status for d in deliveries(env)} == {"delivered"}
    assert len(cloud.requests) == len(WHATSAPP_TYPES)
    sent = {r["text"]["body"] for r in cloud.requests}
    locale = env.owner.user.ui_locale
    for kind in WHATSAPP_TYPES:
        template = templates.BY_TYPE[kind]
        values = templates.variable_values(template, summary, locale) or []
        assert template.render(locale, values) in sent


# --- session message or template ---------------------------------------------------------------


def test_inside_the_window_a_session_message_is_sent_with_the_template_text(
    env: Env, cloud: Cloud, factory: sessionmaker[Session]
) -> None:
    link_owner(env, inbound_ago=timedelta(hours=2))
    notify(env, "approval.requested")
    assert work(env, factory) == 1
    (request,) = cloud.requests
    assert request["type"] == "text" and request["to"] == WA_ID
    template = templates.BY_TYPE["approval.requested"]
    assert request["text"]["body"] == template.render(env.owner.user.ui_locale, [])
    (delivery,) = deliveries(env)
    assert delivery.status == "delivered" and delivery.sent_at == env.clock.now()
    meta = delivery.delivery_metadata
    assert meta["wamid"] == "wamid.OUT1" and meta["send_state"] == "sent"
    assert meta["cost"]["send_mode"] == "session" and meta["cost"]["is_template"] is False
    assert meta["cost"]["category"] == "service"
    assert meta["cost"]["price_verified"] is False and meta["cost"]["price_amount"] is None
    assert "terminal" not in meta and "retryable" not in meta


def test_outside_the_window_an_approved_template_is_sent(
    env: Env, cloud: Cloud, factory: sessionmaker[Session]
) -> None:
    link_owner(env, inbound_ago=timedelta(hours=30))
    notify(env, "approval.requested")
    work(env, factory)
    (request,) = cloud.requests
    template = templates.BY_TYPE["approval.requested"]
    assert request["type"] == "template"
    assert request["template"]["name"] == template.name == "pivoris_approval_requested_v1"
    assert request["template"]["language"] == {"code": env.owner.user.ui_locale[:2]}
    assert "components" not in request["template"]  # no variables
    (delivery,) = deliveries(env)
    cost = delivery.delivery_metadata["cost"]
    assert delivery.status == "delivered"
    assert cost["send_mode"] == "template" and cost["is_template"] is True
    assert cost["category"] == "utility" and cost["template_name"] == template.name
    assert cost["price_verified"] is False and cost["currency"] is None


def test_a_never_messaged_number_is_template_only(
    env: Env, cloud: Cloud, factory: sessionmaker[Session]
) -> None:
    link_owner(env, inbound_ago=None)
    notify(env, "approval.requested")
    work(env, factory)
    assert cloud.kinds == ["template"]


@pytest.mark.parametrize(
    ("age", "kind"),
    [
        (window.WINDOW - window.SAFETY_MARGIN - timedelta(seconds=1), "text"),
        (window.WINDOW - window.SAFETY_MARGIN, "template"),
        (window.WINDOW, "template"),
        (window.WINDOW + timedelta(seconds=1), "template"),
    ],
)
def test_the_choice_at_the_window_boundaries(
    env: Env, cloud: Cloud, factory: sessionmaker[Session], age: timedelta, kind: str
) -> None:
    link_owner(env, inbound_ago=age)
    notify(env, "approval.requested")
    work(env, factory)
    assert cloud.kinds == [kind]


def test_the_window_is_measured_at_send_time_not_at_record_time(
    env: Env, cloud: Cloud, factory: sessionmaker[Session]
) -> None:
    link_owner(env, inbound_ago=timedelta(hours=23, minutes=50))
    notify(env, "approval.requested")  # recorded with the window still open
    env.clock.advance(minutes=30)  # it closes before the worker runs
    work(env, factory)
    assert cloud.kinds == ["template"]


def test_an_unapproved_template_is_never_sent(
    env: Env,
    cloud: Cloud,
    factory: sessionmaker[Session],
    wa_settings: Settings,
) -> None:
    link_owner(env, inbound_ago=timedelta(hours=30))
    channel = WhatsAppChannel(
        client=make_client(cloud),
        settings=wa_settings.model_copy(update={"whatsapp_templates_approved": False}),
    )
    registry.register_channel("whatsapp", channel)
    notify(env, "approval.requested")
    work(env, factory)
    (delivery,) = deliveries(env)
    assert cloud.requests == []
    assert delivery.status == "failed" and delivery.last_error == "whatsapp_templates_not_approved"
    assert delivery.attempt_count == 1 and [j.status for j in jobs(env)] == ["succeeded"]
    assert delivery.delivery_metadata["cost"]["send_mode"] == "template"
    # ...but the window being open still works without any template approval
    link = env.session.scalar(select(ChannelLink))
    assert link is not None
    link.last_inbound_at = env.clock.now()
    env.session.commit()
    notify(env, "reply.failed")
    work(env, factory)
    assert cloud.kinds == ["text"]


# --- the daily summary -------------------------------------------------------------------------


def test_the_daily_summary_carries_the_date_and_three_counts(
    env: Env, cloud: Cloud, factory: sessionmaker[Session]
) -> None:
    link_owner(env, inbound_ago=timedelta(days=2))
    notify(
        env,
        "report.daily_ready",
        params={
            "local_date": "2026-11-18",
            "inbound_messages": 12,
            "replies_sent": 5,
            "pending_approvals": 2,
            "customer_message": "my secret order 5551234",
        },
    )
    work(env, factory)
    (request,) = cloud.requests
    assert request["type"] == "template"
    assert request["template"]["name"] == "pivoris_daily_summary_v1"
    values = [p["text"] for p in request["template"]["components"][0]["parameters"]]
    expected = ["18.11.2026", "12", "5", "2"]
    if env.owner.user.ui_locale != "tr":
        expected[0] = "2026-11-18"
    assert values == expected
    assert "secret" not in json.dumps(request)


def test_a_summary_without_its_numbers_fails_terminally_and_sends_nothing(
    env: Env, cloud: Cloud, factory: sessionmaker[Session]
) -> None:
    link_owner(env)
    notify(env, "report.daily_ready", params={"local_date": "2026-11-18"})
    work(env, factory)
    (delivery,) = deliveries(env)
    assert cloud.requests == []
    assert delivery.status == "failed" and delivery.last_error == "template_variables_missing"
    assert [j.status for j in jobs(env)] == ["succeeded"]  # terminal: not retried


def test_customer_text_in_params_never_reaches_the_provider(
    env: Env, cloud: Cloud, factory: sessionmaker[Session]
) -> None:
    link_owner(env)
    leaked = "Ayşe Hanım 0555 123 45 67 siparişim nerede"
    for kind in ("reply.failed", "owner_question.requested", "content.failed"):
        notify(
            env,
            kind,
            params={
                "text": leaked,
                "message": leaked,
                "question": leaked,
                "customer": leaked,
                "title": leaked,
            },
        )
    work(env, factory)
    assert len(cloud.requests) == 3
    assert "Ayşe" not in json.dumps(cloud.requests, ensure_ascii=False)
    assert "5551234567" not in json.dumps(cloud.requests).replace(" ", "")


# --- quiet hours -------------------------------------------------------------------------------


def test_quiet_hours_hold_an_ordinary_notification(
    env: Env, cloud: Cloud, factory: sessionmaker[Session]
) -> None:
    link_owner(env)
    go_to_night(env)
    notify(env, "reply.failed")
    notify(env, "owner_question.requested")
    work(env, factory)
    assert [d.status for d in deliveries(env)] == ["skipped_quiet_hours"] * 2
    assert jobs(env) == [] and cloud.requests == []


def test_the_daily_summary_follows_quiet_hours_too(
    env: Env, cloud: Cloud, factory: sessionmaker[Session]
) -> None:
    link_owner(env)
    go_to_night(env)
    notify(
        env,
        "report.daily_ready",
        params={
            "local_date": "2026-11-18",
            "inbound_messages": 1,
            "replies_sent": 1,
            "pending_approvals": 0,
        },
    )
    work(env, factory)
    assert [d.status for d in deliveries(env)] == ["skipped_quiet_hours"]
    assert cloud.requests == []


def test_a_critical_notification_bypasses_quiet_hours(
    env: Env, cloud: Cloud, factory: sessionmaker[Session]
) -> None:
    link_owner(env, inbound_ago=timedelta(hours=1))
    go_to_night(env)
    notify(env, "account.needs_reauth")
    work(env, factory)
    assert deliveries(env)[0].status == "delivered" and len(cloud.requests) == 1


def test_an_approval_expiring_within_two_hours_bypasses_quiet_hours(
    env: Env, cloud: Cloud, factory: sessionmaker[Session]
) -> None:
    link_owner(env)
    go_to_night(env)
    soon = (env.clock.now() + timedelta(minutes=90)).isoformat()
    later = (env.clock.now() + timedelta(hours=5)).isoformat()
    notify(env, "approval.requested", params={"expires_at": soon})
    notify(env, "approval.requested", params={"expires_at": later})
    work(env, factory)
    assert sorted(d.status for d in deliveries(env)) == ["delivered", "skipped_quiet_hours"]


# --- failures: retry, rejection, ambiguity -----------------------------------------------------

RATE_LIMITED = (429, {"error": {"message": "slow down", "code": 130429}})
SERVER_ERROR = (503, {"error": {"message": "unavailable", "code": 2}})
REJECTED = (400, {"error": {"message": "bad request", "code": 131047}})
NO_ID = (200, {"messaging_product": "whatsapp", "messages": []})


def test_a_rate_limit_is_retried_with_backoff_and_then_delivered(
    env: Env, cloud: Cloud, factory: sessionmaker[Session]
) -> None:
    link_owner(env)
    cloud.script = [RATE_LIMITED, OK]
    notify(env, "approval.requested")
    assert work(env, factory) == 1
    (delivery,) = deliveries(env)
    assert delivery.status == "pending" and delivery.attempt_count == 1
    assert delivery.last_error == "whatsapp_retryable:130429"
    assert delivery.delivery_metadata["send_state"] == "not_sent"
    assert work(env, factory) == 0  # backoff: not due yet

    env.clock.advance(seconds=40)
    assert work(env, factory) == 1
    (delivery,) = deliveries(env)
    assert delivery.status == "delivered" and delivery.attempt_count == 2
    assert delivery.last_error is None and delivery.delivery_metadata["send_state"] == "sent"
    assert len(cloud.requests) == 2 and [j.status for j in jobs(env)] == ["succeeded"]


def test_when_every_attempt_fails_the_delivery_fails_and_the_job_is_dead(
    env: Env, cloud: Cloud, factory: sessionmaker[Session]
) -> None:
    link_owner(env)
    cloud.default = SERVER_ERROR
    notify(env, "approval.requested")
    for _ in range(3):
        work(env, factory)
        env.clock.advance(minutes=5)
    (delivery,) = deliveries(env)
    assert delivery.status == "failed" and delivery.attempt_count == 3
    assert [j.status for j in jobs(env)] == ["dead"]  # visible, not silent
    assert len(cloud.requests) == 3


def test_a_rejected_message_fails_without_retry_and_without_provider_text(
    env: Env, cloud: Cloud, factory: sessionmaker[Session]
) -> None:
    link_owner(env, inbound_ago=timedelta(hours=1))
    cloud.default = REJECTED
    notify(env, "approval.requested")
    work(env, factory)
    env.clock.advance(minutes=10)
    work(env, factory)
    (delivery,) = deliveries(env)
    assert len(cloud.requests) == 1
    assert delivery.status == "failed" and delivery.last_error == "whatsapp_rejected:131047"
    assert "bad request" not in json.dumps(delivery.delivery_metadata)
    assert [j.status for j in jobs(env)] == ["succeeded"]


@pytest.mark.parametrize(
    "step",
    [httpx.ReadTimeout("timed out"), NO_ID],
    ids=["transport-timeout", "2xx-without-message-id"],
)
def test_an_ambiguous_send_is_failed_and_never_resent(
    env: Env, cloud: Cloud, factory: sessionmaker[Session], step: Any
) -> None:
    link_owner(env)
    cloud.script = [step]
    notify(env, "approval.requested")
    work(env, factory)
    for _ in range(3):  # any amount of waiting and worker ticks later...
        env.clock.advance(minutes=10)
        work(env, factory)
    (delivery,) = deliveries(env)
    assert len(cloud.requests) == 1  # ...the message is never sent again
    assert delivery.status == "failed" and delivery.last_error == "whatsapp_send_ambiguous"
    assert delivery.delivery_metadata["send_state"] == "ambiguous"
    assert delivery.delivery_metadata["ambiguous"] is True
    assert [j.status for j in jobs(env)] == ["succeeded"]


def test_a_stale_sending_marker_blocks_a_resend(
    env: Env, cloud: Cloud, factory: sessionmaker[Session]
) -> None:
    """The worker died after the provider call and before recording the outcome: the next attempt
    finds the marker and refuses to send again."""
    link_owner(env)
    notify(env, "approval.requested")
    (delivery,) = deliveries(env)
    delivery.delivery_metadata = {"send_state": "sending"}
    env.session.commit()
    work(env, factory)
    (delivery,) = deliveries(env)
    assert cloud.requests == []
    assert delivery.status == "failed" and delivery.last_error == "whatsapp_send_state_unknown"
    assert delivery.delivery_metadata["send_state"] == "ambiguous"


def test_the_access_token_never_reaches_the_ledger_or_the_logs(
    env: Env, cloud: Cloud, factory: sessionmaker[Session], caplog: pytest.LogCaptureFixture
) -> None:
    link_owner(env)
    cloud.default = (400, {"error": {"message": f"bad token {TOKEN}", "code": 190}})
    with caplog.at_level("DEBUG"):
        notify(env, "approval.requested")
        work(env, factory)
    (delivery,) = deliveries(env)
    assert TOKEN not in json.dumps(delivery.delivery_metadata) + (delivery.last_error or "")
    assert TOKEN not in caplog.text and WA_ID not in caplog.text


def test_a_user_who_left_the_workspace_is_not_messaged(
    env: Env, cloud: Cloud, factory: sessionmaker[Session]
) -> None:
    link_owner(env, role="manager", wa_id="905550000002")
    notify(env, "approval.requested", role="manager")
    from app.identity.models import WorkspaceMember

    member = env.session.scalar(
        select(WorkspaceMember).where(WorkspaceMember.user_id == env.manager.user.id)
    )
    assert member is not None
    env.session.delete(member)
    env.session.commit()
    work(env, factory)
    (delivery,) = deliveries(env)
    assert cloud.requests == []
    assert delivery.status == "failed" and delivery.last_error == "recipient_not_member_or_unlinked"


def test_an_unlinked_number_by_the_time_the_worker_runs_is_not_messaged(
    env: Env, cloud: Cloud, factory: sessionmaker[Session]
) -> None:
    link = link_owner(env)
    notify(env, "approval.requested")
    link.status = "unlinked"
    env.session.commit()
    work(env, factory)
    (delivery,) = deliveries(env)
    assert cloud.requests == [] and delivery.status == "failed"


def test_no_database_transaction_is_open_while_the_provider_is_called(
    env: Env, cloud: Cloud, wa_settings: Settings, factory: sessionmaker[Session]
) -> None:
    link = link_owner(env, inbound_ago=timedelta(hours=1))
    notification = notify(env, "approval.requested")
    session = factory()
    set_tenant_context(session, env.workspace.id)
    delivery = NotificationDelivery(
        workspace_id=env.workspace.id,
        notification_id=notification.id,
        recipient_user_id=env.owner.user.id,
        channel="whatsapp",
        channel_link_id=link.id,
        status="pending",
    )
    session.add(delivery)
    session.commit()
    cloud.in_transaction = session.in_transaction
    channel = WhatsAppChannel(client=make_client(cloud), settings=wa_settings)
    result = channel.deliver_notification(
        session,
        env.clock,
        delivery,
        ChannelRecipient(
            user_id=env.owner.user.id,
            workspace_id=env.workspace.id,
            channel="whatsapp",
            channel_user_id=WA_ID,
            channel_chat_id=WA_ID,
            ui_locale="tr",
            timezone="Europe/Istanbul",
        ),
    )
    session.close()
    assert result.success and cloud.seen_in_transaction == [False]


# --- the webhook: window and provider status ---------------------------------------------------


def incoming(
    kind: str = "text", message_id: str = "in1", sender: str = WA_ID, ts: int | None = None
) -> dict[str, Any]:
    message: dict[str, Any] = {"id": message_id, "from": sender, "type": kind}
    if kind == "text":
        message["text"] = {"body": "hello"}
    if ts is not None:
        message["timestamp"] = str(ts)
    return envelope([message])


def run_webhook(env: Env, wa_settings: Settings, cloud: Cloud, payload: dict[str, Any]) -> None:
    process_webhook(env.session, env.clock, payload, make_client(cloud), wa_settings)


def refreshed_link(env: Env) -> ChannelLink:
    set_tenant_context(env.session, env.workspace.id)
    env.session.expire_all()
    link = env.session.scalar(select(ChannelLink).where(ChannelLink.channel == "whatsapp"))
    assert link is not None
    return link


def test_a_text_from_a_linked_owner_opens_the_window_and_it_only_moves_forward(
    env: Env, wa_settings: Settings, cloud: Cloud
) -> None:
    link_owner(env, inbound_ago=None)
    stamp = int(env.clock.now().timestamp()) - 600
    run_webhook(env, wa_settings, cloud, incoming(ts=stamp, message_id="a"))
    first = refreshed_link(env).last_inbound_at
    assert first is not None and int(first.timestamp()) == stamp
    # An older message (a late retry) never moves it back; a newer one moves it forward.
    run_webhook(env, wa_settings, cloud, incoming(ts=stamp - 3600, message_id="b"))
    assert refreshed_link(env).last_inbound_at == first
    run_webhook(env, wa_settings, cloud, incoming(ts=stamp + 60, message_id="c"))
    assert refreshed_link(env).last_inbound_at is not None
    assert int(refreshed_link(env).last_inbound_at.timestamp()) == stamp + 60  # type: ignore[union-attr]


def test_a_button_tap_or_any_other_message_also_opens_the_window(
    env: Env, wa_settings: Settings, cloud: Cloud
) -> None:
    link_owner(env, inbound_ago=None)
    run_webhook(env, wa_settings, cloud, incoming(kind="image", message_id="img"))
    assert refreshed_link(env).last_inbound_at == env.clock.now()


def test_a_future_message_timestamp_is_not_trusted(
    env: Env, wa_settings: Settings, cloud: Cloud
) -> None:
    link_owner(env, inbound_ago=None)
    future = int(env.clock.now().timestamp()) + 86400
    run_webhook(env, wa_settings, cloud, incoming(ts=future))
    assert refreshed_link(env).last_inbound_at == env.clock.now()


def test_a_message_from_an_unknown_number_changes_nothing(
    env: Env, wa_settings: Settings, cloud: Cloud
) -> None:
    link_owner(env, inbound_ago=None)
    run_webhook(env, wa_settings, cloud, incoming(sender="905559999999"))
    assert refreshed_link(env).last_inbound_at is None
    assert cloud.requests == []  # an unknown sender is not answered


def test_the_owner_writing_after_the_window_closed_switches_back_to_session_messages(
    env: Env, wa_settings: Settings, cloud: Cloud, factory: sessionmaker[Session]
) -> None:
    link_owner(env, inbound_ago=timedelta(hours=40))
    notify(env, "approval.requested")
    work(env, factory)
    assert cloud.kinds == ["template"]
    run_webhook(env, wa_settings, cloud, incoming(message_id="wake"))
    cloud.requests.clear()  # forget the fixed "open the app" reply the webhook sent
    notify(env, "reply.failed")
    work(env, factory)
    assert cloud.kinds == ["text"]


def status_event(status: str, pricing: dict[str, Any] | None = None) -> dict[str, Any]:
    entry: dict[str, Any] = {"id": "wamid.OUT1", "recipient_id": WA_ID, "status": status}
    if pricing is not None:
        entry["pricing"] = pricing
    return envelope([], [entry])


def test_status_webhooks_record_the_providers_status_and_billing_flags(
    env: Env, wa_settings: Settings, cloud: Cloud, factory: sessionmaker[Session]
) -> None:
    link_owner(env)
    notify(env, "approval.requested")
    work(env, factory)
    run_webhook(env, wa_settings, cloud, status_event("sent"))
    run_webhook(
        env,
        wa_settings,
        cloud,
        status_event(
            "delivered",
            {
                "billable": True,
                "pricing_model": "PMP",
                "category": "service",
                "type": "regular",
                "amount": 99,
            },
        ),
    )
    (delivery,) = deliveries(env)
    meta = delivery.delivery_metadata
    assert delivery.status == "delivered" and meta["provider_status"] == "delivered"
    assert meta["billing"] == {
        "billable": True,
        "pricing_model": "PMP",
        "category": "service",
        "type": "regular",
    }
    assert meta["cost"]["price_amount"] is None  # an amount is never stored


def test_a_failed_status_marks_the_delivery_failed(
    env: Env, wa_settings: Settings, cloud: Cloud, factory: sessionmaker[Session]
) -> None:
    link_owner(env)
    notify(env, "approval.requested")
    work(env, factory)
    run_webhook(env, wa_settings, cloud, status_event("failed"))
    (delivery,) = deliveries(env)
    assert delivery.status == "failed" and delivery.last_error == "whatsapp_status_failed"
    assert len(cloud.requests) == 1  # and nothing is re-sent because of it


def test_a_status_for_an_unknown_message_is_ignored(
    env: Env, wa_settings: Settings, cloud: Cloud
) -> None:
    link_owner(env)
    run_webhook(env, wa_settings, cloud, status_event("delivered", {"billable": True}))
    assert deliveries(env) == []
