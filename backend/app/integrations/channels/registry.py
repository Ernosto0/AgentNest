"""Channel registry for owner communication channels (ADR-012 §5.1).

Maintains a registry of available owner channels (e.g. "web", "telegram").
Provides lazy resolution so Telegram is only loaded when registered or requested,
avoiding heavy imports during normal web-only operation.
"""

from collections.abc import Callable
from typing import cast

from app.integrations.channels.base import OwnerChannel, WebChannel

_REGISTRY: dict[str, OwnerChannel] = {}
_FACTORIES: dict[str, Callable[[], OwnerChannel]] = {}


def register_channel(name: str, channel: OwnerChannel) -> None:
    """Register an active OwnerChannel instance."""
    _REGISTRY[name] = channel


def register_channel_factory(name: str, factory: Callable[[], OwnerChannel]) -> None:
    """Register a lazy factory for an OwnerChannel instance."""
    _FACTORIES[name] = factory


def get_channel(name: str) -> OwnerChannel:
    """Retrieve the registered channel instance by name, resolving lazily if needed.

    Raises KeyError if the channel is unknown or cannot be resolved.
    """
    if name in _REGISTRY:
        return _REGISTRY[name]

    if name == "web":
        web = WebChannel()
        _REGISTRY["web"] = web
        return web

    if name in _FACTORIES:
        channel = _FACTORIES[name]()
        _REGISTRY[name] = channel
        return channel

    # Attempt lazy resolution for telegram if implemented in later session
    if name == "telegram":
        try:
            from app.integrations.channels.telegram import TelegramChannel

            tg: OwnerChannel = cast(OwnerChannel, TelegramChannel())
            _REGISTRY["telegram"] = tg
            return tg
        except ImportError:
            raise KeyError(
                f"Channel '{name}' is not registered and telegram adapter is not available"
            ) from None

    raise KeyError(f"Unknown owner channel: '{name}'. Available: {list_registered_channels()}")


def list_registered_channels() -> list[str]:
    """Return the names of all currently registered or resolvable channels."""
    names = set(_REGISTRY.keys()) | set(_FACTORIES.keys()) | {"web"}
    return sorted(names)


def reset_channel_registry() -> None:
    """Reset the registry to initial state (primarily for test isolation)."""
    _REGISTRY.clear()
    _FACTORIES.clear()
    _REGISTRY["web"] = WebChannel()


# Initialise default web channel
reset_channel_registry()
