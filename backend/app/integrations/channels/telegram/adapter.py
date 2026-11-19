"""Telegram OwnerChannel adapter (ADR-012, Phase 9 Session 04 & 06, Session 01)."""

from __future__ import annotations

import contextlib
import html
import logging
import uuid
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
from app.identity.models import ChannelLink, User, Workspace, WorkspaceMember
from app.identity.service import workspace_context
from app.integrations.channels.base import ChannelRecipient, DeliveryResult, OwnerChannel
from app.integrations.channels.telegram.client import TelegramApiError, TelegramClient
from app.notifications.models import Notification, NotificationDelivery
from app.notifications.quota_text import TEXT as QUOTA_TEXT

_log = logging.getLogger(__name__)

SEVERITY_ICONS: dict[str, str] = {
    "critical": "🚨",
    "attention": "⚠️",
    "info": "ℹ️",
}

_LOCALIZED_NOTIFICATION_TEXT: dict[str, dict[str, tuple[str, str]]] = {
    "approval.requested": {
        "tr": ("Onayınız bekleniyor", "Kararınızı bekleyen bir işlem var."),
        "en": ("Approval needed", "Something is waiting for your decision."),
    },
    "approval.expired": {
        "tr": ("Onay süresi doldu", "Bekleyen bir onay isteğinin süresi doldu."),
        "en": ("Approval expired", "A pending approval request has expired."),
    },
    "owner_question.requested": {
        "tr": ("Asistanınızın bir sorusu var", "Yanıtlamak için uygulamayı açın."),
        "en": ("Your assistant has a question", "Open the app to answer it."),
    },
    "owner_question.window_closed": {
        "tr": (
            "Bir soru yanıtsız kaldı",
            "24 saatlik mesajlaşma penceresi kapandı. Ne olduğunu görmek için uygulamayı açın.",
        ),
        "en": (
            "A question went unanswered",
            "The 24-hour messaging window closed. Open the app to see what happened.",
        ),
    },
    "content.failed": {
        "tr": ("Bir paylaşım yayınlanamadı", "Ne olduğunu görmek için uygulamayı açın."),
        "en": ("A post could not be published", "Open the app to see what happened."),
    },
    "content.on_hold": {
        "tr": ("Paylaşım beklemeye alındı", "Planlanan paylaşım kontrolünüzü bekliyor."),
        "en": ("Post placed on hold", "A scheduled post needs your review."),
    },
    "reply.failed": {
        "tr": ("Bir yanıt gönderilemedi", "Ne olduğunu görmek için uygulamayı açın."),
        "en": ("A reply was not sent", "Open the app to see what happened."),
    },
    "conversation.needs_human": {
        "tr": (
            "Görüşme ilgilenmenizi bekliyor",
            "Bir müşteri görüşmesi insan müdahalesi bekliyor.",
        ),
        "en": (
            "Conversation needs your attention",
            "A customer conversation requires human attention.",
        ),
    },
    "account.needs_reauth": {
        "tr": (
            "Instagram bağlantısı yenilenmeli",
            "Hesabı yeniden bağlamak için uygulamayı açın.",
        ),
        "en": (
            "Instagram needs to be reconnected",
            "Open the app to reconnect your account.",
        ),
    },
    "account.degraded": {
        "tr": (
            "Instagram bağlantısında gecikme",
            "Geçici bağlantı sorunları yaşanıyor; otomatik olarak yeniden denenecek.",
        ),
        "en": (
            "Instagram connection degraded",
            "Temporary connection issues detected; retrying automatically.",
        ),
    },
    "account.permission_missing": {
        "tr": (
            "Instagram izni eksik",
            "Gerekli izinleri vermek için hesabınızı uygulamada yeniden bağlayın.",
        ),
        "en": (
            "Instagram permission missing",
            "Reconnect your account in the app to grant the required permissions.",
        ),
    },
    "report.daily_ready": {
        "tr": ("Günlük rapor hazır", "Günlük özet raporunuzu uygulamada görüntüleyebilirsiniz."),
        "en": ("Daily report ready", "Your daily summary report is ready in the app."),
    },
    "report.missed_customers_ready": {
        "tr": (
            "Kaçırılan müşteri raporu hazır",
            "Haftalık kaçırılan müşteri özetinizi uygulamada inceleyin.",
        ),
        "en": (
            "Missed-customer report ready",
            "Review your weekly missed-customer summary in the app.",
        ),
    },
}


def _terminal(reason: str, **metadata: Any) -> DeliveryResult:
    return DeliveryResult(
        success=False,
        status="failed",
        error_message=reason,
        metadata={"terminal": True, **metadata},
    )


def _format_time_tz(dt: datetime, tz_name: str | None) -> str:
    """Format datetime string according to timezone (INV-19)."""
    if tz_name:
        with contextlib.suppress(Exception):
            from zoneinfo import ZoneInfo

            dt = dt.astimezone(ZoneInfo(tz_name))
    return dt.strftime("%Y-%m-%d %H:%M")


TELEGRAM_TEXT_BUDGET = 3900  # the API limit is 4096 characters (markup counts here: conservative)
FACT_LABEL_CHARS = 60
FACT_DISPLAY_CHARS = 40
EXPIRY_LINE_CHARS = 80
MORE_LINE_CHARS = 24  # room for the "+N more" line


def _format_date_tz(dt: datetime, tz_name: str | None) -> str:
    """The calendar day in the workspace timezone, ``2026-11-03`` (INV-19)."""
    return _format_time_tz(dt, tz_name)[:10]


def _clip(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _fact_source_lines(
    session: Session, draft: Any, tz_name: str | None, is_tr: bool, budget: int
) -> list[str]:
    """One compact line per verified fact the reply quotes: the value, where it comes from and
    when it was verified (D-01). The mapping is the server's (``knowledge.sources``); lines that
    do not fit ``budget`` characters are dropped, with a count of what was left out. All text from
    the database is HTML-escaped."""
    from app.knowledge.sources import fact_sources, unique_sources

    rendered = (draft.validation or {}).get("rendered", []) if draft else []
    if not rendered:
        return []
    sources = unique_sources(
        fact_sources(session, draft.workspace_id, rendered, "tr" if is_tr else "en")
    )
    title = "Değerlerin kaynağı" if is_tr else "Where the values come from"
    verified = "doğrulandı" if is_tr else "verified"
    unknown = "doğrulama tarihi kayıtlı değil" if is_tr else "verification date not recorded"
    lines: list[str] = []
    used = len(title) + 8
    for index, source in enumerate(sources):
        when = (
            f"{verified} {_format_date_tz(source.verified_at, tz_name)}"
            if source.verified_at
            else unknown
        )
        line = (
            f"• <b>{html.escape(_clip(source.display, FACT_DISPLAY_CHARS))}</b> — "
            f"{'kaynak' if is_tr else 'from'}: "
            f"{html.escape(_clip(source.label, FACT_LABEL_CHARS))}, {when}"
        )
        if used + len(line) + 1 > budget - MORE_LINE_CHARS:
            left = len(sources) - index
            lines.append(f"+{left} " + ("değer daha" if is_tr else "more"))
            break
        lines.append(line)
        used += len(line) + 1
    return [f"<b>{title}:</b>", *lines] if lines else []


def _format_notification_text(notification: Notification, locale: str | None = None) -> str:
    icon = SEVERITY_ICONS.get(notification.severity, "ℹ️")
    is_tr = (locale or "tr").lower().startswith("tr")
    lang = "tr" if is_tr else "en"
    params = notification.params if isinstance(notification.params, dict) else {}
    localized = _LOCALIZED_NOTIFICATION_TEXT.get(notification.type, {}).get(lang)

    raw_title = (
        params.get("title")
        or (localized[0] if localized else None)
        or notification.type.replace(".", " ").replace("_", " ").title()
    )
    raw_body = (
        params.get("message") or params.get("body") or (localized[1] if localized else "") or ""
    )
    title = html.escape(str(raw_title))
    body = html.escape(str(raw_body))

    sim_badge = (
        "🧪 <b>[SİMÜLASYON]</b>\n"
        if (notification.is_simulated and is_tr)
        else ("🧪 <b>[SIMULATED]</b>\n" if notification.is_simulated else "")
    )

    lines = [f"{sim_badge}{icon} <b>{title}</b>"]
    if body:
        lines.append("")
        lines.append(body)

    other_params = {
        k: v
        for k, v in params.items()
        if k not in ("title", "message", "body", "link_url", "summary")
    }
    if other_params:
        lines.append("")
        for k, v in other_params.items():
            lines.append(f"• <i>{html.escape(str(k))}</i>: {html.escape(str(v))}")

    return "\n".join(lines)


def _append_reply_draft_lines(
    session: Session,
    lines: list[str],
    *,
    draft: Any,
    conv: Any,
    account: Any,
    approval: Approval,
    recipient: ChannelRecipient,
    is_tr: bool,
    sim_badge: str,
) -> None:
    from app.inbox.models import Message

    account_name = f"@{account.username}" if account and account.username else "Instagram"
    last_inbound = None
    if conv is not None:
        last_inbound = session.scalar(
            select(Message)
            .where(Message.conversation_id == conv.id, Message.direction == "inbound")
            .order_by(Message.provider_timestamp.desc())
            .limit(1)
        )

    heading = "Onay İsteği: Müşteri Yanıtı" if is_tr else "Approval Request: Customer Reply"
    lines.append(f"{sim_badge}💬 <b>{heading}</b>")
    lines.append("")
    lines.append(f"• <b>{'Hesap' if is_tr else 'Account'}:</b> {html.escape(account_name)}")
    if conv is not None and conv.customer_handle:
        c_label = "Müşteri" if is_tr else "Customer"
        lines.append(f"• <b>{c_label}:</b> @{html.escape(conv.customer_handle)}")
    if last_inbound is not None and last_inbound.text:
        msg_label = "Gelen Mesaj" if is_tr else "Incoming Message"
        msg_text = html.escape(last_inbound.text[:200])
        lines.append(f'• <b>{msg_label}:</b> <i>"{msg_text}"</i>')
    summary_dict = approval.summary if isinstance(approval.summary, dict) else {}
    proposed = (
        draft.text
        if draft is not None and draft.text
        else str(summary_dict.get("text") or summary_dict.get("proposed_text") or "")
    )
    rep_label = "Önerilen Yanıt" if is_tr else "Proposed Reply"
    lines.append(f"• <b>{rep_label}:</b>\n<blockquote>{html.escape(proposed)}</blockquote>")
    room = TELEGRAM_TEXT_BUDGET - len("\n".join(lines)) - EXPIRY_LINE_CHARS
    fact_lines = _fact_source_lines(session, draft, recipient.timezone, is_tr, room)
    if fact_lines:
        lines.append("")
        lines.extend(fact_lines)


def _append_agent_action_lines(
    session: Session,
    lines: list[str],
    *,
    approval: Approval,
    recipient: ChannelRecipient,
    is_tr: bool,
    sim_badge: str,
) -> None:
    """Format an informed description for Account Agent approvals (subject_type='agent_action')."""
    from app.agent.models import AgentAction
    from app.comments.models import (
        PrivateReplyOpportunity,
        PublicComment,
        PublicCommentAction,
        PublicMedia,
    )
    from app.content.models import ContentItem
    from app.inbox.models import Conversation, ReplyDraft
    from app.integrations.calendar.models import CalendarAppointment
    from app.integrations.instagram.models import SocialAccount

    action = session.get(AgentAction, approval.subject_id)
    if action is not None and action.workspace_id != approval.workspace_id:
        action = None

    summary = approval.summary if isinstance(approval.summary, dict) else {}
    action_type = (
        action.action_type
        if action is not None
        else str(summary.get("action_type") or approval.action)
    )
    account = (
        session.get(SocialAccount, action.social_account_id)
        if action is not None and action.social_account_id
        else None
    )
    account_name = f"@{account.username}" if account and account.username else "Instagram"

    # 1. Account Agent DM Reply (dm.send)
    if action_type == "dm.send":
        draft = (
            session.get(ReplyDraft, action.payload_ref)
            if action is not None and action.payload_ref
            else None
        )
        if draft is None and action is not None:
            draft = session.scalar(
                select(ReplyDraft)
                .where(
                    ReplyDraft.workspace_id == action.workspace_id,
                    ReplyDraft.agent_action_id == action.id,
                )
                .limit(1)
            )
        if draft is not None and draft.workspace_id != approval.workspace_id:
            draft = None
        conv = session.get(Conversation, draft.conversation_id) if draft is not None else None
        if conv is None and action is not None and action.target_ref:
            with contextlib.suppress(ValueError):
                cand_conv = session.get(Conversation, uuid.UUID(action.target_ref))
                if cand_conv is not None and cand_conv.workspace_id == approval.workspace_id:
                    conv = cand_conv
        if account is None and conv is not None:
            account = session.get(SocialAccount, conv.social_account_id)
        _append_reply_draft_lines(
            session,
            lines,
            draft=draft,
            conv=conv,
            account=account,
            approval=approval,
            recipient=recipient,
            is_tr=is_tr,
            sim_badge=sim_badge,
        )
        return

    # 2. Account Agent Comment Reply / Private Reply / Moderation
    if action_type in (
        "comment.reply",
        "comment.private_reply",
        "comment.hide",
        "comment.unhide",
        "comment.delete",
    ):
        comment: PublicComment | None = None
        proposed_text: str | None = None
        if action_type == "comment.private_reply":
            opp = (
                session.get(PrivateReplyOpportunity, action.payload_ref)
                if action is not None and action.payload_ref
                else None
            )
            if opp is not None and opp.workspace_id == approval.workspace_id:
                comment = session.get(PublicComment, opp.comment_id)
                proposed_text = opp.text
        else:
            pub_act = (
                session.get(PublicCommentAction, action.payload_ref)
                if action is not None and action.payload_ref
                else None
            )
            if pub_act is not None and pub_act.workspace_id == approval.workspace_id:
                comment = session.get(PublicComment, pub_act.comment_id)
                proposed_text = pub_act.text
        if comment is None and action is not None and action.target_ref:
            with contextlib.suppress(ValueError):
                cand_comment = session.get(PublicComment, uuid.UUID(action.target_ref))
                if cand_comment is not None and cand_comment.workspace_id == approval.workspace_id:
                    comment = cand_comment
        media = (
            session.get(PublicMedia, comment.media_id)
            if comment is not None and comment.media_id
            else None
        )
        headings = {
            "comment.reply": (
                "Onay İsteği: Yorum Yanıtı",
                "Approval Request: Comment Reply",
            ),
            "comment.private_reply": (
                "Onay İsteği: Yorumdan Özel Yanıt (DM)",
                "Approval Request: Private Reply to Comment",
            ),
            "comment.hide": (
                "Onay İsteği: Yorum Gizleme",
                "Approval Request: Hide Comment",
            ),
            "comment.unhide": (
                "Onay İsteği: Yorum Görünür Yapma",
                "Approval Request: Unhide Comment",
            ),
            "comment.delete": (
                "Onay İsteği: Yorum Silme",
                "Approval Request: Delete Comment",
            ),
        }
        tr_h, en_h = headings[action_type]
        lines.append(f"{sim_badge}💬 <b>{tr_h if is_tr else en_h}</b>")
        lines.append("")
        lines.append(f"• <b>{'Hesap' if is_tr else 'Account'}:</b> {html.escape(account_name)}")
        if media is not None and media.caption:
            post_label = "Gönderi" if is_tr else "Post"
            lines.append(f"• <b>{post_label}:</b> {html.escape(_clip(media.caption.strip(), 120))}")
        if comment is not None and comment.text:
            c_label = "Yorum" if is_tr else "Comment"
            lines.append(f'• <b>{c_label}:</b> <i>"{html.escape(comment.text[:200])}"</i>')
        if not proposed_text:
            raw_prop = summary.get("text") or summary.get("proposed_text")
            if isinstance(raw_prop, str) and raw_prop.strip():
                proposed_text = raw_prop.strip()
        if proposed_text:
            rep_label = "Önerilen Yanıt" if is_tr else "Proposed Reply"
            lines.append(
                f"• <b>{rep_label}:</b>\n<blockquote>{html.escape(proposed_text)}</blockquote>"
            )
        return

    # 3. Account Agent Content Actions (prepare, schedule, publish, cancel)
    if action_type in (
        "content.prepare",
        "content.schedule",
        "content.publish",
        "content.cancel",
    ):
        item = (
            session.get(ContentItem, action.payload_ref)
            if action is not None and action.payload_ref
            else None
        )
        if item is None and action is not None and action.target_ref:
            with contextlib.suppress(ValueError):
                cand_item = session.get(ContentItem, uuid.UUID(action.target_ref))
                if cand_item is not None and cand_item.workspace_id == approval.workspace_id:
                    item = cand_item
        if item is not None and item.workspace_id != approval.workspace_id:
            item = None
        intent: dict[str, Any] = (
            dict(action.content_intent)
            if action is not None and isinstance(action.content_intent, dict)
            else {}
        )
        raw_req = intent.get("request")
        req_dict: dict[str, Any] = dict(raw_req) if isinstance(raw_req, dict) else {}
        raw_payload = intent.get("payload")
        payload_dict: dict[str, Any] = dict(raw_payload) if isinstance(raw_payload, dict) else {}

        content_headings = {
            "content.prepare": (
                "Onay İsteği: Paylaşım Taslağı",
                "Approval Request: Content Draft",
            ),
            "content.schedule": (
                "Onay İsteği: Paylaşım Planı",
                "Approval Request: Content Schedule",
            ),
            "content.publish": (
                "Onay İsteği: Paylaşım Yayınlama",
                "Approval Request: Content Publication",
            ),
            "content.cancel": (
                "Onay İsteği: Paylaşım İptali",
                "Approval Request: Cancel Content",
            ),
        }
        tr_h, en_h = content_headings[action_type]
        lines.append(f"{sim_badge}📸 <b>{tr_h if is_tr else en_h}</b>")
        lines.append("")
        lines.append(f"• <b>{'Hesap' if is_tr else 'Account'}:</b> {html.escape(account_name)}")

        raw_type = (
            (item.content_type if item is not None else None)
            or payload_dict.get("content_type")
            or req_dict.get("content_type")
            or summary.get("content_type")
        )
        if isinstance(raw_type, str) and raw_type.strip():
            c_type = raw_type.replace("_", " ").title()
            lines.append(f"• <b>{'Tür' if is_tr else 'Type'}:</b> {html.escape(c_type)}")

        raw_title = (
            (item.title if item is not None and item.title else None)
            or req_dict.get("title")
            or summary.get("title")
        )
        if isinstance(raw_title, str) and raw_title.strip():
            lines.append(
                f"• <b>{'Başlık' if is_tr else 'Title'}:</b> {html.escape(raw_title.strip())}"
            )

        raw_caption = (
            (item.caption if item is not None and item.caption else None)
            or intent.get("rendered_caption")
            or payload_dict.get("caption")
            or summary.get("caption")
        )
        if isinstance(raw_caption, str) and raw_caption.strip():
            cap_label = "Açıklama" if is_tr else "Caption"
            escaped_cap = html.escape(raw_caption.strip())
            lines.append(f"• <b>{cap_label}:</b>\n<blockquote>{escaped_cap}</blockquote>")

        sched_str: str | None = None
        if item is not None and item.scheduled_at is not None:
            sched_str = _format_time_tz(item.scheduled_at, recipient.timezone)
        else:
            raw_sched = payload_dict.get("scheduled_at") or summary.get("scheduled_at")
            if isinstance(raw_sched, str) and raw_sched.strip():
                with contextlib.suppress(ValueError):
                    parsed_dt = datetime.fromisoformat(raw_sched.replace("Z", "+00:00"))
                    sched_str = _format_time_tz(parsed_dt, recipient.timezone)
                if sched_str is None:
                    sched_str = raw_sched.strip()
        if sched_str:
            time_label = "Planlanan Zaman" if is_tr else "Scheduled Time"
            lines.append(f"• <b>{time_label}:</b> {html.escape(sched_str)}")
        return

    # 4. Account Agent Calendar Actions (calendar.book, calendar.reschedule, calendar.cancel)
    if action_type in ("calendar.book", "calendar.reschedule", "calendar.cancel"):
        cal_intent: dict[str, Any] = (
            dict(action.content_intent)
            if action is not None and isinstance(action.content_intent, dict)
            else {}
        )
        appt = (
            session.get(CalendarAppointment, action.payload_ref)
            if action is not None and action.payload_ref
            else None
        )
        if appt is not None and appt.workspace_id != approval.workspace_id:
            appt = None

        cal_headings = {
            "calendar.book": (
                "Onay İsteği: Randevu Oluşturma",
                "Approval Request: Book Appointment",
            ),
            "calendar.reschedule": (
                "Onay İsteği: Randevu Değişikliği",
                "Approval Request: Reschedule Appointment",
            ),
            "calendar.cancel": (
                "Onay İsteği: Randevu İptali",
                "Approval Request: Cancel Appointment",
            ),
        }
        tr_h, en_h = cal_headings[action_type]
        lines.append(f"{sim_badge}📅 <b>{tr_h if is_tr else en_h}</b>")
        lines.append("")
        lines.append(f"• <b>{'Hesap' if is_tr else 'Account'}:</b> {html.escape(account_name)}")

        appt_title = (
            cal_intent.get("title")
            or summary.get("title")
            or (appt.title if appt is not None else None)
        )
        if isinstance(appt_title, str) and appt_title.strip():
            t_label = "Hizmet / Başlık" if is_tr else "Service / Title"
            lines.append(f"• <b>{t_label}:</b> {html.escape(appt_title.strip())}")

        cust_name = (
            cal_intent.get("customer_name")
            or summary.get("customer_name")
            or (appt.customer_name if appt is not None else None)
        )
        cust_contact = cal_intent.get("customer_contact") or (
            appt.customer_contact if appt is not None else None
        )
        if isinstance(cust_name, str) and cust_name.strip():
            c_label = "Müşteri" if is_tr else "Customer"
            c_val = cust_name.strip()
            if (
                isinstance(cust_contact, str)
                and cust_contact.strip()
                and cust_contact.strip().lstrip("@") != c_val.lstrip("@")
            ):
                c_val = f"{c_val} ({cust_contact.strip()})"
            lines.append(f"• <b>{c_label}:</b> {html.escape(c_val)}")

        local_date = cal_intent.get("local_date") or summary.get("local_date")
        local_time = cal_intent.get("local_time") or summary.get("local_time")
        tz_label = (
            cal_intent.get("timezone")
            or summary.get("timezone")
            or (appt.timezone if appt is not None else None)
            or recipient.timezone
        )
        new_when = (
            f"{local_date} {local_time}".strip()
            if (local_date or local_time)
            else (_format_time_tz(appt.start_at, str(tz_label)) if appt is not None else "")
        )
        if new_when:
            dt_label = "Tarih / Saat" if is_tr else "Date / Time"
            if action_type == "calendar.reschedule" and appt is not None:
                old_when = _format_time_tz(appt.start_at, str(tz_label))
                if old_when != new_when:
                    new_when = f"{old_when} → {new_when}"
            if isinstance(tz_label, str) and tz_label.strip():
                new_when = f"{new_when} ({tz_label.strip()})"
            lines.append(f"• <b>{dt_label}:</b> {html.escape(new_when)}")

        duration = cal_intent.get("duration_minutes") or summary.get("duration_minutes")
        if isinstance(duration, int) and duration > 0:
            d_label = "Süre" if is_tr else "Duration"
            d_unit = "dk" if is_tr else "min"
            lines.append(f"• <b>{d_label}:</b> {duration} {d_unit}")

        note_or_reason = cal_intent.get("reason") or cal_intent.get("description")
        if isinstance(note_or_reason, str) and note_or_reason.strip():
            n_label = "Not / Neden" if is_tr else "Notes / Reason"
            lines.append(f"• <b>{n_label}:</b> {html.escape(note_or_reason.strip())}")
        return

    # Fallback for any other agent_action
    req_label = "Onay İsteği" if is_tr else "Approval Request"
    lines.append(f"{sim_badge}⚡ <b>{req_label}: {html.escape(action_type)}</b>")
    lines.append("")
    lines.append(f"• <b>{'Hesap' if is_tr else 'Account'}:</b> {html.escape(account_name)}")
    for k, v in summary.items():
        if k not in ("payload_hash", "action_type"):
            lines.append(f"• <b>{html.escape(str(k))}:</b> {html.escape(str(v))}")


def _send_with_ledger_fence(
    client: TelegramClient,
    session: Session,
    clock: Clock,
    delivery: NotificationDelivery,
    *,
    chat_id: str,
    text: str,
    reply_markup: dict[str, Any] | None = None,
    extra: dict[str, Any] | None = None,
) -> DeliveryResult:
    """Commit the ``send_state='sending'`` marker and any minted tokens before the HTTP call.

    Guarantees:
    - No DB transaction is open while calling Telegram (INV: no external call in a DB transaction).
    - Single-use action tokens exist in Postgres before Telegram can deliver the inline buttons.
    - A transport timeout, a 2xx response missing ``message_id``, or a crash after ``send_message``
      is recorded as ``ambiguous`` (terminal) and is never blindly resent.
    - Explicit HTTP 429 or 5xx responses leave ``send_state='not_sent'`` and mark ``retryable=True``
      for worker backoff.
    """
    extra_meta = dict(extra or {})
    previous = dict(delivery.delivery_metadata or {})
    delivery.delivery_metadata = {
        **previous,
        "send_state": "sending",
        "send_started_at": clock.now().isoformat(),
        **extra_meta,
    }
    session.commit()

    try:
        res = client.send_message(
            chat_id=chat_id,
            text=text,
            parse_mode="HTML",
            reply_markup=reply_markup,
        )
    except TelegramApiError as exc:
        code = exc.error_code if isinstance(exc.error_code, int) else exc.status_code
        _log.warning("telegram_send_failed status=%s code=%s", exc.status_code, code)
        if exc.ambiguous:
            return _terminal(
                "telegram_send_ambiguous",
                ambiguous=True,
                send_state="ambiguous",
                **extra_meta,
            )
        if exc.retryable:
            return DeliveryResult(
                success=False,
                status="failed",
                error_message=f"telegram_retryable:{code}",
                metadata={"retryable": True, "send_state": "not_sent", **extra_meta},
            )
        reason = f"telegram_rejected:{code}" if code is not None else str(exc)
        return _terminal(reason, send_state="not_sent", **extra_meta)
    except Exception:
        _log.warning("telegram_send_unexpected_error")
        return _terminal(
            "telegram_send_ambiguous",
            ambiguous=True,
            send_state="ambiguous",
            **extra_meta,
        )

    msg_id = (
        str(res.get("message_id")).strip()
        if isinstance(res, dict) and res.get("message_id") is not None
        else ""
    )
    if not msg_id:
        return _terminal(
            "telegram_send_ambiguous",
            ambiguous=True,
            send_state="ambiguous",
            **extra_meta,
        )

    return DeliveryResult(
        success=True,
        status="delivered",
        delivered_at=clock.now(),
        external_message_id=msg_id,
        metadata={"send_state": "sent", "message_id": msg_id, **extra_meta},
    )


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
        return _terminal("Recipient missing Telegram chat ID", send_state="not_sent")

    if approval.workspace_id != delivery.workspace_id:
        return _terminal("approval_not_found", send_state="not_sent")
    if approval.status != "pending" or approval.expires_at <= clock.now():
        return _terminal("approval_not_pending", send_state="not_sent")

    # 1. Resolve workspace, user and member context to generate single-use action tokens
    workspace = session.get(Workspace, delivery.workspace_id)
    user = session.get(User, recipient.user_id)
    if workspace is None or user is None or not user.is_active:
        return _terminal(
            "Workspace or user missing for approval notification", send_state="not_sent"
        )

    member = session.scalar(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == workspace.id,
            WorkspaceMember.user_id == user.id,
        )
    )
    if member is None:
        return _terminal("Recipient is no longer a workspace member", send_state="not_sent")
    role = member.role
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
        from app.inbox.models import Conversation, ReplyDraft
        from app.integrations.instagram.models import SocialAccount

        draft = session.get(ReplyDraft, approval.subject_id)
        conv = session.get(Conversation, draft.conversation_id) if draft else None
        account = session.get(SocialAccount, conv.social_account_id) if conv else None
        _append_reply_draft_lines(
            session,
            lines,
            draft=draft,
            conv=conv,
            account=account,
            approval=approval,
            recipient=recipient,
            is_tr=is_tr,
            sim_badge=sim_badge,
        )

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

    elif approval.subject_type == "agent_action":
        _append_agent_action_lines(
            session,
            lines,
            approval=approval,
            recipient=recipient,
            is_tr=is_tr,
            sim_badge=sim_badge,
        )

    elif approval.action == "command.make_price_card":
        heading = "Fiyat kartı oluştur" if is_tr else "Make a price card"
        lines.append(f"{sim_badge}<b>{heading}</b>")
        lines.append(html.escape(str(approval.summary.get("label", ""))))
        lines.append(html.escape(str(approval.summary.get("price_formatted", ""))))
        lines.append("Yalnızca taslak oluşturulur." if is_tr else "Creates a draft only.")
    elif approval.action in ("command.reschedule_content", "command.pause_agent"):
        pause = approval.action == "command.pause_agent"
        heading = (
            ("Asistanı duraklat" if is_tr else "Pause assistant")
            if pause
            else ("İçerik zamanını değiştir" if is_tr else "Reschedule content")
        )
        lines.append(f"{sim_badge}<b>{heading}</b>")
        summary = approval.summary
        if pause:
            label = "Devam zamanı" if is_tr else "Resume at"
            lines.append(f"{label}: {html.escape(str(summary.get('resume_at', '')))}")
        else:
            lines.append(html.escape(str(summary.get("label", ""))))
            lines.append(
                f"{html.escape(str(summary.get('old_formatted', '')))} → "
                f"{html.escape(str(summary.get('new_formatted', '')))}"
            )
        lines.append(html.escape(str(summary.get("timezone", ""))))
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

    return _send_with_ledger_fence(
        client,
        session,
        clock,
        delivery,
        chat_id=str(chat_id),
        text=text,
        reply_markup=reply_markup,
        extra={"approval_id": str(approval.id)},
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
        return _terminal("Recipient missing Telegram chat ID", send_state="not_sent")

    if question.workspace_id != delivery.workspace_id:
        return _terminal("question_not_found", send_state="not_sent")

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
    q_ref = f"Q-{str(question.id)[:8]}"
    title = f"{sim_badge}❓ <b>{q_heading}</b>"
    q_body = html.escape(question.body or "")
    lines = [
        title,
        "",
        f"• <b>{'Hesap' if is_tr else 'Account'}:</b> {html.escape(account_name)}",
        f"• <b>{'Kategori' if is_tr else 'Category'}:</b> {html.escape(category)}",
        f"• <b>{'Referans' if is_tr else 'Ref'}:</b> <code>{q_ref}</code>",
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

    return _send_with_ledger_fence(
        client,
        session,
        clock,
        delivery,
        chat_id=str(chat_id),
        text=text,
        reply_markup=reply_markup,
        extra={"question_id": str(question.id)},
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
        previous = dict(delivery.delivery_metadata or {})
        if previous.get("send_state") == "sending":
            return _terminal(
                "telegram_send_state_unknown",
                ambiguous=True,
                send_state="ambiguous",
            )

        notification = session.get(Notification, delivery.notification_id)
        if notification is None:
            return _terminal(
                f"Notification record not found: {delivery.notification_id}",
                send_state="not_sent",
            )
        if (
            notification.workspace_id != delivery.workspace_id
            or notification.recipient_user_id != recipient.user_id
        ):
            return _terminal("notification_not_found", send_state="not_sent")

        if delivery.channel_link_id is not None:
            link = session.get(ChannelLink, delivery.channel_link_id)
            if (
                link is None
                or link.workspace_id != delivery.workspace_id
                or link.user_id != recipient.user_id
                or link.channel != "telegram"
                or link.status != "active"
            ):
                return _terminal("recipient_not_linked", send_state="not_sent")

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
            return _terminal("Recipient missing Telegram chat ID", send_state="not_sent")

        if notification.type in QUOTA_TEXT:
            locale = "tr" if (recipient.ui_locale or "tr").lower().startswith("tr") else "en"
            title, body = QUOTA_TEXT[notification.type][locale]
            text = f"<b>{title}</b>\n\n{body}"
        else:
            text = _format_notification_text(notification, recipient.ui_locale)

        return _send_with_ledger_fence(
            self.client,
            session,
            clock,
            delivery,
            chat_id=str(chat_id),
            text=text,
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

        from app.integrations.channels.formatting import format_command_for_telegram

        text, reply_markup = format_command_for_telegram(command, recipient)
        with contextlib.suppress(Exception):
            self.client.send_message(
                chat_id=chat_id,
                text=text,
                parse_mode="HTML",
                reply_markup=reply_markup,
            )
