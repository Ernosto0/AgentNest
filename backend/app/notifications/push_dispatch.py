"""Hand a new notification to the Web Push owner channel (F-01 part 2).

``notify`` calls this inside the caller's transaction. When the type is pushable, push is
configured, the recipient opted into the type's category and has at least one active device, a
``notification_deliveries`` ledger row is written (status from the quiet-hours policy) and, if the
policy says deliver now, a ``deliver_channel_notification`` job is enqueued in the same
transaction. Nothing is sent here: the job sends outside any transaction.

This never raises into ``notify``: a problem in the push path is logged and rolled back to a
savepoint, so the in-app notification and the state change that caused it are never lost.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import Clock
from app.core.config import get_settings
from app.core.context import WorkspaceContext
from app.core.logging import get_logger
from app.integrations.channels.base import ChannelRecipient
from app.notifications import push_preferences
from app.notifications.catalog import PUSH_TYPES
from app.notifications.delivery_ledger import dispatch_channel_notification
from app.notifications.models import Notification, NotificationDelivery, PushSubscription

_log = get_logger("app.notifications.push_dispatch")

WEB_PUSH_CHANNEL = "web_push"


def has_active_device(session: Session, workspace_id: uuid.UUID, user_id: uuid.UUID) -> bool:
    return (
        session.scalar(
            select(PushSubscription.id)
            .where(
                PushSubscription.workspace_id == workspace_id,
                PushSubscription.user_id == user_id,
                PushSubscription.revoked_at.is_(None),
            )
            .limit(1)
        )
        is not None
    )


def dispatch_web_push(
    session: Session,
    clock: Clock,
    ctx: WorkspaceContext,
    notification: Notification,
) -> NotificationDelivery | None:
    """Record and enqueue the push for ``notification`` when it applies; else do nothing."""
    category = PUSH_TYPES.get(notification.type)
    if category is None or not get_settings().web_push_enabled:
        return None
    try:
        with session.begin_nested():
            workspace_id = notification.workspace_id
            user_id = notification.recipient_user_id
            if not push_preferences.is_enabled(session, workspace_id, user_id, category):
                return None
            if not has_active_device(session, workspace_id, user_id):
                return None
            recipient = ChannelRecipient(
                user_id=user_id,
                workspace_id=workspace_id,
                channel=WEB_PUSH_CHANNEL,
                timezone=ctx.timezone,
            )
            return dispatch_channel_notification(
                session,
                clock,
                workspace_id=workspace_id,
                notification=notification,
                recipient=recipient,
                channel=WEB_PUSH_CHANNEL,
            )
    except Exception:
        _log.exception(
            "web_push_dispatch_failed",
            notification_id=str(notification.id),
            notification_type=notification.type,
        )
        return None
