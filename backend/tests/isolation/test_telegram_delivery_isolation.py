"""Isolation of Telegram delivery state (INV-01, Session 01).

Proves:
- TelegramChannel refuses a ChannelLink that belongs to another workspace or another user.
- TelegramChannel refuses a Notification that belongs to another workspace or another user.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import httpx
import pytest
from sqlalchemy.orm import Session

from app.core.clock import FrozenClock
from app.core.db import set_tenant_context
from app.identity.models import ChannelLink
from app.integrations.channels.base import ChannelRecipient
from app.integrations.channels.telegram import TelegramChannel, TelegramClient
from app.notifications.models import Notification, NotificationDelivery
from tests.factories import workspace_with_members

NOW = datetime(2026, 11, 19, 12, 0, tzinfo=UTC)
A_CHAT, B_CHAT = "7770011", "7770022"


@pytest.mark.invariant("INV-01")
def test_telegram_adapter_refuses_link_or_notification_of_another_workspace_or_user(
    db_session: Session,
) -> None:
    ws_a, users_a = workspace_with_members(db_session, name="TG Isolation A")
    ws_b, users_b = workspace_with_members(db_session, name="TG Isolation B")
    owner_a, owner_b = users_a["owner"], users_b["owner"]

    set_tenant_context(db_session, ws_a.id)
    link_a = ChannelLink(
        workspace_id=ws_a.id,
        user_id=owner_a.id,
        channel="telegram",
        channel_user_id=A_CHAT,
        channel_chat_id=A_CHAT,
        status="active",
        linked_at=NOW,
    )
    notif_a = Notification(
        id=uuid.uuid4(),
        workspace_id=ws_a.id,
        recipient_user_id=owner_a.id,
        type="reply.failed",
        severity="attention",
        params={},
        created_at=NOW,
        updated_at=NOW,
    )
    db_session.add_all([link_a, notif_a])
    db_session.flush()
    delivery_a = NotificationDelivery(
        workspace_id=ws_a.id,
        notification_id=notif_a.id,
        recipient_user_id=owner_a.id,
        channel="telegram",
        channel_link_id=link_a.id,
        status="pending",
    )
    db_session.add(delivery_a)
    db_session.flush()

    set_tenant_context(db_session, ws_b.id)
    link_b = ChannelLink(
        workspace_id=ws_b.id,
        user_id=owner_b.id,
        channel="telegram",
        channel_user_id=B_CHAT,
        channel_chat_id=B_CHAT,
        status="active",
        linked_at=NOW,
    )
    db_session.add(link_b)
    db_session.commit()

    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json={"ok": True, "result": {"message_id": 101}})

    channel = TelegramChannel(
        client=TelegramClient(token="TEST_TOKEN", transport=httpx.MockTransport(handler))
    )
    clock = FrozenClock(NOW)

    # 1. Tampered link pointing to Workspace B's link
    set_tenant_context(db_session, ws_a.id)
    delivery_a.channel_link_id = link_b.id
    db_session.flush()
    recipient_a = ChannelRecipient(
        user_id=owner_a.id,
        workspace_id=ws_a.id,
        channel="telegram",
        channel_user_id=B_CHAT,
        channel_chat_id=B_CHAT,
    )
    res_1 = channel.deliver_notification(db_session, clock, delivery_a, recipient_a)
    assert not res_1.success and res_1.error_message == "recipient_not_linked"
    assert calls == []

    # 2. Right workspace link, wrong user recipient
    delivery_a.channel_link_id = link_a.id
    db_session.flush()
    stranger = ChannelRecipient(
        user_id=owner_b.id,
        workspace_id=ws_a.id,
        channel="telegram",
        channel_user_id=A_CHAT,
        channel_chat_id=A_CHAT,
    )
    res_2 = channel.deliver_notification(db_session, clock, delivery_a, stranger)
    assert not res_2.success and res_2.error_message in {
        "notification_not_found",
        "recipient_not_linked",
    }
    assert calls == []
