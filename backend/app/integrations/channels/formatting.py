"""Channel-agnostic formatters for OwnerCommand outcomes (Telegram, WhatsApp, etc.).

Ensures consistent conversational formatting across messaging channels.
"""

from __future__ import annotations

import html
from typing import Any

from app.commands.narrator import narrate_fallback
from app.integrations.channels.base import ChannelRecipient


def format_command_for_telegram(
    command: Any, recipient: ChannelRecipient
) -> tuple[str, dict[str, Any] | None]:
    """Format an OwnerCommand for Telegram HTML message and inline keyboard."""
    is_tr = (recipient.ui_locale or "tr").lower().startswith("tr")
    status = getattr(command, "status", None)
    result = getattr(command, "result", None) or {}
    params = result.get("params", {})
    message_key = result.get("message_key", "")
    links = result.get("links", [])

    # Prefer conversational reply_text
    reply_text = result.get("reply_text") or params.get("reply_text")
    if not reply_text and message_key:
        reply_text = narrate_fallback(
            message_key=message_key,
            params=params,
            user_locale="tr" if is_tr else "en",
            user_query=getattr(command, "raw_text", ""),
        )

    if status == "needs_clarification":
        clarification = getattr(command, "clarification", {}) or {}
        q_text = clarification.get("question") or (
            "Detay vermeniz gerekiyor." if is_tr else "Please clarify:"
        )
        heading = "Açıklama Gerekiyor" if is_tr else "Clarification Needed"
        text = f"❓ <b>{heading}</b>\n\n{html.escape(str(q_text))}"
        return text, None

    if status == "awaiting_confirmation":
        resolution = getattr(command, "resolution", {}) or {}
        summary = resolution.get("summary") or (
            "Onayınız bekleniyor." if is_tr else "Approval required."
        )
        heading = "Onay Gerekiyor" if is_tr else "Confirmation Needed"
        text = f"⚠️ <b>{heading}</b>\n\n{html.escape(str(summary))}"
        return text, None

    if status == "completed":
        content = reply_text or str(params or "İşlem tamamlandı" if is_tr else "Completed")
        text = f"💬 {html.escape(content)}"

        # Build reply markup if report link exists
        reply_markup = None
        report_link = next((lnk for lnk in links if lnk.get("target") == "report"), None)
        if report_link:
            btn_text = "📊 Raporu Aç" if is_tr else "📊 Open Report"
            # Placeholder web URL
            web_url = f"/w/{recipient.workspace_id}/more/reports"
            reply_markup = {"inline_keyboard": [[{"text": btn_text, "url": web_url}]]}
        return text, reply_markup

    if status == "failed":
        err_msg = (
            "Komut işlenirken bir sorun oluştu."
            if is_tr
            else "An error occurred while executing the command."
        )
        return f"❌ {html.escape(err_msg)}", None

    # Fallback status
    raw_text = getattr(command, "raw_text", "")
    escaped = html.escape(raw_text)
    if is_tr:
        msg = (
            f'⚡ <b>Komut Alındı</b>\n\n<i>"{escaped}"</i>\n\nKomutunuz sıraya alındı ve işleniyor.'
        )
    else:
        msg = f'⚡ <b>Command Received</b>\n\n<i>"{escaped}"</i>\n\nCommand queued for processing.'
    return msg, None


def format_command_for_whatsapp(command: Any, recipient: ChannelRecipient) -> str:
    """Format an OwnerCommand for WhatsApp using WhatsApp markdown (*bold*, _italic_)."""
    is_tr = (recipient.ui_locale or "tr").lower().startswith("tr")
    status = getattr(command, "status", None)
    result = getattr(command, "result", None) or {}
    params = result.get("params", {})
    message_key = result.get("message_key", "")

    reply_text = result.get("reply_text") or params.get("reply_text")
    if not reply_text and message_key:
        reply_text = narrate_fallback(
            message_key=message_key,
            params=params,
            user_locale="tr" if is_tr else "en",
            user_query=getattr(command, "raw_text", ""),
        )

    if status == "completed":
        content = reply_text or ("İşlem tamamlandı." if is_tr else "Operation completed.")
        return f"💬 {content}"

    if status == "needs_clarification":
        clarification = getattr(command, "clarification", {}) or {}
        q_text = clarification.get("question") or (
            "Lütfen detay belirtin." if is_tr else "Please clarify:"
        )
        return f"*❓ {'Açıklama Gerekiyor' if is_tr else 'Clarification Needed'}*\n\n{q_text}"

    if status == "awaiting_confirmation":
        resolution = getattr(command, "resolution", {}) or {}
        summary = resolution.get("summary") or (
            "Onayınız bekleniyor." if is_tr else "Approval required."
        )
        return f"*⚠️ {'Onay Gerekiyor' if is_tr else 'Confirmation Needed'}*\n\n{summary}"

    if status == "failed":
        return "❌ " + ("Komut tamamlanamadı." if is_tr else "Command could not be completed.")

    raw_text = getattr(command, "raw_text", "")
    return f"⚡ *{'Komut Alındı' if is_tr else 'Command Received'}*\n_{raw_text}_\n\n" + (
        "İşleniyor..." if is_tr else "Processing..."
    )
