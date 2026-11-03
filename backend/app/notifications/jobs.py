"""Durable notification delivery job (ADR-012, Phase 9 Session 03).

Claims a pending NotificationDelivery record, resolves its channel via the channel registry,
dispatches the notification outside database transactions, and records the delivery outcome.
"""

from __future__ import annotations

import uuid

from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.clock import Clock
from app.core.db import set_tenant_context
from app.core.logging import get_logger
from app.identity.models import ChannelLink, User, Workspace
from app.integrations.channels.base import ChannelRecipient, DeliveryResult
from app.integrations.channels.registry import get_channel
from app.jobs.queue import enqueue
from app.jobs.registry import JobContext, job_handler
from app.notifications.delivery_policy import evaluate_delivery_policy
from app.notifications.models import (
    DELIVERY_STATUSES,
    Notification,
    NotificationDelivery,
)

_log = get_logger("app.notifications.jobs")


class DeliverChannelNotificationPayload(BaseModel):
    """Payload for external owner channel notification delivery."""

    delivery_id: uuid.UUID


def dispatch_channel_notification(
    session: Session,
    clock: Clock,
    *,
    workspace_id: uuid.UUID,
    notification: Notification,
    recipient: ChannelRecipient,
    channel: str = "telegram",
    channel_link_id: uuid.UUID | None = None,
    correlation_id: uuid.UUID | None = None,
) -> NotificationDelivery:
    """Evaluate delivery policy, record a delivery ledger entry, and enqueue if eligible."""
    decision = evaluate_delivery_policy(notification, recipient, clock, channel=channel)

    delivery = NotificationDelivery(
        workspace_id=workspace_id,
        notification_id=notification.id,
        recipient_user_id=recipient.user_id,
        channel=channel,
        channel_link_id=channel_link_id,
        status=decision.status,
        attempt_count=0,
    )
    session.add(delivery)
    session.flush()

    if decision.should_deliver:
        enqueue(
            session,
            "deliver_channel_notification",
            DeliverChannelNotificationPayload(delivery_id=delivery.id),
            workspace_id=workspace_id,
            correlation_id=correlation_id,
            clock=clock,
        )

    return delivery


@job_handler(
    "deliver_channel_notification",
    DeliverChannelNotificationPayload,
    max_attempts=3,
    backoff=(5, 30, 120),
)
def deliver_channel_notification(ctx: JobContext) -> None:
    """Durable delivery worker: claims row, delivers outside transaction, updates status."""
    payload = ctx.payload
    if not isinstance(payload, DeliverChannelNotificationPayload):
        return

    # 1. Claim delivery row in a short transaction
    with ctx.session_factory() as session:
        if ctx.workspace_id is not None:
            set_tenant_context(session, ctx.workspace_id)
        delivery = session.get(NotificationDelivery, payload.delivery_id, with_for_update=True)
        if delivery is None:
            _log.warning("delivery_not_found", delivery_id=str(payload.delivery_id))
            return
        if delivery.status != "pending":
            _log.info(
                "delivery_already_resolved",
                delivery_id=str(payload.delivery_id),
                status=delivery.status,
            )
            return

        delivery.attempt_count += 1
        delivery_id = delivery.id
        workspace_id = delivery.workspace_id
        recipient_user_id = delivery.recipient_user_id
        channel_name = delivery.channel
        channel_link_id = delivery.channel_link_id

        user = session.get(User, recipient_user_id)
        workspace = session.get(Workspace, workspace_id)
        link = session.get(ChannelLink, channel_link_id) if channel_link_id else None

        recipient = ChannelRecipient(
            user_id=recipient_user_id,
            workspace_id=workspace_id,
            channel=channel_name,
            channel_user_id=link.channel_user_id if link else None,
            channel_chat_id=link.channel_chat_id if link else None,
            channel_username=link.channel_username if link else None,
            ui_locale=user.ui_locale if user else (workspace.default_locale if workspace else "en"),
            timezone=workspace.timezone if workspace else "UTC",
        )
        session.commit()

    # 2. Outside transaction: resolve channel and deliver
    try:
        channel_adapter = get_channel(channel_name)
        with ctx.session_factory() as read_session:
            if ctx.workspace_id is not None:
                set_tenant_context(read_session, ctx.workspace_id)
            delivery_ref = read_session.get(NotificationDelivery, delivery_id)
            if delivery_ref is None:
                return
            result = channel_adapter.deliver_notification(
                read_session,
                ctx.clock,
                delivery_ref,
                recipient,
            )
    except Exception as exc:
        _log.exception(
            "channel_delivery_failed",
            delivery_id=str(delivery_id),
            channel=channel_name,
        )
        result = DeliveryResult(
            success=False,
            status="failed",
            error_message=str(exc),
        )

    # 3. Short transaction: record delivery result
    with ctx.session_factory() as session:
        if ctx.workspace_id is not None:
            set_tenant_context(session, ctx.workspace_id)
        delivery = session.get(NotificationDelivery, delivery_id, with_for_update=True)
        if delivery is None:
            return
        if result.success:
            delivery.status = result.status if result.status in DELIVERY_STATUSES else "delivered"
            delivery.sent_at = result.delivered_at or ctx.clock.now()
            delivery.last_error = None
        else:
            delivery.status = result.status if result.status in DELIVERY_STATUSES else "failed"
            delivery.last_error = result.error_message
        session.commit()

    if not result.success and result.status == "failed":
        raise RuntimeError(f"Channel delivery failed for {delivery_id}: {result.error_message}")
