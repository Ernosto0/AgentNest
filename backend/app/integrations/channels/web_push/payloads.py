"""The Web Push payload: fixed text per notification type, a same-origin deep link and a tag.

**Customer text never reaches a push service.** A push payload crosses third parties (the browser
vendor's push service) and is shown on a lock screen, so it carries only:

- ``title`` and ``body``: constant text chosen by *notification type* and the recipient's language
  (plus a "simulation" marker when the notification is simulated, INV-09);
- ``url``: a same-origin path (``/w/<workspace id>/...``) whose only variable parts are UUIDs
  parsed out of the notification, never free text;
- ``tag``: the notification type and id, so a re-send replaces rather than stacks.

This module deliberately reads nothing else from the notification: ``params`` is consulted for
UUID values by key and for nothing more, and no message, draft, question, customer name or handle,
caption or title is ever read. It imports no inbox, AI, knowledge, approval or content module
(import-linter), so there is no path to that text. ``tests/integration/notifications/
test_web_push_channel.py`` seeds distinctive customer text in every place it could come from and
asserts it never appears in any payload.
"""

import json
import uuid
from dataclasses import dataclass
from typing import Any

from app.notifications.catalog import PUSH_TYPES
from app.notifications.models import Notification
from app.notifications.quota_text import TEXT as QUOTA_TEXT

MAX_PAYLOAD_BYTES = 1024  # far under the ~4 KB a push service accepts

# type -> locale -> (title, body)
_TEXT: dict[str, dict[str, tuple[str, str]]] = {
    "approval.requested": {
        "en": ("Approval needed", "Something is waiting for your decision."),
        "tr": ("Onayınız bekleniyor", "Kararınızı bekleyen bir işlem var."),
    },
    "owner_question.requested": {
        "en": ("Your assistant has a question", "Open the app to answer it."),
        "tr": ("Asistanınızın bir sorusu var", "Yanıtlamak için uygulamayı açın."),
    },
    "owner_question.window_closed": {
        "en": ("A question went unanswered", "Open the app to see what happened."),
        "tr": ("Bir soru yanıtsız kaldı", "Ne olduğunu görmek için uygulamayı açın."),
    },
    "content.failed": {
        "en": ("A post could not be published", "Open the app to see what happened."),
        "tr": ("Bir paylaşım yayınlanamadı", "Ne olduğunu görmek için uygulamayı açın."),
    },
    "reply.failed": {
        "en": ("A reply was not sent", "Open the app to see what happened."),
        "tr": ("Bir yanıt gönderilemedi", "Ne olduğunu görmek için uygulamayı açın."),
    },
    "account.needs_reauth": {
        "en": ("Instagram needs to be reconnected", "Open the app to reconnect your account."),
        "tr": ("Instagram bağlantısı yenilenmeli", "Hesabı yeniden bağlamak için uygulamayı açın."),
    },
}
_TEXT.update(QUOTA_TEXT)
_SIMULATION_PREFIX = {"en": "[Simulation] ", "tr": "[Simülasyon] "}


@dataclass(frozen=True)
class PushPayload:
    title: str
    body: str
    url: str
    tag: str

    def to_json(self) -> str:
        text = json.dumps(
            {"title": self.title, "body": self.body, "url": self.url, "tag": self.tag},
            ensure_ascii=False,
            separators=(",", ":"),
        )
        if len(text.encode()) > MAX_PAYLOAD_BYTES:
            raise ValueError("push payload too large")
        return text


def _uuid(value: Any) -> str | None:
    """A canonical UUID string, or ``None`` for anything else (so free text can never pass)."""
    try:
        return str(uuid.UUID(str(value))) if value is not None else None
    except ValueError:
        return None


def deep_link(notification: Notification) -> str:
    """The in-app page for the notification, as a same-origin path (never an absolute URL)."""
    base = f"/w/{notification.workspace_id}"
    params = notification.params if isinstance(notification.params, dict) else {}
    kind = notification.type
    if kind.startswith("quota."):
        return f"{base}/more/settings#usage"
    if kind.startswith("owner_question."):
        question = _uuid(params.get("question_id")) or _uuid(notification.subject_id)
        account = _uuid(params.get("account_id"))
        if question and account:
            return f"{base}/more/agent/questions/{question}?account={account}"
        return f"{base}/more/agent/questions"
    if kind == "approval.requested":
        return f"{base}/approvals"
    if kind == "content.failed":
        content = _uuid(params.get("content_id"))
        return f"{base}/content/{content}" if content else f"{base}/content"
    if kind == "reply.failed":
        conversation = _uuid(params.get("conversation_id"))
        return f"{base}/inbox/{conversation}" if conversation else f"{base}/inbox"
    if kind == "account.needs_reauth":
        return f"{base}/more/settings/connections"
    return base


def build_payload(notification: Notification, locale: str | None) -> PushPayload:
    """The payload for ``notification``. An unsupported type is an error, never a fallback."""
    if notification.type not in PUSH_TYPES or notification.type not in _TEXT:
        raise ValueError(f"no push payload for notification type: {notification.type}")
    lang = "tr" if (locale or "tr").lower().startswith("tr") else "en"
    title, body = _TEXT[notification.type][lang]
    if notification.is_simulated:
        title = _SIMULATION_PREFIX[lang] + title
    return PushPayload(
        title=title,
        body=body,
        url=deep_link(notification),
        tag=f"{notification.type}:{notification.id}",
    )
