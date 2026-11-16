"""Web Push OwnerChannel adapter (ADR-012, F-01 part 2).

``deliver_notification`` is called by the ``deliver_channel_notification`` job for one
``notification_deliveries`` row (the ledger), after the delivery policy (quiet hours, critical
bypass) decided to send. For one recipient it:

1. reads, in one short transaction: the notification, the recipient's membership, their opt-in for
   the type's category and their active devices (the decrypted keys are held in memory only);
2. **ends that transaction** (INV: no external call inside a DB transaction);
3. sends the same small payload to each device through ``sender`` (allowlist, public addresses,
   short timeout, no redirects);
4. in a second short transaction records the result: ``last_success_at`` for a device that
   accepted the push, ``revoked_at`` (and an audit entry) for one the push service answered 404 or
   410 for, or whose endpoint can never be allowed.

Result for the job: delivered if at least one device accepted the push; a ``retryable`` failure if
no device accepted and at least one hit a transient error (5xx, 429, timeout, DNS: the job retries
with backoff); otherwise a ``terminal`` failure (nothing deliverable, opted out, no longer a
member). Devices that already accepted a push are pushed again on a retry; the shared ``tag``
makes the device replace the earlier notification instead of stacking a second one.

Neither the endpoint URL nor any key is ever logged; log lines carry the subscription id.
"""

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit import service as audit_service
from app.core.clock import Clock
from app.core.config import Settings, get_settings
from app.core.context import ActorRef
from app.core.logging import get_logger
from app.identity.models import User, WorkspaceMember
from app.integrations.channels.base import ChannelRecipient, DeliveryResult, OwnerChannel
from app.integrations.channels.web_push.payloads import build_payload
from app.integrations.channels.web_push.sender import SendOutcome, send_web_push
from app.notifications import push_preferences, push_subscriptions
from app.notifications.catalog import PUSH_TYPES
from app.notifications.models import (
    Notification,
    NotificationDelivery,
    PushSubscription,
)

_log = get_logger("app.integrations.channels.web_push")

# How long a push service may hold the message for an offline device. Approvals and questions are
# decided in the app within hours; a push that old would only confuse.
TTL_SECONDS = 3600

Sender = Callable[..., SendOutcome]


@dataclass(frozen=True)
class _Target:
    subscription_id: uuid.UUID
    endpoint: str
    p256dh: str
    auth: str


def _terminal(reason: str, **metadata: Any) -> DeliveryResult:
    return DeliveryResult(
        success=False,
        status="failed",
        error_message=reason,
        metadata={"terminal": True, **metadata},
    )


class WebPushChannel(OwnerChannel):
    """Owner channel that pushes to a user's registered browsers and phones."""

    name: str = "web_push"

    def __init__(self, sender: Sender | None = None, settings: Settings | None = None) -> None:
        self._sender: Sender = sender or send_web_push
        self._settings = settings

    @property
    def settings(self) -> Settings:
        return self._settings or get_settings()

    def deliver_notification(
        self,
        session: Session,
        clock: Clock,
        delivery: NotificationDelivery,
        recipient: ChannelRecipient,
    ) -> DeliveryResult:
        settings = self.settings
        if not settings.web_push_enabled:
            return _terminal("web_push_not_configured")
        try:
            return self._deliver(session, clock, settings, delivery, recipient)
        except Exception:
            # Never put an exception text in the ledger or the log: it could carry a URL.
            _log.error("web_push_delivery_error", delivery_id=str(delivery.id))
            return _terminal("web_push_internal_error")

    def _deliver(
        self,
        session: Session,
        clock: Clock,
        settings: Settings,
        delivery: NotificationDelivery,
        recipient: ChannelRecipient,
    ) -> DeliveryResult:
        workspace_id = delivery.workspace_id
        delivery_id = delivery.id
        notification = session.get(Notification, delivery.notification_id)
        if (
            notification is None
            or notification.workspace_id != workspace_id
            or notification.recipient_user_id != recipient.user_id
        ):
            return _terminal("notification_not_found")
        category = PUSH_TYPES.get(notification.type)
        if category is None:
            return _terminal("notification_type_not_pushable")

        # A device is skipped, and the delivery fails, when its user is no longer an active member.
        user = session.get(User, recipient.user_id)
        member = session.scalar(
            select(WorkspaceMember).where(
                WorkspaceMember.workspace_id == workspace_id,
                WorkspaceMember.user_id == recipient.user_id,
            )
        )
        if user is None or not user.is_active or member is None:
            return _terminal("recipient_not_member")
        if not push_preferences.is_enabled(session, workspace_id, recipient.user_id, category):
            return _terminal("not_opted_in")

        rows = list(
            session.scalars(
                select(PushSubscription).where(
                    PushSubscription.workspace_id == workspace_id,
                    PushSubscription.user_id == recipient.user_id,
                    PushSubscription.revoked_at.is_(None),
                )
            )
        )
        targets: list[_Target] = []
        undecryptable: list[uuid.UUID] = []
        for row in rows:
            try:
                p256dh, auth = push_subscriptions.decrypt_keys(settings, row)
            except Exception:
                undecryptable.append(row.id)
                continue
            targets.append(_Target(row.id, row.endpoint, p256dh, auth))
        if not targets:
            return _terminal("no_active_device")

        payload = build_payload(notification, recipient.ui_locale)
        body = payload.to_json()
        urgency = "high" if notification.severity == "critical" else "normal"
        vapid_private_key = settings.web_push_vapid_private_key.get_secret_value().strip()
        vapid_subject = settings.web_push_subject.strip()

        # No transaction may be open while we talk to a push service.
        session.rollback()

        outcomes: dict[uuid.UUID, SendOutcome] = {}
        for target in targets:
            outcomes[target.subscription_id] = self._sender(
                endpoint=target.endpoint,
                p256dh=target.p256dh,
                auth=target.auth,
                payload=body,
                vapid_private_key=vapid_private_key,
                vapid_subject=vapid_subject,
                ttl=TTL_SECONDS,
                urgency=urgency,
            )

        self._record(session, clock, workspace_id, recipient.user_id, outcomes)
        return self._result(clock, delivery_id, outcomes, len(undecryptable))

    def _record(
        self,
        session: Session,
        clock: Clock,
        workspace_id: uuid.UUID,
        user_id: uuid.UUID,
        outcomes: dict[uuid.UUID, SendOutcome],
    ) -> None:
        """Second short transaction: success timestamps and revocations."""
        now = clock.now()
        for subscription_id, outcome in outcomes.items():
            revoke = outcome.kind == "gone" or (outcome.kind == "refused" and outcome.permanent)
            if outcome.kind != "sent" and not revoke:
                _log.warning(
                    "web_push_not_delivered",
                    subscription_id=str(subscription_id),
                    kind=outcome.kind,
                    reason=outcome.reason,
                    status=outcome.status_code,
                )
                continue
            row = session.scalar(
                select(PushSubscription)
                .where(
                    PushSubscription.workspace_id == workspace_id,
                    PushSubscription.id == subscription_id,
                )
                .with_for_update()
            )
            if row is None:
                continue
            if outcome.kind == "sent":
                row.last_success_at = now
                row.updated_at = now
            elif row.revoked_at is None:
                row.revoked_at = now
                row.updated_at = now
                audit_service.record(
                    session,
                    None,
                    "push_subscription.revoked",
                    "push_subscription",
                    row.id,
                    {"user_id": str(user_id), "reason": outcome.reason},
                    clock=clock,
                    actor=ActorRef.system("web_push"),
                    workspace_id=workspace_id,
                )
                _log.info(
                    "web_push_subscription_revoked",
                    subscription_id=str(subscription_id),
                    reason=outcome.reason,
                )
        session.commit()

    def _result(
        self,
        clock: Clock,
        delivery_id: uuid.UUID,
        outcomes: dict[uuid.UUID, SendOutcome],
        undecryptable: int,
    ) -> DeliveryResult:
        sent = sum(1 for o in outcomes.values() if o.kind == "sent")
        gone = sum(1 for o in outcomes.values() if o.kind == "gone")
        transient = sum(1 for o in outcomes.values() if o.kind == "retry")
        counts = {
            "devices": len(outcomes),
            "sent": sent,
            "revoked_gone": gone,
            "transient": transient,
            "undecryptable": undecryptable,
        }
        if sent:
            return DeliveryResult(
                success=True, status="delivered", delivered_at=clock.now(), metadata=counts
            )
        if transient:
            return DeliveryResult(
                success=False,
                status="failed",
                error_message="push_service_unavailable",
                metadata={"retryable": True, **counts},
            )
        reasons = sorted({o.reason for o in outcomes.values() if o.reason})
        return _terminal(reasons[0] if len(reasons) == 1 else "no_device_accepted", **counts)

    def render_command_result(
        self,
        session: Session,
        clock: Clock,
        command: Any,
        recipient: ChannelRecipient,
    ) -> None:
        """Web Push carries notifications only; command results are read in the app."""
        return None
