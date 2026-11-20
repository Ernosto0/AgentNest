"""Link codes and fixed replies only; ADR-027 excludes commands and AI."""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.clock import Clock
from app.core.config import Settings
from app.core.errors import AppError
from app.identity.channels import ChannelLinkService
from app.identity.models import ChannelLink
from app.integrations.channels.whatsapp.approval_buttons import handle_button_reply
from app.integrations.channels.whatsapp.client import WhatsAppApiError, WhatsAppClient
from app.integrations.channels.whatsapp.costs import billing_from_pricing
from app.integrations.channels.whatsapp.models import WhatsAppWebhookEvent
from app.integrations.channels.whatsapp.webhook_format import (
    InboundButtonReply,
    InboundStatus,
    InboundText,
    parse_webhook,
)
from app.notifications.models import NotificationDelivery

_log = logging.getLogger(__name__)
REPLIES = {
    "tr": {
        "linked": "WhatsApp bağlantınız kuruldu. Ayarları Pivoris uygulamasından yönetebilirsiniz.",  # noqa: E501
        "failed": "Bağlantı kurulamadı. Pivoris Ayarlar'dan yeni bir kod alıp tekrar deneyin.",
        "open_app": "İşlemleriniz için Pivoris uygulamasını açın.",
    },
    "en": {
        "linked": "WhatsApp linked. You can manage settings in the Pivoris app.",
        "failed": "Linking failed. Get a new code from Pivoris Settings and try again.",
        "open_app": "Open the Pivoris app to manage your work.",
    },
}
_LINK_CODE = re.compile(r"^(?:LINK\s+)?([A-Z0-9]{8})$", re.ASCII)


@dataclass(frozen=True)
class WhatsAppProcessResult:
    processed: int = 0
    ignored: int = 0
    duplicates: int = 0

    @property
    def status(self) -> Literal["processed", "ignored", "duplicate"]:
        if self.processed:
            return "processed"
        if self.ignored or not self.duplicates:
            return "ignored"
        return "duplicate"


_PROVIDER_STATUSES = frozenset({"sent", "delivered", "read", "failed"})


def _inbound_time(raw: str | None, now: datetime) -> datetime:
    """When the owner's message was sent: Meta's timestamp if valid and not in the future, else
    now. The earlier of the two is used so a late (retried) webhook never extends the window."""
    try:
        sent = datetime.fromtimestamp(int(raw), tz=UTC) if raw else None
    except (ValueError, OverflowError, OSError):
        sent = None
    return sent if sent is not None and sent <= now else now


def _extend_window(link: ChannelLink, clock: Clock, raw_timestamp: str | None) -> None:
    """Any message from a linked owner (text, button tap, anything) opens or extends the
    24-hour customer-service window; the time only moves forward."""
    when = _inbound_time(raw_timestamp, clock.now())
    if link.last_inbound_at is None or when > link.last_inbound_at:
        link.last_inbound_at = when


def _record_status(session: Session, event: InboundStatus) -> None:
    """Keep the provider's later word on a message we sent (status and billing flags) on its
    ledger row. A status for a message without a ledger row (a link reply) is ignored."""
    if not event.recipient_id or event.status not in _PROVIDER_STATUSES:
        return
    resolved = ChannelLinkService.resolve_channel_user(session, "whatsapp", event.recipient_id)
    if resolved is None:
        return
    delivery = session.scalar(
        select(NotificationDelivery)
        .where(
            NotificationDelivery.workspace_id == resolved[1].id,
            NotificationDelivery.channel == "whatsapp",
            NotificationDelivery.delivery_metadata["wamid"].astext == event.message_id,
        )
        .with_for_update()
    )
    if delivery is None:
        return
    metadata = dict(delivery.delivery_metadata or {})
    metadata["provider_status"] = event.status
    if event.pricing:
        metadata["billing"] = billing_from_pricing(event.pricing)
    delivery.delivery_metadata = metadata
    if event.status == "failed":
        delivery.status = "failed"
        delivery.last_error = "whatsapp_status_failed"


class _DeferredWhatsAppClient:
    def __init__(self, client: WhatsAppClient) -> None:
        self.client = client
        self.pending: list[tuple[str, str]] = []

    def send_text(self, to: str, body: str) -> None:
        self.pending.append((to, body))

    def flush(self) -> None:
        for to, body in self.pending:
            try:
                self.client.send_text(to, body)
            except WhatsAppApiError as exc:
                # Never log arbitrary provider fields, payloads, identifiers or exceptions.
                code = exc.error_code if isinstance(exc.error_code, int) else None
                _log.warning("whatsapp_reply_failed class=WhatsAppApiError code=%s", code)
            except Exception:
                _log.warning("whatsapp_reply_failed class=Exception")
        self.pending.clear()


def process_webhook(
    session: Session,
    clock: Clock,
    payload: dict[str, Any],
    client: WhatsAppClient,
    settings: Settings,
) -> WhatsAppProcessResult:
    deferred = _DeferredWhatsAppClient(client)
    processed = ignored = duplicates = 0
    try:
        for event in parse_webhook(payload, settings.whatsapp_phone_number_id):
            sender = getattr(event, "wa_id", None)
            # A status event shares the wamid of the message it reports on and repeats (sent,
            # delivered, read), so its dedup key includes the status.
            dedup_key = (
                f"{event.message_id}:{event.status}"
                if isinstance(event, InboundStatus)
                else event.message_id
            )
            is_text = isinstance(event, InboundText)
            # Atomic insert handles concurrent Meta retries, unlike a SELECT then INSERT.
            inserted = session.execute(
                insert(WhatsAppWebhookEvent)
                .values(
                    message_id=dedup_key,
                    received_at=clock.now(),
                    status="processed" if is_text else "ignored",
                    wa_id_hash=hashlib.sha256(sender.encode()).hexdigest() if sender else None,
                    error=None,
                )
                .on_conflict_do_nothing(index_elements=["message_id"])
                .returning(WhatsAppWebhookEvent.message_id)
            ).scalar_one_or_none()
            if inserted is None:
                duplicates += 1
                continue
            if isinstance(event, InboundStatus):
                _record_status(session, event)
                ignored += 1
                continue
            if isinstance(event, InboundButtonReply):
                # An approve or reject tap. Only a number linked to an active member is answered;
                # any other sender gets no reply at all (nothing is revealed to a forwarded tap).
                tapper = ChannelLinkService.resolve_channel_user(session, "whatsapp", event.wa_id)
                if tapper is None:
                    ignored += 1
                    continue
                _extend_window(tapper[2], clock, event.timestamp)
                if handle_button_reply(session, clock, event, tapper, deferred.send_text):
                    # decide() may have committed; re-read the ledger row before updating it.
                    row = session.get(WhatsAppWebhookEvent, dedup_key)
                    if row is not None:
                        row.status = "processed"
                    processed += 1
                else:
                    ignored += 1
                continue
            if not isinstance(event, InboundText):
                other = ChannelLinkService.resolve_channel_user(session, "whatsapp", event.wa_id)
                if other:
                    _extend_window(other[2], clock, event.timestamp)
                ignored += 1
                continue
            match = _LINK_CODE.fullmatch(event.text.strip().upper())
            reply = None
            if match:
                try:
                    ChannelLinkService.redeem_link_code(
                        session,
                        clock,
                        channel="whatsapp",
                        channel_user_id=event.wa_id,
                        channel_chat_id=event.wa_id,
                        raw_code=match.group(1),
                        channel_username=None,
                    )
                    reply = "linked"
                except AppError as exc:
                    if exc.code not in {"LINK_CODE_INVALID", "LINK_CODE_USED", "LINK_CODE_EXPIRED"}:
                        raise
                    reply = "failed"
            resolved = ChannelLinkService.resolve_channel_user(session, "whatsapp", event.wa_id)
            locale = resolved[0].ui_locale if resolved else "tr"
            if resolved:
                _extend_window(resolved[2], clock, event.timestamp)
            # ADR-027: free text never reaches commands, approvals, the agent or any LLM.
            if reply is None and resolved:
                reply = "open_app"
            if reply:
                deferred.send_text(event.wa_id, REPLIES.get(locale, REPLIES["tr"])[reply])
            processed += 1
        session.commit()
    except Exception:
        session.rollback()
        raise
    deferred.flush()
    return WhatsAppProcessResult(processed, ignored, duplicates)
