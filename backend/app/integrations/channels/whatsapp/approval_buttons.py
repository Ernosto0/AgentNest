"""Approve and reject buttons on WhatsApp (ADR-027, Feature Phase 5 Session 03).

Two halves, both reusing the Phase 9 action-token machinery (``approvals.action_tokens``: random,
SHA-256 hashed at rest, single-use, bound to approval, member, decision and payload hash, expiring
with the approval). No new token scheme exists here.

**Out.** ``prepare_buttons`` mints one approve token and one reject token for the recipient and
returns the fixed message body and two reply buttons. The button id is ``act:<token>``; the token
is opaque (the id carries no approval id, decision or workspace). The body says **what is being
approved** (an approval must be informed): the proposed outgoing reply, the post's title, caption
and schedule, or the price / time change, the same fields the Telegram message shows, clipped to
the interactive body limit with an ellipsis and "full text in the app" when cut (the approval
still binds to the full payload hash). It never contains the *customer's* inbound message
(ADR-027). Interactive buttons are *session* messages; the adapter calls this only inside the
24-hour window.

**In.** ``handle_button_reply`` is called by the webhook dispatcher for a button tap from a sender
whose number is linked to an active member. It consumes the token, which checks, in one locked
transaction: the token exists, is unused and unexpired, the tapping number resolves to the token's
member in the token's workspace, and the approval is still pending. Then it decides through the
same ``approvals.service.decide`` as the web and Telegram, with ``channel="whatsapp"`` and the
payload hash stored in the token (so an edited subject is stale, never approved). The answer to the
owner is a fixed, localised session message sent after the commit; a replayed, expired, stale or
withdrawn button gets the *current* state in words, and only if the tapper is the token's member
(a forwarded button tapped by someone else learns nothing). A sender whose number is not linked
gets no reply at all. Free text never reaches this module (it is only called for button replies).
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.approvals.action_tokens import ActionTokenService
from app.approvals.models import Approval
from app.approvals.service import decide as decide_approval
from app.core.clock import Clock
from app.core.context import ActorRef
from app.core.errors import AppError
from app.identity.models import ChannelLink, User, Workspace, WorkspaceMember
from app.identity.service import workspace_context
from app.integrations.channels.whatsapp.templates import normalize_locale
from app.integrations.channels.whatsapp.webhook_format import InboundButtonReply

_log = logging.getLogger(__name__)

BUTTON_PREFIX = "act:"
MAX_TOKEN_CHARS = 64  # a token is ~22 characters; anything longer is not ours

# One fixed label per approval action: never a value taken from the approval's summary.
_KIND_LABELS: dict[str, tuple[str, str]] = {
    "reply.send": ("müşteri yanıtı", "customer reply"),
    "comments.approve": ("yorum yanıtı", "comment reply"),
    "content.publish": ("paylaşım", "post"),
    "content.prepare": ("paylaşım", "post"),
    "content.schedule": ("paylaşım planı", "post schedule"),
    "content.cancel": ("paylaşım iptali", "post cancellation"),
    "calendar.book": ("randevu", "appointment"),
    "calendar.reschedule": ("randevu değişikliği", "appointment change"),
    "calendar.cancel": ("randevu iptali", "appointment cancellation"),
}
_DEFAULT_LABEL = ("işlem", "action")

BUTTON_TITLES = {"tr": ("Onayla", "Reddet"), "en": ("Approve", "Reject")}

BODY_LIMIT = 1000  # Meta allows 1024 characters in an interactive body; keep a safety margin
FIELD_LIMIT = 80  # secondary fields (title, label, time) are short by nature
ELLIPSIS = "\u2026"

_TEXT = {
    "tr": {
        "head": "AgentNest: Kararınızı bekleyen bir onay var ({label}).",
        "expires": "Son karar zamanı: {expires}. Aşağıdaki düğmelerle karar verebilirsiniz.",
        "cut": "(tam metin uygulamada)",
        "reply": "Önerilen yanıt",
        "title": "Başlık",
        "caption": "Açıklama",
        "type": "Tür",
        "scheduled": "Planlanan zaman",
        "label": "Konu",
        "price": "Fiyat",
        "change": "Değişiklik",
        "resume": "Devam zamanı",
        "creates_draft": "Yalnızca taslak oluşturulur.",
    },
    "en": {
        "head": "AgentNest: An approval is waiting for your decision ({label}).",
        "expires": "Decide by: {expires}. You can decide with the buttons below.",
        "cut": "(full text in the app)",
        "reply": "Proposed reply",
        "title": "Title",
        "caption": "Caption",
        "type": "Type",
        "scheduled": "Scheduled",
        "label": "About",
        "price": "Price",
        "change": "Change",
        "resume": "Resume at",
        "creates_draft": "Creates a draft only.",
    },
}

# Fixed answers to a tap. Nothing from the approval, the customer or the provider is ever echoed.
REPLIES: dict[str, dict[str, str]] = {
    "tr": {
        "approved": "Onaylandı. Ayrıntılar uygulamada.",
        "rejected": "Reddedildi. Ayrıntılar uygulamada.",
        "already_approved": "Bu onay zaten onaylanmış. Ayrıntılar uygulamada.",
        "already_rejected": "Bu onay zaten reddedilmiş. Ayrıntılar uygulamada.",
        "expired": "Bu onayın süresi doldu. Güncel durum için uygulamayı açın.",
        "stale": "Onay içeriği değişti ya da geri çekildi; bu düğme artık geçerli değil. "
        "Uygulamayı açın.",
        "forbidden": "Bu onay için yetkiniz yok. Uygulamayı açın.",
        "invalid": "Bu düğme geçerli değil. Uygulamayı açın.",
        "failed": "Karar kaydedilemedi. Uygulamayı açıp tekrar deneyin.",
    },
    "en": {
        "approved": "Approved. Details are in the app.",
        "rejected": "Rejected. Details are in the app.",
        "already_approved": "This approval was already approved. Details are in the app.",
        "already_rejected": "This approval was already rejected. Details are in the app.",
        "expired": "This approval has expired. Open the app for the current state.",
        "stale": "The approval changed or was withdrawn; this button no longer applies. "
        "Open the app.",
        "forbidden": "You are not allowed to decide this approval. Open the app.",
        "invalid": "This button is not valid. Open the app.",
        "failed": "The decision could not be saved. Open the app and try again.",
    },
}

SendText = Callable[[str, str], None]


@dataclass(frozen=True)
class PreparedButtons:
    body: str
    buttons: list[tuple[str, str]]  # (button id, title) as the client wants them


def _expiry_text(when: datetime, tz_name: str | None) -> str:
    try:
        from zoneinfo import ZoneInfo

        local = when.astimezone(ZoneInfo(tz_name)) if tz_name else when
    except Exception:
        local = when
    return local.strftime("%d.%m.%Y %H:%M")


def _clip(value: object, limit: int) -> str:
    text = " ".join(str(value).split())  # one line, no control characters
    return text if len(text) <= limit else text[: limit - 1].rstrip() + ELLIPSIS


def _details(
    session: Session, approval: Approval, loc: str, timezone: str | None
) -> tuple[list[str], str | None]:
    """What is being approved: ``(short fields, the one long text or None)``.

    The long text (a proposed reply or a caption) is the part clipped to the room left in the
    message. Only the server's own outgoing content and summary fields are read; the customer's
    inbound message is never touched here. Telegram shows the same fields."""
    t = _TEXT[loc]
    summary = approval.summary if isinstance(approval.summary, dict) else {}
    fields: list[str] = []
    long_text: str | None = None
    if approval.subject_type == "reply_draft":
        from app.inbox.models import ReplyDraft

        draft = session.get(ReplyDraft, approval.subject_id)
        if draft is not None and draft.workspace_id != approval.workspace_id:
            draft = None
        raw = draft.text if draft is not None and draft.text else summary.get("text")
        long_text = (str(raw).strip() or None) if raw else None
    elif approval.subject_type == "content_item":
        from app.content.models import ContentItem

        item = session.get(ContentItem, approval.subject_id)
        if item is not None and item.workspace_id == approval.workspace_id:
            kind = _clip(item.content_type.replace("_", " "), FIELD_LIMIT)
            fields.append(f"{t['type']}: {kind}")
            if item.title:
                fields.append(f"{t['title']}: {_clip(item.title, FIELD_LIMIT)}")
            if item.scheduled_at:
                fields.append(f"{t['scheduled']}: {_expiry_text(item.scheduled_at, timezone)}")
            if item.caption and item.caption.strip():
                long_text = item.caption.strip()
    elif approval.action == "command.make_price_card":
        fields.append(f"{t['label']}: {_clip(summary.get('label', ''), FIELD_LIMIT)}")
        fields.append(f"{t['price']}: {_clip(summary.get('price_formatted', ''), FIELD_LIMIT)}")
        fields.append(t["creates_draft"])
    elif approval.action == "command.pause_agent":
        fields.append(f"{t['resume']}: {_clip(summary.get('resume_at', ''), FIELD_LIMIT)}")
    elif approval.action == "command.reschedule_content":
        fields.append(f"{t['label']}: {_clip(summary.get('label', ''), FIELD_LIMIT)}")
        change = f"{summary.get('old_formatted', '')} -> {summary.get('new_formatted', '')}"
        fields.append(f"{t['change']}: {_clip(change, 2 * FIELD_LIMIT)}")
    else:
        # Other kinds: only a short, fixed allow-list of the summary's own display fields.
        for key in ("label", "title", "old_formatted", "new_formatted", "price_formatted"):
            value = summary.get(key)
            if isinstance(value, str | int | float) and str(value).strip():
                fields.append(f"{key.replace('_', ' ')}: {_clip(value, FIELD_LIMIT)}")
    return fields, long_text


def build_body(
    session: Session, approval: Approval, loc: str, timezone: str | None, label: str
) -> str:
    """The interactive body, at most ``BODY_LIMIT`` characters. The long text is cut with an
    ellipsis and a "full text in the app" note when it does not fit; nothing else is ever cut."""
    t = _TEXT[loc]
    fields, long_text = _details(session, approval, loc, timezone)
    head = "\n".join([t["head"].format(label=label), *fields])
    tail = t["expires"].format(expires=_expiry_text(approval.expires_at, timezone))
    if long_text is None:
        return f"{head}\n\n{tail}"[:BODY_LIMIT]
    prefix = t["reply"] if approval.subject_type == "reply_draft" else t["caption"]
    # Room for the text: the limit minus head, tail, prefix and its 6 separator characters.
    room = BODY_LIMIT - len(head) - len(tail) - len(prefix) - 6
    if len(long_text) <= room:
        shown = long_text
    else:
        note = " " + t["cut"]
        shown = long_text[: max(room - len(note) - 1, 0)].rstrip() + ELLIPSIS + note
    return f"{head}\n\n{prefix}:\n{shown}\n\n{tail}"[:BODY_LIMIT]


def prepare_buttons(
    session: Session,
    clock: Clock,
    approval: Approval,
    user_id: uuid.UUID,
    locale: str,
    timezone: str | None,
) -> PreparedButtons | None:
    """Mint the two single-use tokens in the caller's transaction and build the message, or
    ``None`` when the recipient is no longer a member of the approval's workspace."""
    workspace = session.get(Workspace, approval.workspace_id)
    user = session.get(User, user_id)
    member = session.scalar(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == approval.workspace_id,
            WorkspaceMember.user_id == user_id,
        )
    )
    if workspace is None or user is None or member is None:
        return None
    ctx = workspace_context(workspace, ActorRef.user(user_id), member.role)
    approve = ActionTokenService.create_action_token(
        session, clock, ctx, approval, decision="approved", user_id=user_id
    )
    reject = ActionTokenService.create_action_token(
        session, clock, ctx, approval, decision="rejected", user_id=user_id
    )
    loc = normalize_locale(locale)
    label = _KIND_LABELS.get(approval.action, _DEFAULT_LABEL)[0 if loc == "tr" else 1]
    body = build_body(session, approval, loc, timezone, label)
    approve_title, reject_title = BUTTON_TITLES[loc]
    return PreparedButtons(
        body=body,
        buttons=[(BUTTON_PREFIX + approve, approve_title), (BUTTON_PREFIX + reject, reject_title)],
    )


def _state_reply(status: str) -> str:
    if status == "approved":
        return "already_approved"
    if status == "rejected":
        return "already_rejected"
    if status == "expired":
        return "expired"
    return "stale"  # cancelled (edited, superseded, withdrawn) or anything unexpected


def _describe_current_state(
    session: Session, token_str: str, user: User, workspace: Workspace
) -> str:
    """The reply for a replayed or stale button, only for the token's own member."""
    record = ActionTokenService.lookup_action_token(session, token_str)
    if record is None or record.user_id != user.id or record.workspace_id != workspace.id:
        return "invalid"  # not this owner's button: reveal nothing about it
    approval = session.get(Approval, record.approval_id)
    if approval is None:
        return "invalid"
    if approval.status == "pending":
        return "expired"  # a pending approval with a dead token: the token's time ran out
    return _state_reply(approval.status)


def handle_button_reply(
    session: Session,
    clock: Clock,
    event: InboundButtonReply,
    resolved: tuple[User, Workspace, ChannelLink],
    send: SendText,
) -> bool:
    """Process one button tap from a *linked* sender; returns whether it was acted on.

    ``send`` queues a fixed reply to be sent after the commit. The caller commits (``decide``
    commits itself on a decision). Anything but an expected refusal propagates, so Meta's retry is
    processed again (the dedup row rolls back with the transaction).
    """
    user, workspace, _link = resolved
    locale = normalize_locale(user.ui_locale)
    replies = REPLIES[locale]
    raw = event.button_id or ""
    token_str = raw[len(BUTTON_PREFIX) :] if raw.startswith(BUTTON_PREFIX) else ""
    if not token_str or len(token_str) > MAX_TOKEN_CHARS:
        send(event.wa_id, replies["invalid"])
        return True

    try:
        approval, token = ActionTokenService.consume_action_token(
            session, clock, token_str, event.wa_id, channel="whatsapp"
        )
    except AppError as exc:
        key = (
            _describe_current_state(session, token_str, user, workspace)
            if exc.code in {"APPROVAL_ALREADY_DECIDED", "APPROVAL_EXPIRED", "CONFLICT_STATE"}
            else "invalid"
        )
        _log.info("whatsapp_button_refused code=%s", exc.code)
        send(event.wa_id, replies[key])
        return True

    member = session.scalar(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == workspace.id,
            WorkspaceMember.user_id == user.id,
        )
    )
    if member is None:  # resolve_channel_user already requires it; a race is refused, not decided
        send(event.wa_id, replies["forbidden"])
        return True
    ctx = workspace_context(workspace, ActorRef.user(user.id), member.role)
    decision = "approve" if token.decision == "approved" else "reject"
    approval_id = approval.id
    try:
        decide_approval(
            session=session,
            clock=clock,
            ctx=ctx,
            approval_id=approval_id,
            decision=decision,
            payload_hash=token.payload_hash,
            channel="whatsapp",
        )
    except AppError as exc:
        _log.info("whatsapp_button_decision_refused code=%s", exc.code)
        if exc.code == "APPROVAL_ALREADY_DECIDED":
            current = session.get(Approval, approval_id)
            key = _state_reply(current.status if current else "cancelled")
        else:
            key = {
                "APPROVAL_EXPIRED": "expired",
                "APPROVAL_STALE": "stale",
                "FORBIDDEN": "forbidden",
            }.get(exc.code, "failed")
        send(event.wa_id, replies[key])
        return True
    send(event.wa_id, replies["approved" if decision == "approve" else "rejected"])
    return True
