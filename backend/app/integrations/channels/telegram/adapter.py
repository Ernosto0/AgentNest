"""Telegram OwnerChannel adapter (ADR-012, Phase 9 Session 04 & 06)."""

from __future__ import annotations

import contextlib
import html
from datetime import datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.owner_requests.models import OwnerQuestion

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.approvals.action_tokens import ActionTokenService
from app.approvals.models import Approval
from app.core.clock import Clock
from app.core.config import get_settings
from app.core.context import ActorRef
from app.identity.models import User, Workspace, WorkspaceMember
from app.identity.service import workspace_context
from app.integrations.channels.base import ChannelRecipient, DeliveryResult, OwnerChannel
from app.integrations.channels.telegram.client import TelegramClient
from app.notifications.models import Notification, NotificationDelivery

SEVERITY_ICONS: dict[str, str] = {
    "critical": "🚨",
    "attention": "⚠️",
    "info": "ℹ️",
}


def _format_time_tz(dt: datetime, tz_name: str | None) -> str:
    """Format datetime string according to timezone (INV-19)."""
    if tz_name:
        with contextlib.suppress(Exception):
            from zoneinfo import ZoneInfo

            dt = dt.astimezone(ZoneInfo(tz_name))
    return dt.strftime("%Y-%m-%d %H:%M")


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


def _deliver_approval_notification(
    client: TelegramClient,
    session: Session,
    clock: Clock,
    delivery: NotificationDelivery,
    recipient: ChannelRecipient,
    notification: Notification,
    approval: Approval,
) -> DeliveryResult:
    """Format and send approval.requested notification with single-use action buttons."""
    chat_id = recipient.channel_chat_id or recipient.channel_user_id
    if not chat_id:
        return DeliveryResult(
            success=False,
            status="failed",
            error_message="Recipient missing Telegram chat ID",
        )

    # 1. Resolve workspace, user and member context to generate single-use action tokens
    workspace = session.get(Workspace, delivery.workspace_id)
    user = session.get(User, recipient.user_id)
    if workspace is None or user is None:
        return DeliveryResult(
            success=False,
            status="failed",
            error_message="Workspace or user missing for approval notification",
        )

    member = session.scalar(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == workspace.id,
            WorkspaceMember.user_id == user.id,
        )
    )
    role = member.role if member else "owner"
    ctx = workspace_context(workspace, ActorRef.user(user.id), role)

    # 2. Create single-use action tokens bound to user, approval, decision & payload_hash
    token_approve = ActionTokenService.create_action_token(
        session, clock, ctx, approval, decision="approved", user_id=user.id
    )
    token_reject = ActionTokenService.create_action_token(
        session, clock, ctx, approval, decision="rejected", user_id=user.id
    )
    session.flush()

    # 3. Format message text with full summary details
    is_tr = (recipient.ui_locale or "tr").lower().startswith("tr")
    simulated = approval.is_simulated or notification.is_simulated
    sim_badge = (
        "🧪 <b>[SİMÜLASYON]</b>\n"
        if (simulated and is_tr)
        else ("🧪 <b>[SIMULATED]</b>\n" if simulated else "")
    )

    lines: list[str] = []
    if approval.subject_type == "reply_draft":
        from app.inbox.models import Conversation, Message, ReplyDraft
        from app.integrations.instagram.models import SocialAccount

        draft = session.get(ReplyDraft, approval.subject_id)
        conv = session.get(Conversation, draft.conversation_id) if draft else None
        account = session.get(SocialAccount, conv.social_account_id) if conv else None
        account_name = f"@{account.username}" if account and account.username else "Instagram"

        last_inbound = None
        if conv:
            last_inbound = session.scalar(
                select(Message)
                .where(Message.conversation_id == conv.id, Message.direction == "inbound")
                .order_by(Message.provider_timestamp.desc())
                .limit(1)
            )

        heading = "Onay İsteği: Müşteri Yanıtı" if is_tr else "Approval Request: Customer Reply"
        title = f"{sim_badge}💬 <b>{heading}</b>"
        lines.append(title)
        lines.append("")
        lines.append(f"• <b>{'Hesap' if is_tr else 'Account'}:</b> {html.escape(account_name)}")
        if conv and conv.customer_handle:
            c_label = "Müşteri" if is_tr else "Customer"
            lines.append(f"• <b>{c_label}:</b> @{html.escape(conv.customer_handle)}")
        if last_inbound and last_inbound.text:
            msg_label = "Gelen Mesaj" if is_tr else "Incoming Message"
            msg_text = html.escape(last_inbound.text[:200])
            lines.append(f'• <b>{msg_label}:</b> <i>"{msg_text}"</i>')
        proposed = draft.text if draft and draft.text else str(approval.summary.get("text", ""))
        rep_label = "Önerilen Yanıt" if is_tr else "Proposed Reply"
        lines.append(f"• <b>{rep_label}:</b>\n<blockquote>{html.escape(proposed)}</blockquote>")

    elif approval.subject_type == "content_item":
        from app.content.models import ContentItem
        from app.integrations.instagram.models import SocialAccount

        item = session.get(ContentItem, approval.subject_id)
        account = (
            session.get(SocialAccount, item.social_account_id)
            if item and item.social_account_id
            else None
        )
        account_name = f"@{account.username}" if account and account.username else "Instagram"

        c_heading = (
            "Onay İsteği: Paylaşım Planı" if is_tr else "Approval Request: Content Publication"
        )
        title = f"{sim_badge}📸 <b>{c_heading}</b>"
        lines.append(title)
        lines.append("")
        lines.append(f"• <b>{'Hesap' if is_tr else 'Account'}:</b> {html.escape(account_name)}")
        c_type = item.content_type.replace("_", " ").title() if item else "Story"
        lines.append(f"• <b>{'Tür' if is_tr else 'Type'}:</b> {html.escape(c_type)}")
        if item and item.title:
            lines.append(f"• <b>{'Başlık' if is_tr else 'Title'}:</b> {html.escape(item.title)}")
        if item and item.caption:
            cap_label = "Açıklama" if is_tr else "Caption"
            cap_text = html.escape(item.caption)
            lines.append(f"• <b>{cap_label}:</b>\n<blockquote>{cap_text}</blockquote>")
        if item and item.scheduled_at:
            sched_str = _format_time_tz(item.scheduled_at, recipient.timezone)
            time_label = "Planlanan Zaman" if is_tr else "Scheduled Time"
            lines.append(f"• <b>{time_label}:</b> {sched_str}")

    else:
        req_label = "Onay İsteği" if is_tr else "Approval Request"
        title = f"{sim_badge}⚡ <b>{req_label}: {html.escape(approval.action)}</b>"
        lines.append(title)
        lines.append("")
        for k, v in approval.summary.items():
            lines.append(f"• <b>{html.escape(str(k))}:</b> {html.escape(str(v))}")

    expires_str = _format_time_tz(approval.expires_at, recipient.timezone)
    lines.append(f"• <b>{'Son Karar Zamanı' if is_tr else 'Expires At'}:</b> {expires_str}")

    text = "\n".join(lines)

    # 4. Inline keyboard buttons
    btn_approve = "✅ Onayla" if is_tr else "✅ Approve"
    btn_reject = "❌ Reddet" if is_tr else "❌ Reject"
    btn_open = "📱 Uygulamada Aç" if is_tr else "📱 Open in App"

    settings = get_settings()
    web_url = f"{settings.frontend_origin.rstrip('/')}/approvals"

    reply_markup = {
        "inline_keyboard": [
            [
                {"text": btn_approve, "callback_data": f"act:{token_approve}"},
                {"text": btn_reject, "callback_data": f"act:{token_reject}"},
            ],
            [
                {"text": btn_open, "url": web_url},
            ],
        ]
    }

    try:
        res = client.send_message(
            chat_id=chat_id,
            text=text,
            parse_mode="HTML",
            reply_markup=reply_markup,
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
            metadata={"message_id": msg_id, "approval_id": str(approval.id)}
            if msg_id
            else {"approval_id": str(approval.id)},
        )
    except Exception as exc:
        return DeliveryResult(
            success=False,
            status="failed",
            error_message=str(exc),
        )


def _deliver_owner_question_notification(
    client: TelegramClient,
    session: Session,
    clock: Clock,
    delivery: NotificationDelivery,
    recipient: ChannelRecipient,
    notification: Notification,
    question: OwnerQuestion,
) -> DeliveryResult:
    """Format and send owner_question notification prompting for business information."""
    chat_id = recipient.channel_chat_id or recipient.channel_user_id
    if not chat_id:
        return DeliveryResult(
            success=False,
            status="failed",
            error_message="Recipient missing Telegram chat ID",
        )

    from app.inbox.models import Message
    from app.integrations.instagram.models import SocialAccount

    is_tr = (recipient.ui_locale or "tr").lower().startswith("tr")
    simulated = notification.is_simulated
    sim_badge = (
        "🧪 <b>[SİMÜLASYON]</b>\n"
        if (simulated and is_tr)
        else ("🧪 <b>[SIMULATED]</b>\n" if simulated else "")
    )

    account = (
        session.get(SocialAccount, question.social_account_id)
        if question.social_account_id
        else None
    )
    account_name = f"@{account.username}" if account and account.username else "Instagram"

    category_names = {
        "availability": "Müsaitlik / Randevu" if is_tr else "Availability / Booking",
        "exception": "İstisnai Durum" if is_tr else "Exception",
        "service_detail": "Hizmet Detayı" if is_tr else "Service Detail",
        "business_policy": "İşletme Politikası" if is_tr else "Business Policy",
        "other": "Genel Bilgi" if is_tr else "General Info",
    }
    category = category_names.get(question.required_info, question.required_info.title())

    q_heading = "Asistanınız Bilgi Bekliyor" if is_tr else "Your Assistant Needs Information"
    title = f"{sim_badge}❓ <b>{q_heading}</b>"
    q_body = html.escape(question.body or "")
    lines = [
        title,
        "",
        f"• <b>{'Hesap' if is_tr else 'Account'}:</b> {html.escape(account_name)}",
        f"• <b>{'Kategori' if is_tr else 'Category'}:</b> {html.escape(category)}",
        f"• <b>{'Soru' if is_tr else 'Question'}:</b>\n<blockquote>{q_body}</blockquote>",
    ]

    if question.source_message_id:
        source_msg = session.get(Message, question.source_message_id)
        if source_msg and source_msg.text:
            cust_label = "Müşteri Mesajı" if is_tr else "Customer Message"
            cust_text = html.escape(source_msg.text[:200])
            lines.append(f'• <b>{cust_label}:</b> <i>"{cust_text}"</i>')

    lines.append("")
    hint = (
        "💬 <i>Bu mesaja yanıt vererek (Reply) veya doğrudan yazarak cevaplayabilirsiniz.</i>"
        if is_tr
        else "💬 <i>You can answer by replying to this message or writing directly.</i>"
    )
    lines.append(hint)

    text = "\n".join(lines)

    settings = get_settings()
    web_url = f"{settings.frontend_origin.rstrip('/')}/inbox"
    btn_open = "📱 Uygulamada Aç" if is_tr else "📱 Open in App"
    reply_markup = {
        "inline_keyboard": [
            [{"text": btn_open, "url": web_url}],
        ]
    }

    try:
        res = client.send_message(
            chat_id=chat_id,
            text=text,
            parse_mode="HTML",
            reply_markup=reply_markup,
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
            metadata={"message_id": msg_id, "question_id": str(question.id)}
            if msg_id
            else {"question_id": str(question.id)},
        )
    except Exception as exc:
        return DeliveryResult(
            success=False,
            status="failed",
            error_message=str(exc),
        )


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
        notification = session.get(Notification, delivery.notification_id)
        if notification is None:
            return DeliveryResult(
                success=False,
                status="failed",
                error_message=f"Notification record not found: {delivery.notification_id}",
            )

        if notification.type == "approval.requested" and notification.subject_id is not None:
            approval = session.get(Approval, notification.subject_id)
            if approval is not None:
                return _deliver_approval_notification(
                    client=self.client,
                    session=session,
                    clock=clock,
                    delivery=delivery,
                    recipient=recipient,
                    notification=notification,
                    approval=approval,
                )

        if (
            notification.type in ("owner_question.created", "owner_question.requested")
            and notification.subject_id is not None
        ):
            from app.owner_requests.models import OwnerQuestion

            question = session.get(OwnerQuestion, notification.subject_id)
            if question is not None:
                return _deliver_owner_question_notification(
                    client=self.client,
                    session=session,
                    clock=clock,
                    delivery=delivery,
                    recipient=recipient,
                    notification=notification,
                    question=question,
                )

        chat_id = recipient.channel_chat_id or recipient.channel_user_id
        if not chat_id:
            return DeliveryResult(
                success=False,
                status="failed",
                error_message="Recipient missing Telegram chat ID",
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
