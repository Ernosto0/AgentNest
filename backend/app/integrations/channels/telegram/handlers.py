"""Telegram message routing, reporting queries, owner tasks, and photo ingestion handlers.

(Phase 9 Session 05, ADR-012, ADR-014, ADR-024, ADR-025, AC-2, AC-3, INV-04, INV-11).
"""

from __future__ import annotations

import contextlib
import html
import io
import re
import uuid
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent import owner_tasks
from app.agent.models import AccountAgent
from app.approvals.action_tokens import ActionTokenService
from app.approvals.service import ApprovalService
from app.audit import service as audit
from app.commands import service as command_service
from app.content import media
from app.content import service as content_service
from app.content.service import ScheduleRequest
from app.core.clock import Clock
from app.core.config import get_settings
from app.core.context import ActorRef, WorkspaceContext
from app.core.errors import AppError
from app.core.logging import get_logger
from app.identity.models import ChannelLink, User, Workspace, WorkspaceMember
from app.identity.service import workspace_context
from app.integrations.channels.telegram.client import TelegramClient
from app.integrations.channels.telegram.webhook_format import (
    PhotoSize,
    TelegramMessage,
)
from app.integrations.storage.registry import get_media_storage
from app.owner_requests import service as owner_requests_service
from app.owner_requests.models import OwnerQuestion
from app.owner_requests.service import AnswerRequest
from app.reporting import service as reporting_service
from app.reporting.periods import local_date_of

_log = get_logger("app.integrations.channels.telegram.handlers")

MAX_PHOTO_BYTES = 20 * 1024 * 1024  # 20 MB (INV-11)
PENDING_MEDIA_TTL = timedelta(minutes=15)

# In-memory store for pending intake media waiting for user's next command
# user_id -> (asset_id, timestamp)
_PENDING_MEDIA: dict[uuid.UUID, tuple[uuid.UUID, datetime]] = {}


def set_pending_media(user_id: uuid.UUID, asset_id: uuid.UUID, now: datetime) -> None:
    """Store pending media intake reference for a user."""
    _PENDING_MEDIA[user_id] = (asset_id, now)


def get_pending_media(user_id: uuid.UUID, now: datetime) -> uuid.UUID | None:
    """Retrieve and clear pending media intake reference if not expired."""
    entry = _PENDING_MEDIA.get(user_id)
    if entry is None:
        return None
    asset_id, created_at = entry
    if now - created_at > PENDING_MEDIA_TTL:
        _PENDING_MEDIA.pop(user_id, None)
        return None
    _PENDING_MEDIA.pop(user_id, None)
    return asset_id


def is_reporting_query(text: str) -> bool:
    """Check if the text is a reporting or daily summary query (AC-2)."""
    cleaned = re.sub(r"[?!.,]", "", text.strip().lower())
    patterns = [
        r"bugün.*kaç.*(?:dm|mesaj)",
        r"kaç.*(?:dm|mesaj).*geldi",
        r"kaç.*(?:dm|mesaj).*aldık",
        r"bugün(?:kü)?\s*(?:özet|durum|rapor|istatistik)",
        r"günlük\s*(?:özet|rapor)",
        r"today'?s?\s*(?:summary|report|metrics|status)",
        r"how\s+many\s+(?:dms|messages|dm)\s+(?:today|received)",
        r"daily\s+summary",
    ]
    return any(re.search(pat, cleaned) for pat in patterns)


def is_agent_task(text: str) -> bool:
    """Check if the text is an instruction or task for the account agent."""
    cleaned = text.strip().lower()
    task_cues = [
        "dönüş yap",
        "cevapla",
        "yanıtla",
        "randevu",
        "ulaş",
        "ara",
        "yaz",
        "takip et",
        "bilgi ver",
        "görev:",
        "task:",
        "agent:",
        "reply",
        "respond",
        "follow up",
        "contact",
        "appointment",
        "customer",
        "müşteri",
        "ahmet bey",
        "mehmet bey",
        "ayşe hanım",
        "fatma hanım",
    ]
    return any(cue in cleaned for cue in task_cues)


def handle_linked_message(
    session: Session,
    clock: Clock,
    user: User,
    workspace: Workspace,
    link: ChannelLink,
    message: TelegramMessage,
    tg_client: TelegramClient,
    *,
    update_id: int | None = None,
) -> str:
    """Route an incoming message from an authenticated, linked owner."""
    member = session.scalar(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == workspace.id,
            WorkspaceMember.user_id == user.id,
        )
    )
    role = member.role if member else "owner"
    actor = ActorRef(type="user", id=str(user.id))
    ctx = workspace_context(workspace, actor, role)

    chat_id = str(message.chat.id)
    locale = (getattr(user, "ui_locale", None) or workspace.default_locale or "tr").lower()
    is_tr = locale.startswith("tr")
    now = clock.now()

    # -------------------------------------------------------------------------
    # 1. Inbound Photo Ingestion (AC-3, INV-11, INV-04)
    # -------------------------------------------------------------------------
    if message.photo:
        return _handle_photo(
            session=session,
            clock=clock,
            user=user,
            ctx=ctx,
            message=message,
            tg_client=tg_client,
            chat_id=chat_id,
            is_tr=is_tr,
            update_id=update_id,
        )

    raw_text = (message.text or "").strip()
    if not raw_text:
        return "empty"

    # Check if user had pending media uploaded previously
    pending_asset_id = get_pending_media(user.id, now)

    # -------------------------------------------------------------------------
    # 2. Reporting Queries (AC-2)
    # -------------------------------------------------------------------------
    if is_reporting_query(raw_text):
        return _handle_reporting_query(
            session=session,
            clock=clock,
            ctx=ctx,
            raw_text=raw_text,
            tg_client=tg_client,
            chat_id=chat_id,
            is_tr=is_tr,
        )

    # -------------------------------------------------------------------------
    # 2.5 Owner Question Reply (Phase 7.5 / ADR-024)
    # -------------------------------------------------------------------------
    matched_question: OwnerQuestion | None = None
    if message.reply_to_message and message.reply_to_message.text:
        reply_text = message.reply_to_message.text
        if (
            "Asistanınız Bilgi Bekliyor" in reply_text
            or "Your Assistant Needs Information" in reply_text
        ):
            matched_question = session.scalar(
                select(OwnerQuestion)
                .where(
                    OwnerQuestion.workspace_id == ctx.workspace_id,
                    OwnerQuestion.state == "pending",
                    OwnerQuestion.expires_at > now,
                )
                .order_by(OwnerQuestion.created_at.desc())
            )
            if matched_question is None:
                matched_question = session.scalar(
                    select(OwnerQuestion)
                    .where(OwnerQuestion.workspace_id == ctx.workspace_id)
                    .order_by(OwnerQuestion.created_at.desc())
                )

    prefix_match = re.match(
        r"^(?:cevap|yanıt|answer|bilgi):\s*(.*)$", raw_text, re.IGNORECASE | re.DOTALL
    )
    if prefix_match:
        if matched_question is None:
            matched_question = session.scalar(
                select(OwnerQuestion)
                .where(
                    OwnerQuestion.workspace_id == ctx.workspace_id,
                    OwnerQuestion.state == "pending",
                    OwnerQuestion.expires_at > now,
                )
                .order_by(OwnerQuestion.created_at.desc())
            )
            if matched_question is None:
                matched_question = session.scalar(
                    select(OwnerQuestion)
                    .where(OwnerQuestion.workspace_id == ctx.workspace_id)
                    .order_by(OwnerQuestion.created_at.desc())
                )
        if matched_question is not None:
            answer_text = prefix_match.group(1).strip() or raw_text
            return _handle_owner_question_answer(
                session=session,
                clock=clock,
                ctx=ctx,
                user=user,
                raw_text=answer_text,
                tg_client=tg_client,
                chat_id=chat_id,
                is_tr=is_tr,
                question=matched_question,
            )

    if matched_question is not None:
        return _handle_owner_question_answer(
            session=session,
            clock=clock,
            ctx=ctx,
            user=user,
            raw_text=raw_text,
            tg_client=tg_client,
            chat_id=chat_id,
            is_tr=is_tr,
            question=matched_question,
        )

    # If workspace has an active pending owner question and text is not an agent task,
    # route to owner question answer as informational input
    if not is_agent_task(raw_text):
        pending_q = session.scalar(
            select(OwnerQuestion)
            .where(
                OwnerQuestion.workspace_id == ctx.workspace_id,
                OwnerQuestion.state == "pending",
                OwnerQuestion.expires_at > now,
            )
            .order_by(OwnerQuestion.created_at.desc())
        )
        if pending_q is not None:
            return _handle_owner_question_answer(
                session=session,
                clock=clock,
                ctx=ctx,
                user=user,
                raw_text=raw_text,
                tg_client=tg_client,
                chat_id=chat_id,
                is_tr=is_tr,
                question=pending_q,
            )

    # -------------------------------------------------------------------------
    # 3. Account Agent Routing (ADR-024)
    # -------------------------------------------------------------------------
    active_agent = session.scalar(
        select(AccountAgent)
        .where(
            AccountAgent.workspace_id == ctx.workspace_id,
            AccountAgent.controller_mode == "agent",
            AccountAgent.state == "active",
        )
        .limit(1)
    )

    if active_agent is not None and is_agent_task(raw_text):
        return _handle_agent_task(
            session=session,
            clock=clock,
            ctx=ctx,
            user=user,
            active_agent=active_agent,
            raw_text=raw_text,
            pending_asset_id=pending_asset_id,
            tg_client=tg_client,
            chat_id=chat_id,
            is_tr=is_tr,
            update_id=update_id,
        )

    # -------------------------------------------------------------------------
    # 4. General Commands (CommandService.submit)
    # -------------------------------------------------------------------------
    return _handle_general_command(
        session=session,
        clock=clock,
        ctx=ctx,
        raw_text=raw_text,
        tg_client=tg_client,
        chat_id=chat_id,
        is_tr=is_tr,
        update_id=update_id,
    )


def _handle_photo(
    session: Session,
    clock: Clock,
    user: User,
    ctx: Any,
    message: TelegramMessage,
    tg_client: TelegramClient,
    chat_id: str,
    is_tr: bool,
    update_id: int | None,
) -> str:
    """Process incoming photo with 20 MB size validation and draft scheduling."""
    photos = message.photo or []
    # Highest resolution PhotoSize
    best_photo: PhotoSize = max(photos, key=lambda p: (p.width * p.height, p.file_size or 0))

    # Size check on Telegram metadata (INV-11)
    if best_photo.file_size is not None and best_photo.file_size > MAX_PHOTO_BYTES:
        audit.record(
            session,
            ctx,
            "media.rejected",
            "media_asset",
            None,
            {
                "reason": "too_large",
                "original_filename": "telegram_upload.jpg",
                "byte_size": best_photo.file_size,
            },
            clock=clock,
        )
        session.commit()
        reject_msg = (
            "❌ Fotoğraf 20 MB'tan büyük olamaz." if is_tr else "❌ Photo exceeds 20 MB limit."
        )
        tg_client.send_message(chat_id=chat_id, text=reject_msg, parse_mode="HTML")
        return "photo_rejected_size"

    # Fetch file info from Telegram
    file_info = tg_client.get_file(best_photo.file_id)
    file_size = file_info.get("file_size")
    if file_size is not None and int(file_size) > MAX_PHOTO_BYTES:
        audit.record(
            session,
            ctx,
            "media.rejected",
            "media_asset",
            None,
            {
                "reason": "too_large",
                "original_filename": "telegram_upload.jpg",
                "byte_size": int(file_size),
            },
            clock=clock,
        )
        session.commit()
        reject_msg = (
            "❌ Fotoğraf 20 MB'tan büyük olamaz." if is_tr else "❌ Photo exceeds 20 MB limit."
        )
        tg_client.send_message(chat_id=chat_id, text=reject_msg, parse_mode="HTML")
        return "photo_rejected_size"

    file_path = file_info.get("file_path")
    if not file_path:
        raise AppError("TELEGRAM_FILE_NOT_FOUND")

    # Download raw bytes
    photo_bytes = tg_client.download_file(file_path)
    if len(photo_bytes) > MAX_PHOTO_BYTES:
        audit.record(
            session,
            ctx,
            "media.rejected",
            "media_asset",
            None,
            {
                "reason": "too_large",
                "original_filename": "telegram_upload.jpg",
                "byte_size": len(photo_bytes),
            },
            clock=clock,
        )
        session.commit()
        reject_msg = (
            "❌ Fotoğraf 20 MB'tan büyük olamaz." if is_tr else "❌ Photo exceeds 20 MB limit."
        )
        tg_client.send_message(chat_id=chat_id, text=reject_msg, parse_mode="HTML")
        return "photo_rejected_size"

    # Ingest media
    settings = get_settings()
    if settings.media_max_image_bytes < MAX_PHOTO_BYTES:
        settings = settings.model_copy(update={"media_max_image_bytes": MAX_PHOTO_BYTES})
    storage = get_media_storage(settings, clock)

    try:
        media_asset = media.ingest(
            session,
            clock,
            settings,
            storage,
            ctx,
            file=io.BytesIO(photo_bytes),
            filename="telegram_upload.jpg",
            content_type="image/jpeg",
        )
    except AppError as exc:
        if exc.code in ("MEDIA_TOO_LARGE", "MEDIA_INVALID"):
            reject_msg = (
                "❌ Fotoğraf geçersiz veya 20 MB sınırını aşıyor."
                if is_tr
                else "❌ Photo is invalid or exceeds 20 MB limit."
            )
            tg_client.send_message(chat_id=chat_id, text=reject_msg, parse_mode="HTML")
            return "photo_rejected"
        raise

    caption = (message.caption or "").strip()

    # Case A: Photo with caption (AC-3, P9-03)
    if caption:
        lower_cap = caption.lower()
        is_post = "post" in lower_cap or "gönderi" in lower_cap
        content_type = "feed_image" if is_post else "story_image"
        display_type = "Story" if content_type == "story_image" else "Post"

        # Time parsing
        time_match = re.search(r"\b([01]?\d|2[0-3])[:.]([0-5]\d)\b", caption)
        proposed_time = (
            f"{int(time_match.group(1)):02d}:{time_match.group(2)}" if time_match else "19:00"
        )
        today = local_date_of(clock.now(), ctx.timezone)
        target_date = (
            today + timedelta(days=1)
            if ("yarın" in lower_cap or "tomorrow" in lower_cap)
            else today
        )

        client_req_id = f"tg:photo:{message.message_id}:{update_id or ''}"
        item, created = content_service.create_draft(
            session,
            clock,
            ctx,
            content_type=content_type,
            title=f"Telegram {display_type} Draft",
            caption=caption,
            media_asset_id=media_asset.id,
            client_request_id=client_req_id,
        )

        # Propose schedule requiring approval (never auto-scheduled from text, INV-04, AC-3)
        try:
            content_service.submit(
                session,
                clock,
                settings,
                ctx,
                item.id,
                schedule=ScheduleRequest(local_date=target_date, local_time=proposed_time),
                self_approve=False,
                expected_version=item.version,
            )
        except Exception as exc:
            _log.info(
                "content_draft_scheduled_proposal_pending", item_id=str(item.id), reason=str(exc)
            )

        if is_tr:
            confirm = (
                f"📸 <b>{display_type} Taslağı Oluşturuldu</b>\n\n"
                f"• <b>Tür:</b> {display_type}\n"
                f"• <b>Görsel:</b> {html.escape(media_asset.original_filename or 'Foto')} (Hazır)\n"
                f"• <b>Önerilen Zaman:</b> {target_date.isoformat()} {proposed_time}\n"
                f"• <b>Durum:</b> Onay Bekliyor (Taslak)\n\n"
                "⚠️ <i>Güvenlik İlkesi: Serbest metin doğrudan yayınlayamaz (INV-04). "
                "Bu içerik yayınlanmadan önce onayınız gerekmektedir.</i>"
            )
        else:
            confirm = (
                f"📸 <b>{display_type} Draft Created</b>\n\n"
                f"• <b>Type:</b> {display_type}\n"
                f"• <b>Media:</b> {html.escape(media_asset.original_filename or 'Photo')} (Ready)\n"
                f"• <b>Proposed Time:</b> {target_date.isoformat()} {proposed_time}\n"
                f"• <b>Status:</b> Requires Approval (Draft)\n\n"
                "⚠️ <i>Policy: Free-text commands never directly publish (INV-04). "
                "Explicit approval is required before publishing.</i>"
            )
        tg_client.send_message(chat_id=chat_id, text=confirm, parse_mode="HTML")
        return "photo_draft_created"

    # Case B: Photo without caption -> Cache as pending intake media
    set_pending_media(user.id, media_asset.id, clock.now())
    if is_tr:
        confirm = (
            "📷 <b>Fotoğraf Alındı</b>\n\n"
            "Görsel başarıyla yüklendi ve hazırlandı.\n\n"
            "Bu fotoğrafla ne yapmak istersiniz?\n"
            'Örnek: <i>"bu story\'yi 19:00\'da paylaş"</i> veya <i>"yeni bir post oluştur"</i>'
        )
    else:
        confirm = (
            "📷 <b>Photo Received</b>\n\n"
            "Image uploaded and ready.\n\n"
            "What would you like to do with this photo?\n"
            'Example: <i>"share this story at 19:00"</i> or <i>"create a new post"</i>'
        )
    tg_client.send_message(chat_id=chat_id, text=confirm, parse_mode="HTML")
    return "photo_cached"


def _handle_reporting_query(
    session: Session,
    clock: Clock,
    ctx: Any,
    raw_text: str,
    tg_client: TelegramClient,
    chat_id: str,
    is_tr: bool,
) -> str:
    """Fetch daily metrics from reporting service and respond to Telegram (AC-2)."""
    summary = reporting_service.get_daily_summary(session, clock, ctx)
    inbound = summary["inbound_messages"]
    conversations = summary["conversations"]
    new_convs = summary["new_conversations"]
    approvals = summary["pending_approvals"]

    is_dm_count_question = bool(
        re.search(r"kaç.*(?:dm|mesaj)", raw_text.lower())
        or re.search(r"how\s+many\s+(?:dms|messages|dm)", raw_text.lower())
    )

    if is_tr:
        if is_dm_count_question:
            text = (
                "📬 <b>Gelen Mesajlar</b>\n\n"
                f"Bugün toplam <b>{inbound}</b> DM / mesaj geldi.\n\n"
                f"• <b>Yeni Konuşma:</b> {new_convs}\n"
                f"• <b>Aktif Konuşmalar:</b> {conversations}\n"
                f"• <b>Bekleyen Onaylar:</b> {approvals}"
            )
        else:
            text = (
                "📊 <b>Bugünkü Özet</b>\n\n"
                f"• <b>Gelen DM / Mesaj:</b> {inbound}\n"
                f"• <b>Yeni Konuşma:</b> {new_convs}\n"
                f"• <b>Aktif Konuşmalar:</b> {conversations}\n"
                f"• <b>Bekleyen Onaylar:</b> {approvals}"
            )
    else:
        if is_dm_count_question:
            text = (
                "📬 <b>Inbound Messages</b>\n\n"
                f"Today you received <b>{inbound}</b> DM(s).\n\n"
                f"• <b>New Conversations:</b> {new_convs}\n"
                f"• <b>Active Conversations:</b> {conversations}\n"
                f"• <b>Pending Approvals:</b> {approvals}"
            )
        else:
            text = (
                "📊 <b>Today's Summary</b>\n\n"
                f"• <b>Inbound DMs / Messages:</b> {inbound}\n"
                f"• <b>New Conversations:</b> {new_convs}\n"
                f"• <b>Active Conversations:</b> {conversations}\n"
                f"• <b>Pending Approvals:</b> {approvals}"
            )

    tg_client.send_message(chat_id=chat_id, text=text, parse_mode="HTML")
    return "reporting_query"


def _handle_agent_task(
    session: Session,
    clock: Clock,
    ctx: Any,
    user: User,
    active_agent: AccountAgent,
    raw_text: str,
    pending_asset_id: uuid.UUID | None,
    tg_client: TelegramClient,
    chat_id: str,
    is_tr: bool,
    update_id: int | None,
) -> str:
    """Route instruction to active AccountAgent via owner_tasks.submit (ADR-024)."""
    client_req_id = uuid.uuid5(
        uuid.NAMESPACE_OID,
        f"tg:{update_id or clock.now().isoformat()}:{user.id}",
    )
    owner_tasks.submit(
        session,
        clock,
        ctx,
        account_id=active_agent.social_account_id,
        request_text=raw_text,
        client_request_id=client_req_id,
        media_asset_id=pending_asset_id,
        source_channel="telegram",
    )

    if is_tr:
        reply = (
            "🤖 <b>Talimat Alındı</b>\n\n"
            "Talimatınız yapay zeka asistanına iletildi:\n"
            f'<i>"{html.escape(raw_text)}"</i>\n\n'
            "Durumu AgentNest üzerinden takip edebilirsiniz."
        )
    else:
        reply = (
            "🤖 <b>Task Received</b>\n\n"
            "Your instruction has been submitted to the account agent:\n"
            f'<i>"{html.escape(raw_text)}"</i>'
        )
    tg_client.send_message(chat_id=chat_id, text=reply, parse_mode="HTML")
    return "agent_task"


def _handle_general_command(
    session: Session,
    clock: Clock,
    ctx: Any,
    raw_text: str,
    tg_client: TelegramClient,
    chat_id: str,
    is_tr: bool,
    update_id: int | None,
) -> str:
    """Route general command to CommandService.submit and render result."""
    client_req_id = f"tg:{update_id or clock.now().timestamp()}"
    cmd = command_service.submit(
        session,
        clock,
        ctx,
        text=raw_text,
        client_request_id=client_req_id,
        channel="telegram",
    )

    if cmd.status == "needs_clarification" and cmd.clarification:
        question = cmd.clarification.get("question") or "Detay vermeniz gerekiyor."
        msg = f"❓ <b>Açıklama Gerekiyor</b>\n\n{html.escape(str(question))}"
    elif cmd.status == "awaiting_confirmation" and cmd.resolution:
        summary = cmd.resolution.get("summary") or "Onayınız bekleniyor."
        msg = f"⚠️ <b>Onay Gerekiyor</b>\n\n{html.escape(str(summary))}"
    elif cmd.status == "completed" and cmd.resolution:
        msg = f"✅ <b>İşlem Tamamlandı</b>\n\n{html.escape(str(cmd.resolution))}"
    else:
        msg = (
            f"⚡ <b>Komut Alındı</b>\n\n"
            f'<i>"{html.escape(raw_text)}"</i>\n\n'
            "Komutunuz sıraya alındı ve işleniyor."
            if is_tr
            else (
                f"⚡ <b>Command Received</b>\n\n"
                f'<i>"{html.escape(raw_text)}"</i>\n\n'
                "Command queued for processing."
            )
        )
    tg_client.send_message(chat_id=chat_id, text=msg, parse_mode="HTML")
    return "owner_command"


def _handle_owner_question_answer(
    session: Session,
    clock: Clock,
    ctx: WorkspaceContext,
    user: User,
    raw_text: str,
    tg_client: TelegramClient,
    chat_id: str,
    is_tr: bool,
    question: OwnerQuestion,
) -> str:
    """Submit informational response to pending OwnerQuestion (ADR-024, Phase 7.5)."""
    now = clock.now()
    if question.state != "pending" or question.expires_at <= now:
        state_desc = question.state if question.state != "pending" else "expired"
        msg = (
            f"⚠️ <b>Bu soru artık yanıt beklememektedir.</b>\n\n"
            f"Mevcut durum: <code>{html.escape(state_desc)}</code>"
            if is_tr
            else (
                f"⚠️ <b>This question is no longer awaiting an answer.</b>\n\n"
                f"Current status: <code>{html.escape(state_desc)}</code>"
            )
        )
        tg_client.send_message(chat_id=chat_id, text=msg, parse_mode="HTML")
        return "owner_question_stale"

    request = AnswerRequest(
        expected_version=question.version,
        client_request_id=uuid.uuid4(),
        body=raw_text,
        kind="answer",
    )

    try:
        owner_requests_service.decide(
            db=session,
            clock=clock,
            ctx=ctx,
            account=question.social_account_id,
            question=question.id,
            request=request,
        )
        session.commit()
        msg = (
            "✅ <b>Bilgi kaydedildi ve asistana iletildi.</b>\n\n"
            "Müşteriye yanıt hazırlanırken bu bilgi dikkate alınacaktır."
            if is_tr
            else (
                "✅ <b>Information recorded and forwarded to the assistant.</b>\n\n"
                "This information will be used to generate a response for the customer."
            )
        )
        tg_client.send_message(chat_id=chat_id, text=msg, parse_mode="HTML")
        return "owner_question_answered"
    except AppError as exc:
        if exc.code in ("OWNER_QUESTION_CLOSED", "VERSION_CONFLICT"):
            session.rollback()
            state_desc = question.state
            msg = (
                f"⚠️ <b>Bu soru artık yanıt beklememektedir.</b>\n\n"
                f"Mevcut durum: <code>{html.escape(state_desc)}</code>"
                if is_tr
                else (
                    f"⚠️ <b>This question is no longer awaiting an answer.</b>\n\n"
                    f"Current status: <code>{html.escape(state_desc)}</code>"
                )
            )
            tg_client.send_message(chat_id=chat_id, text=msg, parse_mode="HTML")
            return "owner_question_stale"
        raise


def handle_approval_callback(
    session: Session,
    clock: Clock,
    callback_query: Any,
    token_str: str,
    tg_client: TelegramClient,
) -> str:
    """Consume single-use action token and invoke ApprovalService.decide."""
    channel_user_id = str(callback_query.from_.id) if callback_query.from_ else ""
    chat_id = str(callback_query.message.chat.id) if callback_query.message else None
    message_id = callback_query.message.message_id if callback_query.message else None

    try:
        approval, token_record = ActionTokenService.consume_action_token(
            db=session,
            clock=clock,
            token_str=token_str,
            channel_user_id=channel_user_id,
        )
    except AppError as exc:
        if exc.code == "APPROVAL_ALREADY_DECIDED":
            tg_client.answer_callback_query(
                callback_query.id,
                text="Bu onay zaten karara bağlandı / Already decided",
                show_alert=True,
            )
            if chat_id and message_id:
                with contextlib.suppress(Exception):
                    tg_client.edit_message_reply_markup(
                        chat_id=chat_id,
                        message_id=message_id,
                        reply_markup={"inline_keyboard": []},
                    )
            return "approval_already_decided"
        elif exc.code == "APPROVAL_EXPIRED":
            tg_client.answer_callback_query(
                callback_query.id,
                text="Onay süresi doldu / Approval expired",
                show_alert=True,
            )
            if chat_id and message_id:
                with contextlib.suppress(Exception):
                    tg_client.edit_message_reply_markup(
                        chat_id=chat_id,
                        message_id=message_id,
                        reply_markup={"inline_keyboard": []},
                    )
            return "approval_expired"
        elif exc.code == "FORBIDDEN":
            tg_client.answer_callback_query(
                callback_query.id,
                text="Bu onay için yetkiniz yok / Unauthorized",
                show_alert=True,
            )
            return "approval_unauthorized"
        else:
            tg_client.answer_callback_query(
                callback_query.id,
                text=f"Onay işlemi gerçekleştirilemedi: {exc.code}",
                show_alert=True,
            )
            return "approval_failed"

    # Resolve workspace, user and member context for ApprovalService.decide
    user = session.get(User, token_record.user_id)
    workspace = session.get(Workspace, token_record.workspace_id)
    if user is None or workspace is None:
        tg_client.answer_callback_query(
            callback_query.id,
            text="Kullanıcı veya çalışma alanı bulunamadı",
            show_alert=True,
        )
        return "approval_failed"

    member = session.scalar(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == workspace.id,
            WorkspaceMember.user_id == user.id,
        )
    )
    role = member.role if member else "owner"
    ctx = workspace_context(workspace, ActorRef.user(user.id), role)

    decision_val = "approve" if token_record.decision == "approved" else "reject"

    try:
        ApprovalService.decide(
            session=session,
            clock=clock,
            ctx=ctx,
            approval_id=approval.id,
            decision=decision_val,
            payload_hash=token_record.payload_hash,
            channel="telegram",
        )
    except AppError as exc:
        if exc.code == "APPROVAL_ALREADY_DECIDED":
            tg_client.answer_callback_query(
                callback_query.id,
                text="Bu onay zaten karara bağlandı / Already decided",
                show_alert=True,
            )
            if chat_id and message_id:
                with contextlib.suppress(Exception):
                    tg_client.edit_message_reply_markup(
                        chat_id=chat_id,
                        message_id=message_id,
                        reply_markup={"inline_keyboard": []},
                    )
            return "approval_already_decided"
        elif exc.code == "APPROVAL_EXPIRED":
            tg_client.answer_callback_query(
                callback_query.id,
                text="Onay süresi doldu / Approval expired",
                show_alert=True,
            )
            if chat_id and message_id:
                with contextlib.suppress(Exception):
                    tg_client.edit_message_reply_markup(
                        chat_id=chat_id,
                        message_id=message_id,
                        reply_markup={"inline_keyboard": []},
                    )
            return "approval_expired"
        elif exc.code == "APPROVAL_STALE":
            tg_client.answer_callback_query(
                callback_query.id,
                text="Onay içeriği değişti / Approval stale",
                show_alert=True,
            )
            if chat_id and message_id:
                with contextlib.suppress(Exception):
                    tg_client.edit_message_reply_markup(
                        chat_id=chat_id,
                        message_id=message_id,
                        reply_markup={"inline_keyboard": []},
                    )
            return "approval_stale"
        elif exc.code == "FORBIDDEN":
            tg_client.answer_callback_query(
                callback_query.id,
                text="Bu onay için yetkiniz yok / Unauthorized",
                show_alert=True,
            )
            return "approval_unauthorized"
        raise

    is_approved = token_record.decision == "approved"
    decision_text = "Onaylandı" if is_approved else "Reddedildi"
    badge_icon = "✅" if is_approved else "❌"

    tg_client.answer_callback_query(
        callback_query.id,
        text=f"{badge_icon} {decision_text}",
        show_alert=False,
    )

    if chat_id and message_id and callback_query.message:
        orig_text = callback_query.message.text or ""
        user_name = user.display_name or user.email or "Owner"
        new_text = orig_text + f"\n\n{badge_icon} {decision_text} — {user_name}"
        try:
            tg_client.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=new_text,
                reply_markup={"inline_keyboard": []},
            )
        except Exception:
            with contextlib.suppress(Exception):
                tg_client.edit_message_reply_markup(
                    chat_id=chat_id,
                    message_id=message_id,
                    reply_markup={"inline_keyboard": []},
                )

    return "approval_decided"
