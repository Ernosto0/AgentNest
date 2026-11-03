"""Owner channel abstraction: protocol, recipient contract, and default web channel (ADR-012)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any, Literal, Protocol, runtime_checkable

from sqlalchemy.orm import Session

from app.core.clock import Clock

if TYPE_CHECKING:
    from app.notifications.models import NotificationDelivery


@dataclass(frozen=True)
class ChannelRecipient:
    """Target identity context for dispatching notifications or rendering command results."""

    user_id: uuid.UUID
    workspace_id: uuid.UUID
    channel: str = "web"
    channel_user_id: str | None = None
    channel_chat_id: str | None = None
    channel_username: str | None = None
    ui_locale: str = "en"
    timezone: str = "UTC"


@dataclass(frozen=True)
class DeliveryResult:
    """Outcome of attempting to deliver a notification across a channel."""

    success: bool
    status: Literal["delivered", "failed", "skipped_quiet_hours"] = "delivered"
    error_message: str | None = None
    external_message_id: str | None = None
    delivered_at: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class OwnerChannel(Protocol):
    """Protocol for owner communication channels (ADR-012 §5.1)."""

    name: str

    def deliver_notification(
        self,
        session: Session,
        clock: Clock,
        delivery: NotificationDelivery,
        recipient: ChannelRecipient,
    ) -> DeliveryResult:
        """Deliver one notification to the recipient on this channel."""
        ...

    def render_command_result(
        self,
        session: Session,
        clock: Clock,
        command: Any,
        recipient: ChannelRecipient,
    ) -> None:
        """Render the outcome of an owner command to this channel."""
        ...


class WebChannel:
    """In-app web notification and command renderer (ADR-012 §5.1).

    The web channel requires no external push; notifications are stored in the database
    and retrieved by the frontend via the notification center.
    """

    name: str = "web"

    def deliver_notification(
        self,
        session: Session,
        clock: Clock,
        delivery: NotificationDelivery,
        recipient: ChannelRecipient,
    ) -> DeliveryResult:
        return DeliveryResult(
            success=True,
            status="delivered",
            delivered_at=clock.now(),
            metadata={"channel": "web", "in_app": True},
        )

    def render_command_result(
        self,
        session: Session,
        clock: Clock,
        command: Any,
        recipient: ChannelRecipient,
    ) -> None:
        # Web command results are read via the existing owner_commands REST API
        return None

