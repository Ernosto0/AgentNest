"""WhatsApp message templates: the one registry of every owner-notification text (ADR-027).

Outside the 24-hour customer-service window only an approved **template** may be sent, so every
notification type the channel carries has one template here, in Turkish and English. Inside the
window the same rendered text is sent as a plain session message, so an owner reads the same words
either way.

Rules the registry enforces (``tests/unit/integrations/channels/test_whatsapp_templates.py``):

- Meta category is always ``utility`` (a notification about the owner's own account activity; no
  promotion). Marketing and authentication are never used.
- Template ``name`` is lowercase letters, digits and underscores (Meta rule) and carries a version
  suffix, because an approved template cannot be edited in place.
- Variables are positional ``{{1}}``, ``{{2}}``... and are **numbers or a date only**. Customer
  text, names, handles and message content never become a variable (same rule as Web Push).
- A variable is never the first or last thing in a body (Meta rejects such templates), and a body
  is far shorter than the 1024-character limit.

``docs/research/platform-capabilities.md`` section 2.2 lists the same templates for submission in
Meta's WhatsApp Manager; keep the two in step (a test compares the names).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from typing import Any

CATEGORY_UTILITY = "utility"
LOCALES = ("tr", "en")
_PLACEHOLDER = re.compile(r"\{\{(\d+)\}\}")


@dataclass(frozen=True)
class WhatsAppTemplate:
    name: str
    notification_type: str
    bodies: dict[str, str]  # locale -> body text with {{n}} placeholders
    variables: tuple[str, ...] = ()  # one documented meaning per positional variable
    category: str = CATEGORY_UTILITY

    def render(self, locale: str, values: list[str]) -> str:
        if len(values) != len(self.variables):
            raise ValueError("template variable count mismatch")
        body = self.bodies[normalize_locale(locale)]
        return _PLACEHOLDER.sub(lambda m: values[int(m.group(1)) - 1], body)


def normalize_locale(locale: str | None) -> str:
    return "tr" if (locale or "tr").lower().startswith("tr") else "en"


def _t(
    name: str,
    notification_type: str,
    tr: str,
    en: str,
    variables: tuple[str, ...] = (),
) -> WhatsAppTemplate:
    return WhatsAppTemplate(name, notification_type, {"tr": tr, "en": en}, variables)


_TEMPLATES = (
    _t(
        "pivoris_approval_requested_v1",
        "approval.requested",
        "Pivoris: Kararınızı bekleyen bir onay var. Ayrıntılar için uygulamayı açın.",
        "Pivoris: An approval is waiting for your decision. Open the app for details.",
    ),
    _t(
        "pivoris_owner_question_v1",
        "owner_question.requested",
        "Pivoris: Asistanınızın size bir sorusu var. Yanıtlamak için uygulamayı açın.",
        "Pivoris: Your assistant has a question for you. Open the app to answer it.",
    ),
    _t(
        "pivoris_question_unanswered_v1",
        "owner_question.window_closed",
        "Pivoris: Bir soru yanıtsız kaldı. Ne olduğunu görmek için uygulamayı açın.",
        "Pivoris: A question went unanswered. Open the app to see what happened.",
    ),
    _t(
        "pivoris_content_failed_v1",
        "content.failed",
        "Pivoris: Bir paylaşım yayınlanamadı. Ne olduğunu görmek için uygulamayı açın.",
        "Pivoris: A post could not be published. Open the app to see what happened.",
    ),
    _t(
        "pivoris_reply_failed_v1",
        "reply.failed",
        "Pivoris: Bir yanıt gönderilemedi. Ne olduğunu görmek için uygulamayı açın.",
        "Pivoris: A reply was not sent. Open the app to see what happened.",
    ),
    _t(
        "pivoris_account_reauth_v1",
        "account.needs_reauth",
        "Pivoris: Instagram bağlantısının yenilenmesi gerekiyor. "
        "Hesabı yeniden bağlamak için uygulamayı açın.",
        "Pivoris: Your Instagram connection needs to be renewed. "
        "Open the app to reconnect your account.",
    ),
    _t(
        "pivoris_quota_warning_v1",
        "quota.warning",
        "Pivoris: Yapay zeka yanıt hakkınızın %80'i kullanıldı. "
        "Planınızı ve kullanımı Ayarlar'dan görün.",
        "Pivoris: 80% of your AI reply allowance is used. See your plan and usage in Settings.",
    ),
    _t(
        "pivoris_quota_grace_v1",
        "quota.grace",
        "Pivoris: Yapay zeka yanıt hakkınıza ulaşıldı. "
        "Taslaklar %10 ek hakla devam eder, sonra duraklar.",
        "Pivoris: AI reply allowance reached. Drafting continues within an extra 10%, "
        "then pauses.",
    ),
    _t(
        "pivoris_quota_paused_v1",
        "quota.paused",
        "Pivoris: Yapay zeka yanıtları duraklatıldı. Mesajlar gelen kutusuna düşmeye devam "
        "eder; yeni döneme kadar kendiniz yanıtlayın.",
        "Pivoris: AI replies are paused. Messages still arrive in the inbox; reply yourself "
        "until the next period.",
    ),
    _t(
        "pivoris_daily_summary_v1",
        "report.daily_ready",
        "Pivoris günlük özet, {{1}} tarihi için: {{2}} yeni mesaj, {{3}} gönderilen yanıt, "
        "{{4}} bekleyen onay. Ayrıntılar uygulamada.",
        "Pivoris daily summary for {{1}}: {{2}} new messages, {{3}} replies sent, "
        "{{4}} approvals waiting. Details are in the app.",
        ("local_date", "inbound_messages", "replies_sent", "pending_approvals"),
    ),
)

ALL_TEMPLATES: tuple[WhatsAppTemplate, ...] = _TEMPLATES
BY_TYPE: dict[str, WhatsAppTemplate] = {t.notification_type: t for t in _TEMPLATES}
BY_NAME: dict[str, WhatsAppTemplate] = {t.name: t for t in _TEMPLATES}


def _count(value: Any) -> str | None:
    """A non-negative integer as text; anything else (free text included) is refused."""
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return str(value)


def variable_values(
    template: WhatsAppTemplate, params: dict[str, Any], locale: str
) -> list[str] | None:
    """The send-time values of ``template`` from a notification's params, or ``None`` when one is
    missing or is not a number or date. Nothing else of ``params`` is ever read."""
    values: list[str] = []
    for key in template.variables:
        raw = params.get(key)
        if key == "local_date":
            try:
                day = date.fromisoformat(raw) if isinstance(raw, str) else None
            except ValueError:
                day = None
            if day is None:
                return None
            tr = normalize_locale(locale) == "tr"
            values.append(day.strftime("%d.%m.%Y") if tr else day.isoformat())
        else:
            count = _count(raw)
            if count is None:
                return None
            values.append(count)
    return values
