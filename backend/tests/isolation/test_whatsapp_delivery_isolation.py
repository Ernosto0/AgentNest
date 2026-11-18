"""Isolation of WhatsApp delivery state (INV-01, Feature Phase 5 Session 02).

Proves: the delivery metadata and the window anchor are tenant-scoped under the runtime role; the
adapter refuses a link that belongs to another workspace or another user; and a webhook for one
workspace's number can neither move another workspace's window nor write to its delivery rows.
"""

from __future__ import annotations

import contextlib
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest
from pydantic import SecretStr
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core.clock import FrozenClock
from app.core.config import Settings
from app.core.db import clear_tenant_context, set_tenant_context
from app.identity.models import ChannelLink
from app.integrations.channels.base import ChannelRecipient
from app.integrations.channels.whatsapp.adapter import WhatsAppChannel
from app.integrations.channels.whatsapp.client import WhatsAppClient
from app.integrations.channels.whatsapp.dispatcher import process_webhook
from app.notifications.models import Notification, NotificationDelivery
from tests.factories import workspace_with_members
from tests.helpers.roles import ensure_runtime_roles
from tests.unit.integrations.channels.test_whatsapp_webhook_format import envelope

NOW = datetime(2026, 11, 18, 12, 0, tzinfo=UTC)
A_NUMBER, B_NUMBER = "905550000011", "905550000022"


@contextlib.contextmanager
def as_role(session: Session, role: str) -> Iterator[None]:
    ensure_runtime_roles(session)
    session.execute(text(f"SET LOCAL ROLE {role}"))
    session.execute(text("SET LOCAL search_path = public, pg_temp"))
    try:
        yield
    finally:
        session.execute(text("RESET ROLE"))


class World:
    """Two workspaces, each with an owner, a linked WhatsApp number and one delivery."""

    def __init__(self, session: Session) -> None:
        self.session = session
        self.ws_a, users_a = workspace_with_members(session, name="WA Isolation A")
        self.ws_b, users_b = workspace_with_members(session, name="WA Isolation B")
        self.owner_a, self.owner_b = users_a["owner"], users_b["owner"]
        self.link_a = self._link(self.ws_a.id, self.owner_a.id, A_NUMBER)
        self.link_b = self._link(self.ws_b.id, self.owner_b.id, B_NUMBER)
        self.delivery_a = self._delivery(self.ws_a.id, self.owner_a.id, self.link_a, "wamid.A")
        self.delivery_b = self._delivery(self.ws_b.id, self.owner_b.id, self.link_b, "wamid.B")
        session.commit()

    def _link(self, workspace_id: uuid.UUID, user_id: uuid.UUID, number: str) -> ChannelLink:
        set_tenant_context(self.session, workspace_id)
        link = ChannelLink(
            workspace_id=workspace_id,
            user_id=user_id,
            channel="whatsapp",
            channel_user_id=number,
            channel_chat_id=number,
            status="active",
            linked_at=NOW,
        )
        self.session.add(link)
        self.session.flush()
        return link

    def _delivery(
        self, workspace_id: uuid.UUID, user_id: uuid.UUID, link: ChannelLink, wamid: str
    ) -> NotificationDelivery:
        set_tenant_context(self.session, workspace_id)
        notification = Notification(
            id=uuid.uuid4(),
            workspace_id=workspace_id,
            recipient_user_id=user_id,
            type="approval.requested",
            severity="attention",
            params={},
            created_at=NOW,
            updated_at=NOW,
        )
        self.session.add(notification)
        self.session.flush()
        delivery = NotificationDelivery(
            workspace_id=workspace_id,
            notification_id=notification.id,
            recipient_user_id=user_id,
            channel="whatsapp",
            channel_link_id=link.id,
            status="delivered",
            delivery_metadata={"wamid": wamid, "send_state": "sent"},
        )
        self.session.add(delivery)
        self.session.flush()
        return delivery


@pytest.fixture
def world(db_session: Session) -> World:
    return World(db_session)


@pytest.fixture
def wa_settings(settings: Settings) -> Settings:
    return settings.model_copy(
        update={
            "whatsapp_access_token": SecretStr("synthetic-token"),
            "whatsapp_app_secret": SecretStr("synthetic-secret"),
            "whatsapp_webhook_verify_token": SecretStr("verify"),
            "whatsapp_phone_number_id": "123",
            "whatsapp_display_phone_number": "905551112233",
            "whatsapp_templates_approved": True,
        }
    )


def client_with(handler: Any) -> WhatsAppClient:
    return WhatsAppClient(
        access_token=SecretStr("synthetic-token"),
        phone_number_id="123",
        transport=httpx.MockTransport(handler),
    )


def ok(_: httpx.Request) -> httpx.Response:
    return httpx.Response(200, json={"messages": [{"id": "wamid.X"}]})


@pytest.mark.invariant("INV-01")
def test_delivery_metadata_and_the_window_anchor_are_tenant_scoped(
    world: World, db_session: Session
) -> None:
    set_tenant_context(db_session, world.ws_a.id)
    with as_role(db_session, "agentnest_app"):
        wamids = db_session.scalars(
            select(NotificationDelivery.delivery_metadata["wamid"].astext)
        ).all()
        links = db_session.scalars(select(ChannelLink.channel_user_id)).all()
    assert wamids == ["wamid.A"] and links == [A_NUMBER]
    # B's wamid is invisible to A even when asked for by value.
    with as_role(db_session, "agentnest_app"):
        found = db_session.scalars(
            select(NotificationDelivery.id).where(
                NotificationDelivery.delivery_metadata["wamid"].astext == "wamid.B"
            )
        ).all()
    assert found == []
    clear_tenant_context(db_session)
    with as_role(db_session, "agentnest_app"):
        assert db_session.scalars(select(NotificationDelivery.id)).all() == []


@pytest.mark.invariant("INV-01")
def test_the_adapter_refuses_a_link_of_another_workspace_or_user(
    world: World, db_session: Session, wa_settings: Settings
) -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return ok(request)

    channel = WhatsAppChannel(client=client_with(handler), settings=wa_settings)
    clock = FrozenClock(NOW)
    set_tenant_context(db_session, world.ws_a.id)
    own = db_session.get(NotificationDelivery, world.delivery_a.id)
    assert own is not None
    own.delivery_metadata = {}
    own.channel_link_id = world.link_b.id  # a link of workspace B (tampered or stale pointer)
    db_session.flush()
    recipient = ChannelRecipient(
        user_id=world.owner_a.id,
        workspace_id=world.ws_a.id,
        channel="whatsapp",
        channel_user_id=B_NUMBER,
        channel_chat_id=B_NUMBER,
    )
    result = channel.deliver_notification(db_session, clock, own, recipient)
    assert not result.success and result.error_message == "recipient_not_linked"
    assert calls == []

    # The right workspace but another user's link is refused too.
    other = db_session.get(NotificationDelivery, world.delivery_a.id)
    assert other is not None
    other.channel_link_id = world.link_a.id
    db_session.flush()
    stranger = ChannelRecipient(
        user_id=world.owner_b.id,
        workspace_id=world.ws_a.id,
        channel="whatsapp",
        channel_user_id=A_NUMBER,
        channel_chat_id=A_NUMBER,
    )
    result = channel.deliver_notification(db_session, clock, other, stranger)
    assert not result.success and result.error_message in {
        "notification_not_found",
        "recipient_not_linked",
    }
    assert calls == []


@pytest.mark.invariant("INV-01")
def test_a_webhook_for_one_number_never_touches_another_workspace(
    world: World, db_session: Session, wa_settings: Settings
) -> None:
    clock = FrozenClock(NOW)
    client = client_with(ok)
    # B's number writes: only B's window opens.
    msg = envelope([{"id": "b-in", "from": B_NUMBER, "type": "image"}])
    process_webhook(db_session, clock, msg, client, wa_settings)
    # A status about A's wamid, reported for B's number, must not change A's delivery.
    status = envelope([], [{"id": "wamid.A", "recipient_id": B_NUMBER, "status": "failed"}])
    process_webhook(db_session, clock, status, client, wa_settings)

    db_session.expire_all()
    set_tenant_context(db_session, world.ws_a.id)
    link_a = db_session.get(ChannelLink, world.link_a.id)
    delivery_a = db_session.get(NotificationDelivery, world.delivery_a.id)
    assert link_a is not None and link_a.last_inbound_at is None
    assert delivery_a is not None and delivery_a.status == "delivered"
    assert "provider_status" not in delivery_a.delivery_metadata
    set_tenant_context(db_session, world.ws_b.id)
    link_b = db_session.get(ChannelLink, world.link_b.id)
    delivery_b = db_session.get(NotificationDelivery, world.delivery_b.id)
    assert link_b is not None and link_b.last_inbound_at == NOW
    assert delivery_b is not None and delivery_b.status == "delivered"
    assert "provider_status" not in delivery_b.delivery_metadata
