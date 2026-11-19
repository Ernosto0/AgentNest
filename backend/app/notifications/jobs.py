"""Durable notification delivery job (ADR-012, Phase 9 Session 03).

Claims a pending NotificationDelivery record, resolves its channel via the channel registry,
dispatches the notification outside database transactions, and records the delivery outcome.
"""

from __future__ import annotations

from sqlalchemy import select

from app.core.db import set_tenant_context
from app.core.errors import RetryableError
from app.core.logging import get_logger
from app.identity.models import ChannelLink, User, Workspace, WorkspaceMember
from app.integrations.channels.base import ChannelRecipient, DeliveryResult
from app.integrations.channels.registry import get_channel
from app.jobs.registry import JobContext, job_handler
from app.notifications.delivery_ledger import (  # noqa: F401  (dispatch is re-exported)
    DeliverChannelNotificationPayload,
    dispatch_channel_notification,
)
from app.notifications.models import (
    DELIVERY_STATUSES,
    Notification,
    NotificationDelivery,
)

_log = get_logger("app.notifications.jobs")


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
        notification = session.get(Notification, delivery.notification_id)
        member = session.scalar(
            select(WorkspaceMember).where(
                WorkspaceMember.workspace_id == workspace_id,
                WorkspaceMember.user_id == recipient_user_id,
            )
        )
        link = session.get(ChannelLink, channel_link_id) if channel_link_id else None
        if (
            notification is None
            or notification.workspace_id != workspace_id
            or notification.recipient_user_id != recipient_user_id
        ):
            delivery.status = "failed"
            delivery.last_error = "notification_not_found"
            session.commit()
            return
        if notification.is_simulated and channel_name in ("telegram", "whatsapp"):
            delivery.status = "failed"
            delivery.last_error = "simulated_notification_not_sent"
            session.commit()
            return
        # Web and Web Push are tied to the user and their devices, not to a chat link.
        needs_link = channel_name not in ("web", "web_push")
        if (
            member is None
            or user is None
            or not user.is_active
            or (
                needs_link
                and (
                    link is None
                    or link.status != "active"
                    or link.workspace_id != workspace_id
                    or link.user_id != recipient_user_id
                    or link.channel != channel_name
                )
            )
        ):
            delivery.status = "failed"
            delivery.last_error = "recipient_not_member_or_unlinked"
            session.commit()
            return

        if channel_name in ("telegram", "whatsapp"):
            from app.identity.channels import is_channel_enabled

            if not is_channel_enabled(session, workspace_id, recipient_user_id, channel_name):
                delivery.status = "failed"
                delivery.last_error = "channel_disabled_by_preference"
                session.commit()
                return

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

    # 3. Short transaction: record delivery result. A channel marks a transient failure with
    # ``metadata["retryable"]`` and a failure that a retry cannot fix (nothing to send to, no
    # opt-in) with ``metadata["terminal"]``; Telegram sets neither, so it behaves as before.
    will_retry = (
        not result.success
        and bool(result.metadata.get("retryable"))
        and ctx.attempt < ctx.max_attempts
    )
    with ctx.session_factory() as session:
        if ctx.workspace_id is not None:
            set_tenant_context(session, ctx.workspace_id)
        delivery = session.get(NotificationDelivery, delivery_id, with_for_update=True)
        if delivery is None:
            return
        # Channel facts about the attempt (WhatsApp: send state, cost metadata, provider id) are
        # kept on the ledger row; the retry/terminal flags only steer this job.
        recorded = {
            key: value
            for key, value in result.metadata.items()
            if key not in ("retryable", "terminal")
        }
        if recorded:
            delivery.delivery_metadata = {**(delivery.delivery_metadata or {}), **recorded}
        if result.success:
            delivery.status = result.status if result.status in DELIVERY_STATUSES else "delivered"
            delivery.sent_at = result.delivered_at or ctx.clock.now()
            delivery.last_error = None
        elif will_retry:
            # A transient failure (push service 5xx, 429, timeout): the row stays pending so the
            # retry re-claims it; only the last attempt marks it failed.
            delivery.last_error = result.error_message
        else:
            delivery.status = result.status if result.status in DELIVERY_STATUSES else "failed"
            delivery.last_error = result.error_message
        session.commit()

    if not result.success and result.metadata.get("retryable"):
        # The worker retries with backoff and, on the last attempt, marks the job dead.
        raise RetryableError("CHANNEL_DELIVERY_RETRY", result.error_message)
    if not result.success and result.status == "failed" and not result.metadata.get("terminal"):
        raise RuntimeError(f"Channel delivery failed for {delivery_id}: {result.error_message}")
