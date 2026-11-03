"""Pydantic schemas for Telegram Bot API updates (ADR-012, Phase 9 Session 04)."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class TelegramUser(BaseModel):
    """Telegram User object."""

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    id: int
    is_bot: bool = False
    first_name: str = ""
    last_name: str | None = None
    username: str | None = None
    language_code: str | None = None


class TelegramChat(BaseModel):
    """Telegram Chat object."""

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    id: int
    type: str
    title: str | None = None
    username: str | None = None
    first_name: str | None = None
    last_name: str | None = None


class PhotoSize(BaseModel):
    """Telegram PhotoSize object."""

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    file_id: str
    file_unique_id: str
    width: int
    height: int
    file_size: int | None = None


class TelegramMessage(BaseModel):
    """Telegram Message object."""

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    message_id: int
    date: int
    chat: TelegramChat
    from_: TelegramUser | None = Field(default=None, alias="from")
    text: str | None = None
    caption: str | None = None
    photo: list[PhotoSize] | None = None
    reply_to_message: Any | None = None


class CallbackQuery(BaseModel):
    """Telegram CallbackQuery object."""

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    id: str
    from_: TelegramUser = Field(alias="from")
    message: TelegramMessage | None = None
    data: str | None = None


class Update(BaseModel):
    """Incoming Telegram Update payload."""

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    update_id: int
    message: TelegramMessage | None = None
    edited_message: TelegramMessage | None = None
    callback_query: CallbackQuery | None = None


# Friendly aliases
User = TelegramUser
Chat = TelegramChat
Message = TelegramMessage
TelegramUpdateSchema = Update
