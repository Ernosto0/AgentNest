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

from sqlalchemy import delete, select
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
from app.core.db import get_session_factory
from app.core.errors import AppError
from app.core.logging import get_logger
from app.identity.models import ChannelLink, User, Workspace, WorkspaceMember
from app.identity.service import workspace_context
from app.integrations.channels.telegram.client import TelegramClient
from app.integrations.channels.telegram.models import TelegramPendingMedia
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

_QUESTION_REF_RE = re.compile(r"\bQ-([0-9a-f]{8})\b", re.IGNORECASE)
_QUESTION_HEADINGS = (
    "Asistanınız Bilgi Bekliyor",
    "Your Assistant Needs Information",
)
_EXPLICIT_COMMAND_TERMS = (
    "fiyat",
    "price",
    "ücret",
    "tarife",
    "çalışma saat",
    "working hours",
    "saatleri",
    "durdur",
    "duraklat",
    "pause",
    "resume",
    "devam et",
    "story",
    "gönderi",
    "yayınla",
    "publish",
    "planla",
    "schedule",
    "onayla",
    "reddet",
    "approve",
    "reject",
    "rapor",
    "özet",
    "summary",
    "status",
    "durum",
)


def _resolve_workspace_for_pending_media(
    session: Session,
    user_id: uuid.UUID,
) -> uuid.UUID | None:
    link = session.scalar(
        select(ChannelLink)
        .where(
            ChannelLink.user_id == user_id,
            ChannelLink.channel == "telegram",
            ChannelLink.status == "active",
        )
        .limit(1)
    )
    if link is not None:
        return link.workspace_id
    row = session.scalar(
        select(TelegramPendingMedia).where(TelegramPendingMedia.user_id == user_id).limit(1)
    )
    return row.workspace_id if row is not None else None


def set_pending_media(
    user_id: uuid.UUID,
    asset_id: uuid.UUID,
    now: datetime,
    *,
    session: Session | None = None,
    workspace_id: uuid.UUID | None = None,
) -> None:
    """Persist pending media intake reference in PostgreSQL across API workers."""

    def _write(db: Session) -> None:
        ws_id = workspace_id or _resolve_workspace_for_pending_media(db, user_id)
        if ws_id is None:
            raise AppError("WORKSPACE_NOT_FOUND")
        db.execute(
            delete(TelegramPendingMedia).where(
                TelegramPendingMedia.workspace_id == ws_id,
                TelegramPendingMedia.user_id == user_id,
            )
        )
        db.add(
            TelegramPendingMedia(
                id=uuid.uuid4(),
                workspace_id=ws_id,
                user_id=user_id,
                media_asset_id=asset_id,
                expires_at=now + PENDING_MEDIA_TTL,
                created_at=now,
            )
        )
        db.flush()

    if session is not None:
        _write(session)
        return

    with get_session_factory()() as own_session:
        _write(own_session)
        own_session.commit()


def get_pending_media(
    user_id: uuid.UUID,
    now: datetime,
    *,
    session: Session | None = None,
    workspace_id: uuid.UUID | None = None,
) -> uuid.UUID | None:
    """Retrieve and clear pending media intake reference if not expired."""

    def _pop(db: Session) -> uuid.UUID | None:
        stmt = select(TelegramPendingMedia).where(TelegramPendingMedia.user_id == user_id)
        if workspace_id is not None:
            stmt = stmt.where(TelegramPendingMedia.workspace_id == workspace_id)
        entry = db.scalar(stmt.order_by(TelegramPendingMedia.created_at.desc()).limit(1))
        if entry is None:
            return None
        asset_id = entry.media_asset_id
        expired = entry.expires_at <= now
        db.delete(entry)
        db.flush()
        return None if expired else asset_id

    if session is not None:
        return _pop(session)

    with get_session_factory()() as own_session:
        res = _pop(own_session)
        own_session.commit()
        return res


def _is_explicit_owner_command(text: str) -> bool:
    """Return True if message clearly looks like a command rather than a question reply."""
    stripped = text.strip()
    if not stripped or stripped.startswith("/"):
        return True
    lower = stripped.lower()
    return any(term in lower for term in _EXPLICIT_COMMAND_TERMS)


def _find_question_by_ref(
    session: Session,
    workspace_id: uuid.UUID,
    ref_prefix: str,
) -> OwnerQuestion | None:
    """Find workspace OwnerQuestion whose UUID starts with ``ref_prefix`` (8 hex chars)."""
    prefix = ref_prefix.lower()
    questions = session.scalars(
        select(OwnerQuestion)
        .where(OwnerQuestion.workspace_id == workspace_id)
        .order_by((OwnerQuestion.state == "pending").desc(), OwnerQuestion.created_at.desc())
    ).all()
    for q in questions:
        if str(q.id).lower().startswith(prefix):
            return q
    return None


def _resolve_replied_owner_question(
    session: Session,
    workspace_id: uuid.UUID,
    reply_msg: Any,
) -> tuple[OwnerQuestion | None, bool]:
    """Resolve the specific OwnerQuestion referenced by a Telegram ``reply_to_message``."""
    reply_text = (
        reply_msg.get("text") or reply_msg.get("caption")
        if isinstance(reply_msg, dict)
        else getattr(reply_msg, "text", None) or getattr(reply_msg, "caption", None)
    ) or ""
    if not reply_text:
        return None, False

    ref_match = _QUESTION_REF_RE.search(reply_text)
    if ref_match is not None:
        return _find_question_by_ref(session, workspace_id, ref_match.group(1)), True

    if not any(heading in reply_text for heading in _QUESTION_HEADINGS):
        return None, False

    questions = session.scalars(
        select(OwnerQuestion)
        .where(OwnerQuestion.workspace_id == workspace_id)
        .order_by((OwnerQuestion.state == "pending").desc(), OwnerQuestion.created_at.desc())
    ).all()
    plain_reply = html.unescape(reply_text)
    for q in questions:
        body = (q.body or "").strip()
        if body and (body in reply_text or body in plain_reply):
            return q, True
    return None, True


def _send_ambiguous_questions_prompt(
    tg_client: TelegramClient,
    chat_id: str,
    is_tr: bool,
    pending_questions: list[OwnerQuestion],
) -> str:
    """Ask the owner to reply to the specific question instead of guessing."""
    items = "\n".join(
        f"• <code>Q-{str(q.id)[:8]}</code> — {html.escape((q.body or '')[:80])}"
        for q in pending_questions[:5]
    )
    if is_tr:
        msg = (
            f"⚠️ <b>Birden fazla bekleyen müşteri sorusu var ({len(pending_questions)}).</b>\n\n"
            f"{items}\n\n"
            "Lütfen yanıtlamak istediğiniz soruya Telegram'da <b>Yanıtla (Reply)</b> yapın "
            "veya mesajınıza <code>Q-xxxxxxxx</code> referans kodunu ekleyin."
        )
    else:
        msg = (
            f"⚠️ <b>Multiple pending customer questions ({len(pending_questions)}).</b>\n\n"
            f"{items}\n\n"
            "Please use Telegram <b>Reply</b> on the specific question you want to answer "
            "or include its <code>Q-xxxxxxxx</code> ref code."
        )
    tg_client.send_message(chat_id=chat_id, text=msg, parse_mode="HTML")
    return "owner_question_ambiguous"


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
    chat_id = str(message.chat.id)
    locale = (getattr(user, "ui_locale", None) or workspace.default_locale or "tr").lower()
    is_tr = locale.startswith("tr")

    member = session.scalar(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == workspace.id,
            WorkspaceMember.user_id == user.id,
        )
    )
    if member is None:
        msg = (
            "Bu çalışma alanına erişim yetkiniz kaldırıldı."
            if is_tr
            else "Your access to this workspace has been revoked."
        )
        tg_client.send_message(chat_id=chat_id, text=msg)
        return "forbidden"
    role = member.role
    actor = ActorRef(type="user", id=str(user.id))
    ctx = workspace_context(workspace, actor, role)
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
    pending_asset_id = get_pending_media(
        user.id,
        now,
        session=session,
        workspace_id=ctx.workspace_id,
    )

    # -------------------------------------------------------------------------
    # 2. Reporting Queries (AC-2)
    # -------------------------------------------------------------------------
    if is_reporting_query(raw_text):
        # Queries specifying other periods like 'dün' or 'son 7 gün' go through CommandService
        cleaned = raw_text.lower()
        if any(
            term in cleaned for term in ("dün", "yesterday", "son 7", "last 7", "hafta", "week")
        ):
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
    if message.reply_to_message:
        matched_question, is_question_reply = _resolve_replied_owner_question(
            session, ctx.workspace_id, message.reply_to_message
        )
        if is_question_reply and matched_question is None:
            not_found_msg = (
                "⚠️ <b>Yanıtladığınız soru bulunamadı.</b>\n\n"
                "Lütfen güncel bir soru bildirimine yanıt verin."
                if is_tr
                else "⚠️ <b>The question you replied to could not be found.</b>\n\n"
                "Please reply to an active question notification."
            )
            tg_client.send_message(chat_id=chat_id, text=not_found_msg, parse_mode="HTML")
            return "owner_question_not_found"

    prefix_match = re.match(
        r"^(?:cevap|yanıt|answer|bilgi)(?:\s+(Q-[0-9a-f]{8}))?:\s*(.*)$",
        raw_text,
        re.IGNORECASE | re.DOTALL,
    )
    if prefix_match:
        ref_code = prefix_match.group(1)
        body_text = (prefix_match.group(2) or "").strip()
        if ref_code:
            matched_question = _find_question_by_ref(session, ctx.workspace_id, ref_code[2:])
            if matched_question is None:
                not_found_msg = (
                    f"⚠️ <code>{html.escape(ref_code)}</code> kodlu soru bulunamadı."
                    if is_tr
                    else f"⚠️ Question <code>{html.escape(ref_code)}</code> was not found."
                )
                tg_client.send_message(chat_id=chat_id, text=not_found_msg, parse_mode="HTML")
                return "owner_question_not_found"
        if matched_question is None:
            pending_questions = list(
                session.scalars(
                    select(OwnerQuestion)
                    .where(
                        OwnerQuestion.workspace_id == ctx.workspace_id,
                        OwnerQuestion.state == "pending",
                        OwnerQuestion.expires_at > now,
                    )
                    .order_by(OwnerQuestion.created_at.desc())
                ).all()
            )
            if len(pending_questions) == 1:
                matched_question = pending_questions[0]
            elif len(pending_questions) > 1:
                return _send_ambiguous_questions_prompt(
                    tg_client, chat_id, is_tr, pending_questions
                )
            else:
                matched_question = session.scalar(
                    select(OwnerQuestion)
                    .where(OwnerQuestion.workspace_id == ctx.workspace_id)
                    .order_by(OwnerQuestion.created_at.desc())
                )
        if matched_question is not None:
            answer_text = body_text or raw_text
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

    # Auto-route un-prefixed text ONLY when not a photo follow-up, command, task, or query,
    # and ONLY when there is a single unambiguous pending OwnerQuestion.
    if (
        pending_asset_id is None
        and not _is_explicit_owner_command(raw_text)
        and not is_agent_task(raw_text)
        and not raw_text.rstrip().endswith("?")
    ):
        pending_questions = list(
            session.scalars(
                select(OwnerQuestion)
                .where(
                    OwnerQuestion.workspace_id == ctx.workspace_id,
                    OwnerQuestion.state == "pending",
                    OwnerQuestion.expires_at > now,
                )
                .order_by(OwnerQuestion.created_at.desc())
            ).all()
        )
        if len(pending_questions) == 1:
            return _handle_owner_question_answer(
                session=session,
                clock=clock,
                ctx=ctx,
                user=user,
                raw_text=raw_text,
                tg_client=tg_client,
                chat_id=chat_id,
                is_tr=is_tr,
                question=pending_questions[0],
            )
        if len(pending_questions) > 1:
            return _send_ambiguous_questions_prompt(tg_client, chat_id, is_tr, pending_questions)

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

    # Release DB transaction before external Telegram file download calls (INV-TX)
    session.commit()

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
    set_pending_media(
        user.id,
        media_asset.id,
        clock.now(),
        session=session,
        workspace_id=ctx.workspace_id,
    )
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


def _guarantee_lines(summary: dict[str, Any], is_tr: bool) -> str:
    """ "Replies sent" and "Unverified values sent" (D-01), from the daily report's metrics. Both
    are shown even when they are zero; nothing is shown if the report has no such number."""
    unverified = summary.get("unverified_values_sent")
    if unverified is None:
        return ""
    sent = int(summary.get("replies_sent") or 0)
    if is_tr:
        lines = [
            f"• <b>Gönderilen yanıtlar:</b> {sent}",
            f"• <b>Doğrulanmamış değer gönderilen yanıt:</b> {unverified}",
        ]
    else:
        lines = [
            f"• <b>Replies sent:</b> {sent}",
            f"• <b>Replies with unverified values sent:</b> {unverified}",
        ]
    return "\n".join(lines)


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

    from app.core.narrator import narrate_fallback

    natural_sentence = narrate_fallback(
        message_key="command.activity_summary",
        params={
            "period": "today",
            "inbound_messages": inbound,
            "conversations": conversations,
            "replies_sent": summary.get("replies_sent", 0),
            "replies_auto": summary.get("replies_auto", 0),
            "replies_approved": summary.get("replies_approved", 0),
            "replies_by_owner": summary.get("replies_by_owner", 0),
            "escalations": summary.get("escalations", 0),
            "attention_now": summary.get("attention_now", 0),
        },
        user_locale="tr" if is_tr else "en",
        user_query=raw_text,
    )

    guarantee = _guarantee_lines(summary, is_tr)

    if is_tr:
        if is_dm_count_question:
            text = (
                "📬 <b>Gelen Mesajlar</b>\n\n"
                f"{html.escape(natural_sentence)}\n\n"
                f"• <b>Toplam Gelen:</b> {inbound}\n"
                f"• <b>Yeni Konuşma:</b> {new_convs}\n"
                f"• <b>Aktif Konuşmalar:</b> {conversations}\n"
                f"• <b>Bekleyen Onaylar:</b> {approvals}"
            )
        else:
            text = (
                "📊 <b>Bugünkü Özet</b>\n\n"
                f"{html.escape(natural_sentence)}\n\n"
                f"• <b>Gelen DM / Mesaj:</b> {inbound}\n"
                f"• <b>Yeni Konuşma:</b> {new_convs}\n"
                f"• <b>Aktif Konuşmalar:</b> {conversations}\n"
                f"• <b>Bekleyen Onaylar:</b> {approvals}"
            )
    else:
        if is_dm_count_question:
            text = (
                "📬 <b>Inbound Messages</b>\n\n"
                f"{html.escape(natural_sentence)}\n\n"
                f"• <b>Total Inbound:</b> {inbound}\n"
                f"• <b>New Conversations:</b> {new_convs}\n"
                f"• <b>Active Conversations:</b> {conversations}\n"
                f"• <b>Pending Approvals:</b> {approvals}"
            )
        else:
            text = (
                "📊 <b>Today's Summary</b>\n\n"
                f"{html.escape(natural_sentence)}\n\n"
                f"• <b>Inbound DMs / Messages:</b> {inbound}\n"
                f"• <b>New Conversations:</b> {new_convs}\n"
                f"• <b>Active Conversations:</b> {conversations}\n"
                f"• <b>Pending Approvals:</b> {approvals}"
            )

    if guarantee and not is_dm_count_question:
        text += "\n\n" + guarantee
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
            "Durumu Pivoris üzerinden takip edebilirsiniz."
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

    from app.integrations.channels.base import ChannelRecipient
    from app.integrations.channels.formatting import format_command_for_telegram

    recipient = ChannelRecipient(
        user_id=uuid.UUID(str(ctx.actor.id)),
        workspace_id=ctx.workspace_id,
        channel="telegram",
        channel_chat_id=chat_id,
        ui_locale="tr" if is_tr else "en",
        timezone=ctx.timezone,
    )
    msg, reply_markup = format_command_for_telegram(cmd, recipient)
    tg_client.send_message(chat_id=chat_id, text=msg, parse_mode="HTML", reply_markup=reply_markup)
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
        answer = owner_requests_service.decide(
            db=session,
            clock=clock,
            ctx=ctx,
            account=question.social_account_id,
            question=question.id,
            request=request,
        )
        offer = _fact_save_offer(session, clock, ctx, answer, is_tr)
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
        if offer is None:
            tg_client.send_message(chat_id=chat_id, text=msg, parse_mode="HTML")
        elif offer[1] is None:
            tg_client.send_message(chat_id=chat_id, text=f"{msg}\n\n{offer[0]}", parse_mode="HTML")
        else:
            tg_client.send_message(
                chat_id=chat_id,
                text=f"{msg}\n\n{offer[0]}",
                parse_mode="HTML",
                reply_markup=offer[1],
            )
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


def _fact_save_offer(
    session: Session,
    clock: Clock,
    ctx: WorkspaceContext,
    answer: Any,
    is_tr: bool,
) -> tuple[str, dict[str, Any] | None] | None:
    """The "save as verified fact" offer shown under the confirmation (D-05).

    A one-tap button (single-use token) when the answer is plain text. An answer that carries a
    price, hours or a contact gets a note instead: those go through the typed editor in the app.
    """
    from app.identity.permissions import has_permission
    from app.knowledge.learning import editor_type
    from app.knowledge.models import FactCandidate
    from app.owner_requests import save_tokens

    if answer.candidate_id is None or ctx.actor.id is None:
        return None
    candidate = session.get(FactCandidate, answer.candidate_id)
    if (
        candidate is None
        or candidate.status != "pending"
        or not has_permission(ctx.role, "knowledge.verify")
    ):
        return None
    if editor_type(candidate) is not None:
        note = (
            "ℹ️ Bu yanıt fiyat, saat veya iletişim bilgisi içeriyor. Doğrulanmış bilgi "
            "olarak kaydetmek için uygulamada İşletme bilgisi bölümünden onaylayın."
            if is_tr
            else (
                "ℹ️ This answer contains a price, hours or contact details. To save it "
                "as a verified fact, confirm it in Business knowledge in the app."
            )
        )
        return note, None
    token = save_tokens.create(session, clock, ctx, candidate.id, uuid.UUID(ctx.actor.id))
    label = "💾 Doğrulanmış bilgi olarak kaydet" if is_tr else "💾 Save as verified fact"
    prompt = (
        "Bu yanıtı doğrulanmış bilgi olarak kaydedelim mi? Asistan sonraki yanıtlarda kullanır."
        if is_tr
        else "Save this as a verified fact? The assistant will use it in future replies."
    )
    keyboard = {
        "inline_keyboard": [[{"text": label, "callback_data": save_tokens.CALLBACK_PREFIX + token}]]
    }
    return prompt, keyboard


def handle_fact_save_callback(
    session: Session,
    clock: Clock,
    callback_query: Any,
    token_str: str,
    tg_client: TelegramClient,
) -> str:
    """Consume a single-use "save as verified fact" token and accept its candidate (D-05).

    The accept is the ordinary ``knowledge.accept_candidate`` as the linked user: the token only
    proves which candidate and which person the button was meant for.
    """
    from app.knowledge import service as knowledge_service
    from app.owner_requests import save_tokens

    channel_user_id = str(callback_query.from_.id) if callback_query.from_ else ""
    chat_id = str(callback_query.message.chat.id) if callback_query.message else None
    message_id = callback_query.message.message_id if callback_query.message else None

    def finish(text: str, action: str) -> str:
        tg_client.answer_callback_query(callback_query.id, text=text, show_alert=True)
        if chat_id and message_id:
            with contextlib.suppress(Exception):
                tg_client.edit_message_reply_markup(
                    chat_id=chat_id, message_id=message_id, reply_markup={"inline_keyboard": []}
                )
        return action

    try:
        token = save_tokens.consume(session, clock, token_str, channel_user_id)
    except AppError as exc:
        if exc.code == "APPROVAL_ALREADY_DECIDED":
            return finish("Bu bilgi zaten kaydedildi / Already saved", "fact_save_already_used")
        if exc.code == "APPROVAL_EXPIRED":
            return finish("Düğmenin süresi doldu / Button expired", "fact_save_expired")
        if exc.code == "FORBIDDEN":
            return finish("Bu işlem için yetkiniz yok / Unauthorized", "fact_save_unauthorized")
        return finish("Bu düğme geçerli değil / Invalid button", "fact_save_failed")

    user = session.get(User, token.user_id)
    workspace = session.get(Workspace, token.workspace_id)
    member = (
        session.scalar(
            select(WorkspaceMember).where(
                WorkspaceMember.workspace_id == token.workspace_id,
                WorkspaceMember.user_id == token.user_id,
            )
        )
        if user is not None and workspace is not None
        else None
    )
    if user is None or workspace is None or member is None:
        return finish("Çalışma alanı erişimi yok / Workspace access revoked", "fact_save_failed")
    ctx = workspace_context(workspace, ActorRef.user(user.id), member.role)
    try:
        knowledge_service.accept_candidate(session, clock, ctx, token.candidate_id)
    except AppError as exc:
        # The token stays spent: a failed accept changed nothing else.
        session.commit()
        if exc.code == "CONFLICT_STATE":
            return finish("Bu öneri zaten karara bağlandı / Already handled", "fact_save_conflict")
        if exc.code == "FORBIDDEN":
            return finish("Bu işlem için yetkiniz yok / Unauthorized", "fact_save_unauthorized")
        if exc.code == "VALIDATION_FAILED":
            return finish(
                "Bu yanıt uygulamada onaylanmalı / Confirm it in the app", "fact_save_needs_editor"
            )
        return finish("Kaydedilemedi / Could not save", "fact_save_failed")

    tg_client.answer_callback_query(
        callback_query.id, text="✅ Kaydedildi / Saved", show_alert=False
    )
    if chat_id and message_id and callback_query.message:
        orig = callback_query.message.text or ""
        name = user.display_name or user.email or "Owner"
        try:
            tg_client.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=f"{orig}\n\n✅ Doğrulanmış bilgi olarak kaydedildi / Saved as a fact — {name}",
                reply_markup={"inline_keyboard": []},
            )
        except Exception:
            with contextlib.suppress(Exception):
                tg_client.edit_message_reply_markup(
                    chat_id=chat_id, message_id=message_id, reply_markup={"inline_keyboard": []}
                )
    return "fact_saved"


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
    if member is None:
        tg_client.answer_callback_query(
            callback_query.id,
            text="Çalışma alanı erişiminiz kaldırıldı / Workspace access revoked",
            show_alert=True,
        )
        return "approval_failed"
    role = member.role
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
