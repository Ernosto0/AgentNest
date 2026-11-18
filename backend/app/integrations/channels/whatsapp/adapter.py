"""WhatsApp OwnerChannel adapter: notifications and the daily summary (ADR-027, Session 02).

``deliver_notification`` is called by the ``deliver_channel_notification`` job for one
``notification_deliveries`` row (the ledger), after the delivery policy (quiet hours, critical
bypass) decided to send. For one owner it:

1. reads, in one short transaction: the notification, the linked number and the time of the
   owner's last inbound message;
2. decides **template or session** from that time and the injected clock alone
   (``window.choose_send_mode``); outside the 24-hour window only an approved template is sent;
3. writes a ``send_state = "sending"`` marker on the ledger row and **commits** (no transaction is
   open during the HTTP call, INV: no external call inside a DB transaction);
4. sends once. No retry happens inside the adapter.

Outcomes for the job (it merges ``metadata`` into the ledger row's ``delivery_metadata``):

- accepted: delivered, with the provider message id (``wamid``) and the cost metadata;
- 429 or 5xx (the provider answered, nothing was accepted): ``retryable``, so the ledger retries
  with backoff;
- a transport failure, a 2xx without a message id or any unexpected error after the marker:
  **ambiguous**. The message may have been sent, so the delivery is failed terminally and is never
  re-sent automatically. A later attempt that finds the ``sending`` marker still on the row (the
  worker died between the send and the record) is treated the same way;
- any other rejection (4xx, an unapproved template, a missing variable): terminal failure.

Approval requests (Session 03): inside the window the message is an interactive **approve / reject
button** message whose button ids are single-use action tokens (``approval_buttons``); outside the
window it is the plain approval template, with no buttons (interactive buttons are session
messages only, and the template registry has no quick-reply button), and the text says to open the
app. An approval that is no longer pending is not announced at all.

The text is fixed per notification type (``templates``); customer text never reaches WhatsApp.
Simulated notifications are never sent (a paid, real channel must not carry simulated data).
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

from app.approvals.models import Approval
from app.core.clock import Clock
from app.core.config import Settings, get_settings
from app.identity.models import ChannelLink
from app.integrations.channels.base import ChannelRecipient, DeliveryResult
from app.integrations.channels.whatsapp import approval_buttons, templates, window
from app.integrations.channels.whatsapp.client import (
    WhatsAppApiError,
    WhatsAppClient,
    WhatsAppSendResult,
    WhatsAppValidationError,
)
from app.integrations.channels.whatsapp.costs import cost_metadata
from app.notifications.catalog import WHATSAPP_TYPES
from app.notifications.models import Notification, NotificationDelivery

_log = logging.getLogger(__name__)

APPROVAL_TYPE = "approval.requested"


def _terminal(reason: str, **metadata: Any) -> DeliveryResult:
    return DeliveryResult(
        success=False,
        status="failed",
        error_message=reason,
        metadata={"terminal": True, **metadata},
    )


class WhatsAppChannel:
    name: str = "whatsapp"

    def __init__(
        self, client: WhatsAppClient | None = None, settings: Settings | None = None
    ) -> None:
        self._settings = settings
        self._client = client
        if not self.settings.whatsapp_configured:
            raise KeyError("WhatsApp channel is not configured")

    @property
    def settings(self) -> Settings:
        return self._settings or get_settings()

    @property
    def client(self) -> WhatsAppClient:
        if self._client is None:
            s = self.settings
            self._client = WhatsAppClient(
                access_token=s.whatsapp_access_token,
                phone_number_id=s.whatsapp_phone_number_id,
                api_base_url=s.whatsapp_api_base_url,
                api_version=s.whatsapp_api_version,
            )
        return self._client

    def deliver_notification(
        self,
        session: Session,
        clock: Clock,
        delivery: NotificationDelivery,
        recipient: ChannelRecipient,
    ) -> DeliveryResult:
        workspace_id = delivery.workspace_id
        previous: dict[str, Any] = dict(delivery.delivery_metadata or {})
        if previous.get("send_state") == "sending":
            # An earlier attempt reached the provider call and never recorded an outcome.
            return _terminal("whatsapp_send_state_unknown", ambiguous=True, send_state="ambiguous")

        notification = session.get(Notification, delivery.notification_id)
        if (
            notification is None
            or notification.workspace_id != workspace_id
            or notification.recipient_user_id != recipient.user_id
        ):
            return _terminal("notification_not_found")
        if notification.is_simulated:
            return _terminal("simulated_notification_not_sent")
        template = templates.BY_TYPE.get(notification.type)
        if notification.type not in WHATSAPP_TYPES or template is None:
            return _terminal("notification_type_not_supported")

        link = (
            session.get(ChannelLink, delivery.channel_link_id) if delivery.channel_link_id else None
        )
        if (
            link is None
            or link.workspace_id != workspace_id
            or link.user_id != recipient.user_id
            or link.channel != "whatsapp"
            or link.status != "active"
        ):
            return _terminal("recipient_not_linked")
        to = link.channel_chat_id or link.channel_user_id
        locale = templates.normalize_locale(recipient.ui_locale)
        values = templates.variable_values(template, dict(notification.params or {}), locale)
        if values is None:
            return _terminal("template_variables_missing")
        body = template.render(locale, values)

        mode = window.choose_send_mode(link.last_inbound_at, clock.now())
        cost = cost_metadata(mode, template.name, locale, template.category)
        if mode == "template" and not self.settings.whatsapp_templates_approved:
            return _terminal("whatsapp_templates_not_approved", cost=cost)

        # An approval request: buttons inside the window, the plain template outside it.
        prepared: approval_buttons.PreparedButtons | None = None
        extra: dict[str, Any] = {}
        if notification.type == APPROVAL_TYPE:
            approval = (
                session.get(Approval, notification.subject_id) if notification.subject_id else None
            )
            if approval is not None and approval.workspace_id == workspace_id:
                if approval.status != "pending" or approval.expires_at <= clock.now():
                    return _terminal("approval_not_pending", cost=cost)
                extra["approval_id"] = str(approval.id)
                if mode == "session":
                    prepared = approval_buttons.prepare_buttons(
                        session, clock, approval, recipient.user_id, locale, recipient.timezone
                    )
                    if prepared is None:
                        return _terminal("recipient_not_member", cost=cost)
                    extra["approval_buttons"] = "prepared"
                else:
                    extra["approval_buttons"] = "not_sent_outside_window"
            else:
                extra["approval_buttons"] = "approval_not_found"

        # Mark the attempt before the call and end the transaction: no DB transaction may be open
        # during the HTTP call, and a crash after the call leaves a marker that blocks a re-send.
        # (Any action tokens minted above are committed here, before the message can exist.)
        delivery.delivery_metadata = {
            **previous,
            "send_state": "sending",
            "send_started_at": clock.now().isoformat(),
            "cost": cost,
            **extra,
        }
        session.commit()

        try:
            if prepared is not None:
                sent = self.client.send_interactive_buttons(to, prepared.body, prepared.buttons)
            else:
                sent = self._send(mode, to, template, locale, values, body)
        except WhatsAppValidationError:
            return _terminal("whatsapp_message_invalid", send_state="not_sent", cost=cost)
        except WhatsAppApiError as exc:
            return self._api_error(exc, cost)
        except Exception:
            _log.warning("whatsapp_send_unexpected_error")
            return _terminal(
                "whatsapp_send_ambiguous", ambiguous=True, send_state="ambiguous", cost=cost
            )
        if prepared is not None:
            extra["approval_buttons"] = "sent"
        return DeliveryResult(
            success=True,
            status="delivered",
            delivered_at=clock.now(),
            external_message_id=sent.message_id,
            metadata={"send_state": "sent", "wamid": sent.message_id, "cost": cost, **extra},
        )

    def _send(
        self,
        mode: str,
        to: str,
        template: templates.WhatsAppTemplate,
        locale: str,
        values: list[str],
        body: str,
    ) -> WhatsAppSendResult:
        if mode == "session":
            return self.client.send_text(to, body)
        return self.client.send_template(to, template.name, locale, values)

    @staticmethod
    def _api_error(exc: WhatsAppApiError, cost: dict[str, Any]) -> DeliveryResult:
        code = exc.error_code if isinstance(exc.error_code, int) else exc.status_code
        # Never log or store the provider's text: it is arbitrary and could echo request data.
        _log.warning("whatsapp_send_failed status=%s code=%s", exc.status_code, code)
        if exc.ambiguous:
            return _terminal(
                "whatsapp_send_ambiguous", ambiguous=True, send_state="ambiguous", cost=cost
            )
        if exc.retryable:
            return DeliveryResult(
                success=False,
                status="failed",
                error_message=f"whatsapp_retryable:{code}",
                metadata={"retryable": True, "send_state": "not_sent", "cost": cost},
            )
        return _terminal(f"whatsapp_rejected:{code}", send_state="not_sent", cost=cost)

    def render_command_result(
        self,
        session: Session,
        clock: Clock,
        command: Any,
        recipient: ChannelRecipient,
    ) -> None:
        """WhatsApp carries notifications only (ADR-027); command results are read in the app."""
        return None
