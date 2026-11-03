"""Telegram OwnerChannel adapter (ADR-012, Phase 9 Session 04)."""

from __future__ import annotations

import contextlib
import html
from typing import Any

from sqlalchemy.orm import Session

from app.core.clock import Clock
from app.integrations.channels.base import ChannelRecipient, DeliveryResult, OwnerChannel
from app.integrations.channels.telegram.client import TelegramClient
from app.notifications.models import Notification, NotificationDelivery

SEVERITY_ICONS: dict[str, str] = {
    "critical": "🚨",
    "attention": "⚠️",
    "info": "ℹ️",
}


def _format_notification_text(notification: Notification) -> str:
    icon = SEVERITY_ICONS.get(notification.severity, "ℹ️")
    raw_title = (
        notification.params.get("title")
        or notification.type.replace(".", " ").replace("_", " ").title()
    )
    title = html.escape(str(raw_title))
    body = html.escape(
        str(notification.params.get("message") or notification.params.get("body") or "")
    )

    lines = [f"{icon} <b>{title}</b>"]
    if body:
        lines.append("")
        lines.append(body)

    other_params = {
        k: v
        for k, v in notification.params.items()
        if k not in ("title", "message", "body", "link_url")
    }
    if other_params:
        lines.append("")
        for k, v in other_params.items():
            lines.append(f"• <i>{html.escape(str(k))}</i>: {html.escape(str(v))}")

    return "\n".join(lines)


class TelegramChannel(OwnerChannel):
    """Owner channel adapter for Telegram Bot API (ADR-012 §5.1)."""

    name: str = "telegram"

    def __init__(self, client: TelegramClient | None = None) -> None:
        self._client = client

    @property
    def client(self) -> TelegramClient:
        if self._client is None:
            self._client = TelegramClient()
        return self._client

    def deliver_notification(
        self,
        session: Session,
        clock: Clock,
        delivery: NotificationDelivery,
        recipient: ChannelRecipient,
    ) -> DeliveryResult:
        """Deliver one notification to the recipient on Telegram."""
        chat_id = recipient.channel_chat_id or recipient.channel_user_id
        if not chat_id:
            return DeliveryResult(
                success=False,
                status="failed",
                error_message="Recipient missing Telegram chat ID",
            )

        notification = session.get(Notification, delivery.notification_id)
        if notification is None:
            return DeliveryResult(
                success=False,
                status="failed",
                error_message=f"Notification record not found: {delivery.notification_id}",
            )

        text = _format_notification_text(notification)

        try:
            res = self.client.send_message(
                chat_id=chat_id,
                text=text,
                parse_mode="HTML",
            )
            msg_id = (
                str(res.get("message_id"))
                if isinstance(res, dict) and res.get("message_id") is not None
                else None
            )
            return DeliveryResult(
                success=True,
                status="delivered",
                delivered_at=clock.now(),
                external_message_id=msg_id,
                metadata={"message_id": msg_id} if msg_id else {},
            )
        except Exception as exc:
            return DeliveryResult(
                success=False,
                status="failed",
                error_message=str(exc),
            )

    def render_command_result(
        self,
        session: Session,
        clock: Clock,
        command: Any,
        recipient: ChannelRecipient,
    ) -> None:
        """Render the outcome of an owner command to Telegram."""
        chat_id = recipient.channel_chat_id or recipient.channel_user_id
        if not chat_id:
            return

        summary = (
            getattr(command, "result_summary", None)
            or getattr(command, "text", None)
            or str(command)
        )
        text = f"🤖 {html.escape(str(summary))}"
        with contextlib.suppress(Exception):
            self.client.send_message(chat_id=chat_id, text=text, parse_mode="HTML")
