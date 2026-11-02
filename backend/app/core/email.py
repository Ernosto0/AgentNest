"""Transactional email delivery and local outbox capture (ADR-025 §2, OQ-16).

Supports standard SMTP (smtp:// and smtps://) when configured via ``SMTP_URL`` and
``MAIL_FROM``. When unconfigured or in tests, captured in an in-memory outbox for
credential-free operation, reproducible tests, and safe verification.
"""

import contextlib
import smtplib
import urllib.parse
from dataclasses import dataclass
from datetime import UTC, datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from threading import Lock

from app.core.config import Settings
from app.core.logging import get_logger

_log = get_logger("app.email")


@dataclass(frozen=True)
class CapturedEmail:
    to_email: str
    subject: str
    text_body: str
    html_body: str | None
    sent_at: datetime


class InMemoryEmailOutbox:
    """Thread-safe store for captured emails during development, testing, and offline runs."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._messages: list[CapturedEmail] = []

    def record(self, message: CapturedEmail) -> None:
        with self._lock:
            self._messages.append(message)

    def get_messages(self) -> list[CapturedEmail]:
        with self._lock:
            return list(self._messages)

    def clear(self) -> None:
        with self._lock:
            self._messages.clear()


email_outbox = InMemoryEmailOutbox()


def send_email(
    settings: Settings,
    to_email: str,
    subject: str,
    text_body: str,
    html_body: str | None = None,
) -> None:
    """Deliver an email via SMTP if configured, always recording to outbox for inspection."""
    now = datetime.now(UTC)
    from_email = settings.mail_from.strip() or f"noreply@{settings.product_name.lower()}.local"

    captured = CapturedEmail(
        to_email=to_email,
        subject=subject,
        text_body=text_body,
        html_body=html_body,
        sent_at=now,
    )
    email_outbox.record(captured)

    smtp_raw = settings.smtp_url.get_secret_value().strip()
    if not smtp_raw:
        _log.info("email_captured_locally", to=to_email, subject=subject)
        return

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = from_email
    msg["To"] = to_email

    msg.attach(MIMEText(text_body, "plain", "utf-8"))
    if html_body:
        msg.attach(MIMEText(html_body, "html", "utf-8"))

    parsed = urllib.parse.urlparse(smtp_raw)
    scheme = parsed.scheme.lower()
    host = parsed.hostname or "localhost"
    port = parsed.port or (465 if scheme == "smtps" else 587)
    username = urllib.parse.unquote(parsed.username) if parsed.username else None
    password = urllib.parse.unquote(parsed.password) if parsed.password else None

    if scheme == "smtps" or port == 465:
        with smtplib.SMTP_SSL(host, port, timeout=10) as server:
            if username and password:
                server.login(username, password)
            server.send_message(msg)
    else:
        with smtplib.SMTP(host, port, timeout=10) as server:
            with contextlib.suppress(smtplib.SMTPNotSupportedError):
                server.starttls()
            if username and password:
                server.login(username, password)
            server.send_message(msg)

    _log.info("email_sent_smtp", to=to_email, host=host, port=port)


def send_invitation_email(
    settings: Settings,
    to_email: str,
    workspace_name: str,
    role: str,
    invite_url: str,
    ui_locale: str = "tr",
) -> None:
    """Send a workspace invitation email with single-use link."""
    product = settings.product_name
    role_labels = {
        "owner": {"tr": "Yönetici (Owner)", "en": "Owner"},
        "manager": {"tr": "Müdür (Manager)", "en": "Manager"},
        "staff": {"tr": "Personel (Staff)", "en": "Staff"},
    }
    role_label = role_labels.get(role, {}).get(ui_locale, role)

    if ui_locale == "en":
        subject = f"[{product}] You have been invited to {workspace_name}"
        text_body = (
            f"Hello,\n\n"
            f"You have been invited to join the '{workspace_name}' workspace as {role_label} "
            f"on {product}.\n\n"
            f"To accept this invitation, please open the link below:\n"
            f"{invite_url}\n\n"
            f"This invitation link will expire in 7 days.\n\n"
            f"Best regards,\n"
            f"The {product} Team"
        )
        html_body = (
            "<div style='font-family: sans-serif; line-height: 1.5; color: #111;'>"
            f"<h2>Welcome to {product}</h2>"
            f"<p>You have been invited to join the <strong>{workspace_name}</strong> workspace as "
            f"<strong>{role_label}</strong>.</p>"
            f"<p><a href='{invite_url}' style='display: inline-block; padding: 10px 20px; "
            "background-color: #2563eb; color: #fff; text-decoration: none; border-radius: 6px;'>"
            "Accept Invitation</a></p>"
            f"<p style='color: #666; font-size: 13px;'>Or copy and paste this link into your "
            f"browser:<br/><a href='{invite_url}'>{invite_url}</a></p>"
            "<p style='color: #888; font-size: 12px;'>This link will expire in 7 days.</p>"
            "</div>"
        )
    else:
        subject = f"[{product}] {workspace_name} çalışma alanına davet edildiniz"
        text_body = (
            f"Merhaba,\n\n"
            f"{product} üzerinde '{workspace_name}' çalışma alanına {role_label} rolüyle "
            f"davet edildiniz.\n\n"
            f"Daveti kabul etmek için aşağıdaki bağlantıyı kullanabilirsiniz:\n"
            f"{invite_url}\n\n"
            f"Bu davet bağlantısı 7 gün boyunca geçerlidir.\n\n"
            f"İyi çalışmalar,\n"
            f"{product} Ekibi"
        )
        html_body = (
            "<div style='font-family: sans-serif; line-height: 1.5; color: #111;'>"
            f"<h2>{product} Çalışma Alanı Daveti</h2>"
            f"<p><strong>{workspace_name}</strong> çalışma alanına <strong>{role_label}</strong> "
            "rolüyle davet edildiniz.</p>"
            f"<p><a href='{invite_url}' style='display: inline-block; padding: 10px 20px; "
            "background-color: #2563eb; color: #fff; text-decoration: none; border-radius: 6px;'>"
            "Daveti Kabul Et</a></p>"
            f"<p style='color: #666; font-size: 13px;'>Veya bu bağlantıyı tarayıcınıza yapıştırın:"
            f"<br/><a href='{invite_url}'>{invite_url}</a></p>"
            "<p style='color: #888; font-size: 12px;'>Bu bağlantı 7 gün süreyle geçerlidir.</p>"
            "</div>"
        )

    send_email(settings, to_email, subject, text_body, html_body)


def send_password_reset_email(
    settings: Settings,
    to_email: str,
    reset_url: str,
    ui_locale: str = "tr",
) -> None:
    """Send a password reset email with secure, single-use, 60-minute token link."""
    product = settings.product_name

    if ui_locale == "en":
        subject = f"[{product}] Password reset request"
        text_body = (
            f"Hello,\n\n"
            f"We received a request to reset the password for your {product} account\n"
            f"({to_email}).\n\n"
            f"Click the link below to set a new password:\n"
            f"{reset_url}\n\n"
            f"This link is single-use and will expire in 60 minutes.\n"
            f"If you did not request this, please disregard this email; your account is secure.\n\n"
            f"Best regards,\n"
            f"The {product} Team"
        )
        html_body = (
            "<div style='font-family: sans-serif; line-height: 1.5; color: #111;'>"
            f"<h2>Password Reset Request</h2>"
            f"<p>We received a request to reset the password for your {product} account.</p>"
            f"<p><a href='{reset_url}' style='display: inline-block; padding: 10px 20px; "
            "background-color: #2563eb; color: #fff; text-decoration: none; border-radius: 6px;'>"
            "Reset Password</a></p>"
            f"<p style='color: #666; font-size: 13px;'>Or copy and paste this link into your "
            f"browser:<br/><a href='{reset_url}'>{reset_url}</a></p>"
            "<p style='color: #888; font-size: 12px;'>This single-use link will expire in "
            "60 minutes. If you did not request this reset, you can safely ignore this email.</p>"
            "</div>"
        )
    else:
        subject = f"[{product}] Şifre sıfırlama talebi"
        text_body = (
            f"Merhaba,\n\n"
            f"{product} hesabınız ({to_email}) için bir şifre sıfırlama talebi aldık.\n\n"
            f"Yeni bir şifre belirlemek için aşağıdaki bağlantıya tıklayabilirsiniz:\n"
            f"{reset_url}\n\n"
            f"Bu bağlantı tek kullanımlıktır ve 60 dakika içinde geçerliliğini yitirecektir.\n"
            f"Eğer bu talebi siz yapmadıysanız bu e-postayı dikkate almayınız.\n\n"
            f"İyi çalışmalar,\n"
            f"{product} Ekibi"
        )
        html_body = (
            "<div style='font-family: sans-serif; line-height: 1.5; color: #111;'>"
            f"<h2>Şifre Sıfırlama Talebi</h2>"
            f"<p>{product} hesabınız için bir şifre sıfırlama talebi aldık.</p>"
            f"<p><a href='{reset_url}' style='display: inline-block; padding: 10px 20px; "
            "background-color: #2563eb; color: #fff; text-decoration: none; border-radius: 6px;'>"
            "Şifremi Sıfırla</a></p>"
            f"<p style='color: #666; font-size: 13px;'>Veya bu bağlantıyı tarayıcınıza yapıştırın:"
            f"<br/><a href='{reset_url}'>{reset_url}</a></p>"
            "<p style='color: #888; font-size: 12px;'>Bu tek kullanımlık bağlantı 60 dakika "
            "süresince geçerlidir. Talebi siz yapmadıysanız bu e-postayı güvenle "
            "yok sayabilirsiniz.</p></div>"
        )

    send_email(settings, to_email, subject, text_body, html_body)
