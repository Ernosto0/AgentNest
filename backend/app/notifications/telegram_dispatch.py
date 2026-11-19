"""Hand a new notification to the Telegram owner channel (ADR-012, Session 01).

``notify`` calls this inside the caller's transaction, alongside Web Push and WhatsApp. When the
type is one Telegram carries (``catalog.TELEGRAM_TYPES``: approvals, owner questions, operational
failures, quota warnings and existing report-ready notifications) and the recipient is an active
workspace member with an **active Telegram link**, a ``notification_deliveries`` ledger row is
written (status from the quiet-hours policy) and, if the policy says deliver now, a
``deliver_channel_notification`` job is enqueued in the same transaction. Nothing is sent here; the
job sends outside any transaction.

An owner without an active Telegram link gets nothing recorded. Simulated notifications are never
dispatched to Telegram. This never raises into ``notify``: a problem here is logged and rolled back
to a savepoint, so the in-app notification and the state change that caused it are never lost.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import Clock
from app.core.context import WorkspaceContext
from app.core.logging import get_logger
from app.identity.channels import is_channel_enabled
from app.identity.models import ChannelLink, User, WorkspaceMember
from app.integrations.channels.base import ChannelRecipient
from app.notifications.catalog import TELEGRAM_TYPES
from app.notifications.delivery_ledger import dispatch_channel_notification
from app.notifications.models import Notification, NotificationDelivery

_log = get_logger("app.notifications.telegram_dispatch")

TELEGRAM_CHANNEL = "telegram"


def dispatch_telegram(
    session: Session,
    clock: Clock,
    ctx: WorkspaceContext,
    notification: Notification,
) -> NotificationDelivery | None:
    """Record and enqueue the Telegram message for ``notification`` when it applies."""
    if notification.type not in TELEGRAM_TYPES or notification.is_simulated:
        return None
    try:
        with session.begin_nested():
            user = session.get(User, notification.recipient_user_id)
            member = session.scalar(
                select(WorkspaceMember).where(
                    WorkspaceMember.workspace_id == notification.workspace_id,
                    WorkspaceMember.user_id == notification.recipient_user_id,
                )
            )
            if user is None or not user.is_active or member is None:
                return None
            if not is_channel_enabled(
                session,
                notification.workspace_id,
                notification.recipient_user_id,
                TELEGRAM_CHANNEL,
            ):
                return None
            link = session.scalar(
                select(ChannelLink).where(
                    ChannelLink.workspace_id == notification.workspace_id,
                    ChannelLink.user_id == notification.recipient_user_id,
                    ChannelLink.channel == TELEGRAM_CHANNEL,
                    ChannelLink.status == "active",
                )
            )
            if link is None or not (link.channel_chat_id or link.channel_user_id):
                return None
            recipient = ChannelRecipient(
                user_id=notification.recipient_user_id,
                workspace_id=notification.workspace_id,
                channel=TELEGRAM_CHANNEL,
                channel_user_id=link.channel_user_id,
                channel_chat_id=link.channel_chat_id,
                channel_username=link.channel_username,
                ui_locale=user.ui_locale or ctx.locale,
                timezone=ctx.timezone,
            )
            return dispatch_channel_notification(
                session,
                clock,
                workspace_id=notification.workspace_id,
                notification=notification,
                recipient=recipient,
                channel=TELEGRAM_CHANNEL,
                channel_link_id=link.id,
            )
    except Exception:
        _log.exception(
            "telegram_dispatch_failed",
            notification_id=str(notification.id),
            notification_type=notification.type,
        )
        return None
