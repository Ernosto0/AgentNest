"""Telegram update processing pipeline and dispatcher (ADR-012, Phase 9 Session 04)."""

from __future__ import annotations

import html
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.clock import Clock
from app.core.errors import AppError
from app.core.logging import get_logger
from app.identity.channels import ChannelLinkService
from app.identity.models import ChannelLink, User, Workspace
from app.integrations.channels.telegram.client import TelegramClient
from app.integrations.channels.telegram.models import TelegramUpdate
from app.integrations.channels.telegram.webhook_format import (
    TelegramMessage,
    Update,
)
from app.notifications.models import Notification

_log = get_logger("app.integrations.channels.telegram.dispatcher")

LinkedMessageHook = Callable[
    [Session, Clock, User, Workspace, ChannelLink, TelegramMessage, TelegramClient],
    None,
]


@dataclass(frozen=True)
class ProcessResult:
    """Outcome of processing an incoming Telegram update."""

    status: Literal["processed", "ignored", "duplicate", "failed"]
    update_id: int
    channel_user_id: str | None = None
    action: str | None = None
    error: str | None = None


def _parse_command(text: str) -> tuple[str, str]:
    """Parse text into (command, argument).

    Strips '@botname' from command if present.
    """
    parts = text.strip().split(None, 1)
    if not parts:
        return "", ""
    raw_cmd = parts[0]
    arg = parts[1].strip() if len(parts) > 1 else ""
    cmd = raw_cmd.split("@")[0].lower()
    return cmd, arg


def process_update(
    session: Session,
    clock: Clock,
    update_data: dict[str, Any] | Update,
    client: TelegramClient | None = None,
    on_linked_message: LinkedMessageHook | None = None,
) -> ProcessResult:
    """Process one incoming Telegram update with deduplication and command routing."""
    tg_client = client or TelegramClient()

    update = update_data if isinstance(update_data, Update) else Update.model_validate(update_data)

    update_id = update.update_id

    # 1. Deduplication against telegram_updates global table (INV-06)
    existing = session.get(TelegramUpdate, update_id)
    if existing is not None:
        _log.info("duplicate_telegram_update_rejected", update_id=update_id)
        return ProcessResult(
            status="duplicate",
            update_id=update_id,
            channel_user_id=existing.channel_user_id,
            action="duplicate",
        )

    # 2. Extract sender and payload
    channel_user_id: str | None = None
    username: str | None = None
    chat_id: str | None = None
    message: TelegramMessage | None = update.message or update.edited_message

    if message and message.from_:
        channel_user_id = str(message.from_.id)
        username = message.from_.username
        chat_id = str(message.chat.id)
    elif update.callback_query and update.callback_query.from_:
        channel_user_id = str(update.callback_query.from_.id)
        username = update.callback_query.from_.username
        if update.callback_query.message:
            chat_id = str(update.callback_query.message.chat.id)

    # Record update in global table
    record = TelegramUpdate(
        update_id=update_id,
        received_at=clock.now(),
        status="processed",
        channel_user_id=channel_user_id,
        error=None,
    )
    session.add(record)
    session.flush()

    # 3. Handle Callback Query acknowledgment
    if update.callback_query:
        try:
            tg_client.answer_callback_query(update.callback_query.id)
        except Exception as exc:
            _log.warning("failed_answering_callback_query", error=str(exc))
        return ProcessResult(
            status="processed",
            update_id=update_id,
            channel_user_id=channel_user_id,
            action="callback_query",
        )

    # 4. If no message or chat_id, mark ignored
    if not message or not chat_id or not channel_user_id:
        record.status = "ignored"
        session.flush()
        return ProcessResult(
            status="ignored",
            update_id=update_id,
            channel_user_id=channel_user_id,
            action="ignored",
        )

    text = (message.text or message.caption or "").strip()
    cmd, arg = _parse_command(text)

    try:
        # Route: /start
        if cmd == "/start":
            greeting = (
                "👋 <b>Welcome to AgentNest!</b>\n\n"
                "I am your business operations and delegated autonomy assistant.\n\n"
                "<b>With AgentNest you can:</b>\n"
                "• Receive instant notifications and approval requests\n"
                "• Review and approve marketing content and replies\n"
                "• Query business performance and status\n\n"
                "<b>To connect your account:</b>\n"
                "1. Open AgentNest in your browser\n"
                "2. Navigate to <i>Settings → Notifications & Channels</i>\n"
                "3. Generate a <b>Telegram Link Code</b>\n"
                "4. Send <code>/link &lt;CODE&gt;</code> here!"
            )
            tg_client.send_message(chat_id=chat_id, text=greeting, parse_mode="HTML")
            return ProcessResult(
                status="processed",
                update_id=update_id,
                channel_user_id=channel_user_id,
                action="start",
            )

        # Route: /link <code>
        if cmd == "/link":
            if not arg:
                tg_client.send_message(
                    chat_id=chat_id,
                    text=(
                        "⚠️ Please provide your 8-character link code: "
                        "<code>/link &lt;CODE&gt;</code>"
                    ),
                    parse_mode="HTML",
                )
                return ProcessResult(
                    status="processed",
                    update_id=update_id,
                    channel_user_id=channel_user_id,
                    action="link_missing_code",
                )

            try:
                ChannelLinkService.redeem_link_code(
                    session,
                    clock,
                    channel="telegram",
                    channel_user_id=channel_user_id,
                    channel_chat_id=chat_id,
                    raw_code=arg,
                    channel_username=username,
                )
                resolved = ChannelLinkService.resolve_channel_user(
                    session, channel="telegram", channel_user_id=channel_user_id
                )
                if resolved:
                    user, workspace, _ = resolved
                    user_name = user.display_name or user.email
                    ws_name = workspace.name
                else:
                    user_name = "User"
                    ws_name = "AgentNest"

                tg_client.send_message(
                    chat_id=chat_id,
                    text=(
                        f"✅ <b>Successfully linked!</b>\n\n"
                        f"Welcome, <b>{html.escape(user_name)}</b>! "
                        f"You are connected to workspace: <b>{html.escape(ws_name)}</b>."
                    ),
                    parse_mode="HTML",
                )
                return ProcessResult(
                    status="processed",
                    update_id=update_id,
                    channel_user_id=channel_user_id,
                    action="link_success",
                )
            except AppError as exc:
                if exc.code == "LINK_CODE_INVALID":
                    msg = (
                        "❌ <b>Invalid link code.</b> Please check the code in "
                        "AgentNest Settings and try again."
                    )
                elif exc.code == "LINK_CODE_USED":
                    msg = (
                        "❌ <b>This link code has already been used.</b> Please generate "
                        "a new code in AgentNest Settings."
                    )
                elif exc.code == "LINK_CODE_EXPIRED":
                    msg = (
                        "❌ <b>This link code has expired.</b> Link codes are valid for "
                        "15 minutes. Please generate a new code in Settings."
                    )
                else:
                    msg = f"❌ <b>Link failed:</b> {html.escape(exc.code)}"

                tg_client.send_message(chat_id=chat_id, text=msg, parse_mode="HTML")
                return ProcessResult(
                    status="processed",
                    update_id=update_id,
                    channel_user_id=channel_user_id,
                    action=f"link_failed_{exc.code}",
                )

        # Route: /unlink
        if cmd == "/unlink":
            ChannelLinkService.unlink_by_channel(
                session,
                clock,
                channel="telegram",
                channel_user_id=channel_user_id,
            )
            tg_client.send_message(
                chat_id=chat_id,
                text="🔌 Your Telegram account has been unlinked from AgentNest.",
                parse_mode="HTML",
            )
            return ProcessResult(
                status="processed",
                update_id=update_id,
                channel_user_id=channel_user_id,
                action="unlink",
            )

        # Route: /status
        if cmd == "/status":
            resolved = ChannelLinkService.resolve_channel_user(
                session,
                channel="telegram",
                channel_user_id=channel_user_id,
            )
            if resolved is None:
                tg_client.send_message(
                    chat_id=chat_id,
                    text=(
                        "ℹ️ <b>Account Status</b>\n\n"
                        "Your Telegram account is not linked to any AgentNest workspace.\n\n"
                        "Use <code>/link &lt;CODE&gt;</code> to connect your account."
                    ),
                    parse_mode="HTML",
                )
            else:
                user, workspace, link = resolved
                user_name = user.display_name or user.email
                unread_count = (
                    session.scalar(
                        select(func.count(Notification.id)).where(
                            Notification.workspace_id == workspace.id,
                            Notification.recipient_user_id == user.id,
                            Notification.read_at.is_(None),
                        )
                    )
                    or 0
                )
                linked_time_str = link.linked_at.strftime("%Y-%m-%d %H:%M UTC")
                tg_client.send_message(
                    chat_id=chat_id,
                    text=(
                        f"✅ <b>Linked to AgentNest</b>\n\n"
                        f"• <b>Workspace:</b> {html.escape(workspace.name)}\n"
                        f"• <b>User:</b> {html.escape(user_name)}\n"
                        f"• <b>Active notifications:</b> {unread_count}\n"
                        f"• <b>Linked at:</b> {linked_time_str}\n\n"
                        f"Send <code>/unlink</code> to disconnect."
                    ),
                    parse_mode="HTML",
                )
            return ProcessResult(
                status="processed",
                update_id=update_id,
                channel_user_id=channel_user_id,
                action="status",
            )

        # Non-command or unhandled text
        resolved = ChannelLinkService.resolve_channel_user(
            session,
            channel="telegram",
            channel_user_id=channel_user_id,
        )

        if resolved is None:
            # Unlinked user
            tg_client.send_message(
                chat_id=chat_id,
                text=(
                    "ℹ️ You have not linked your Telegram account yet.\n\n"
                    "Please link your account first using <code>/link &lt;CODE&gt;</code>.\n"
                    "You can generate a link code in the AgentNest web app under "
                    "<i>Settings → Notifications & Channels</i>."
                ),
                parse_mode="HTML",
            )
            return ProcessResult(
                status="processed",
                update_id=update_id,
                channel_user_id=channel_user_id,
                action="unlinked_prompt",
            )

        # Linked user non-command message: execute hook for Session 5 routing
        user, workspace, link = resolved
        if on_linked_message is not None:
            on_linked_message(session, clock, user, workspace, link, message, tg_client)
        else:
            tg_client.send_message(
                chat_id=chat_id,
                text=(
                    "💬 Message received. Natural language command execution will "
                    "be available in Session 05."
                ),
                parse_mode="HTML",
            )

        return ProcessResult(
            status="processed",
            update_id=update_id,
            channel_user_id=channel_user_id,
            action="linked_message",
        )

    except Exception as exc:
        _log.exception("telegram_update_processing_failed", update_id=update_id)
        record.status = "failed"
        record.error = str(exc)
        session.flush()
        return ProcessResult(
            status="failed",
            update_id=update_id,
            channel_user_id=channel_user_id,
            error=str(exc),
        )
