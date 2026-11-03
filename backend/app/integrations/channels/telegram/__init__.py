"""Telegram channel integration package (ADR-012, Phase 9 Session 04)."""

from app.integrations.channels.telegram.adapter import TelegramChannel
from app.integrations.channels.telegram.client import TelegramApiError, TelegramClient
from app.integrations.channels.telegram.dispatcher import (
    LinkedMessageHook,
    ProcessResult,
    process_update,
)
from app.integrations.channels.telegram.models import TelegramUpdate
from app.integrations.channels.telegram.webhook_format import (
    CallbackQuery,
    PhotoSize,
    TelegramChat,
    TelegramMessage,
    TelegramUser,
    Update,
)

__all__ = [
    "CallbackQuery",
    "LinkedMessageHook",
    "PhotoSize",
    "ProcessResult",
    "TelegramApiError",
    "TelegramChannel",
    "TelegramChat",
    "TelegramClient",
    "TelegramMessage",
    "TelegramUpdate",
    "TelegramUser",
    "Update",
    "process_update",
]
