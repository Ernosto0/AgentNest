"""Hand a new notification to the WhatsApp owner channel (F-06, Feature Phase 5, Session 02).

``notify`` calls this inside the caller's transaction, after Web Push. When the type is one WhatsApp
carries (``catalog.WHATSAPP_TYPES``: the Web Push types plus the daily summary), WhatsApp is
configured and the recipient has an **active WhatsApp link**, a ``notification_deliveries`` ledger
row is written (status from the quiet-hours policy) and, if the policy says deliver now, a
``deliver_channel_notification`` job is enqueued in the same transaction. Nothing is sent here; the
job sends outside any transaction, and chooses template or session from the 24-hour window at send
time.

An owner without a WhatsApp link gets nothing recorded. Simulated notifications are never sent to
WhatsApp. This never raises into ``notify``: a problem here is logged and rolled back to a
savepoint, so the in-app notification and the state change that caused it are never lost.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import Clock
from app.core.config import get_settings
from app.core.context import WorkspaceContext
from app.core.logging import get_logger
from app.identity.channels import is_channel_enabled
from app.identity.models import ChannelLink
from app.integrations.channels.base import ChannelRecipient
from app.notifications.catalog import WHATSAPP_TYPES
from app.notifications.delivery_ledger import dispatch_channel_notification
from app.notifications.models import Notification, NotificationDelivery

_log = get_logger("app.notifications.whatsapp_dispatch")

WHATSAPP_CHANNEL = "whatsapp"


def dispatch_whatsapp(
    session: Session,
    clock: Clock,
    ctx: WorkspaceContext,
    notification: Notification,
) -> NotificationDelivery | None:
    """Record and enqueue the WhatsApp message for ``notification`` when it applies."""
    if notification.type not in WHATSAPP_TYPES or notification.is_simulated:
        return None
    if not get_settings().whatsapp_configured:
        return None
    try:
        with session.begin_nested():
            if not is_channel_enabled(
                session,
                notification.workspace_id,
                notification.recipient_user_id,
                WHATSAPP_CHANNEL,
            ):
                return None
            link = session.scalar(
                select(ChannelLink).where(
                    ChannelLink.workspace_id == notification.workspace_id,
                    ChannelLink.user_id == notification.recipient_user_id,
                    ChannelLink.channel == WHATSAPP_CHANNEL,
                    ChannelLink.status == "active",
                )
            )
            if link is None:
                return None
            recipient = ChannelRecipient(
                user_id=notification.recipient_user_id,
                workspace_id=notification.workspace_id,
                channel=WHATSAPP_CHANNEL,
                channel_user_id=link.channel_user_id,
                channel_chat_id=link.channel_chat_id,
                timezone=ctx.timezone,
            )
            return dispatch_channel_notification(
                session,
                clock,
                workspace_id=notification.workspace_id,
                notification=notification,
                recipient=recipient,
                channel=WHATSAPP_CHANNEL,
                channel_link_id=link.id,
            )
    except Exception:
        _log.exception(
            "whatsapp_dispatch_failed",
            notification_id=str(notification.id),
            notification_type=notification.type,
        )
        return None
