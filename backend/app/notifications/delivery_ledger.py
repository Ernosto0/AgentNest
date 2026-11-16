"""The delivery ledger entry point: policy decision, ``notification_deliveries`` row, job.

Split from ``jobs`` so that ``notifications.service`` can record a delivery without importing the
channel registry (and with it every channel adapter). Nothing here sends anything; the
``deliver_channel_notification`` job in ``jobs`` does, outside any transaction.
"""

from __future__ import annotations

import uuid

from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.clock import Clock
from app.integrations.channels.base import ChannelRecipient
from app.jobs.queue import enqueue
from app.notifications.delivery_policy import evaluate_delivery_policy
from app.notifications.models import Notification, NotificationDelivery


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
