"""Owner channels (ADR-012): in-app web and external messenger integrations."""

from app.integrations.channels.base import (
    ChannelRecipient,
    DeliveryResult,
    OwnerChannel,
    WebChannel,
)
from app.integrations.channels.registry import (
    get_channel,
    list_registered_channels,
    register_channel,
    register_channel_factory,
    reset_channel_registry,
)

__all__ = [
    "ChannelRecipient",
    "DeliveryResult",
    "OwnerChannel",
    "WebChannel",
    "get_channel",
    "list_registered_channels",
    "register_channel",
    "register_channel_factory",
    "reset_channel_registry",
]
