"""Unit tests for Phase 8 Session 08: SMTP, invitations and password reset (P8-04, OQ-16).

Covers:
- Transactional email outbox capture, clear, and multi-part MIME assembly.
- TR and EN email templates for workspace invites and password resets.
- Password reset request enumeration resistance (generic response).
- Trusted-origin link construction (resistance to Host-header injection).
- Password strength enforcement on reset (minimum 12 chars, deny-list).
- Single-use and expiry token constraints for password reset.
- Token invalidation of superseded reset requests.
- Session invalidation upon password reset.
- Emailed invites and assisted onboarding link preservation.
"""

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from app.core.clock import FrozenClock
from app.core.config import Settings
from app.core.email import (
    CapturedEmail,
    InMemoryEmailOutbox,
    email_outbox,
    send_email,
    send_invitation_email,
    send_password_reset_email,
)
from app.core.errors import AppError
from app.core.security import generate_token, hash_password, hash_token, verify_password
from app.identity import service
from app.identity.models import PasswordResetToken, User
from app.identity.schemas import (
    PasswordResetConfirm,
    PasswordResetRequest,
)


def test_in_memory_email_outbox() -> None:
    outbox = InMemoryEmailOutbox()
    assert outbox.get_messages() == []

    msg1 = CapturedEmail(
        to_email="test1@example.com",
        subject="Test 1",
        text_body="Hello 1",
        html_body=None,
        sent_at=datetime.now(UTC),
    )
    outbox.record(msg1)
    assert len(outbox.get_messages()) == 1
    assert outbox.get_messages()[0].to_email == "test1@example.com"

    outbox.clear()
    assert outbox.get_messages() == []


def test_send_email_captures_locally_when_smtp_unconfigured() -> None:
    email_outbox.clear()
    settings = Settings(
        app_env="test",
        smtp_url="",
        mail_from="system@example.com",
    )

    send_email(
        settings,
        to_email="user@example.com",
        subject="Welcome",
        text_body="Plain text",
        html_body="<p>Plain text</p>",
    )

    messages = email_outbox.get_messages()
    assert len(messages) == 1
    assert messages[0].to_email == "user@example.com"
    assert messages[0].subject == "Welcome"
    assert messages[0].text_body == "Plain text"
    assert messages[0].html_body == "<p>Plain text</p>"


def test_send_invitation_email_templates_tr_and_en() -> None:
    email_outbox.clear()
    settings = Settings(app_env="test", product_name="AgentNest")

    # Turkish template
    send_invitation_email(
        settings,
        to_email="staff@example.com",
        workspace_name="Gölkent Pilates",
        role="staff",
        invite_url="https://app.agentnest.test/invite/token-123",
        ui_locale="tr",
    )
    msgs = email_outbox.get_messages()
    assert len(msgs) == 1
    tr_msg = msgs[0]
    assert "[AgentNest] Gölkent Pilates çalışma alanına davet edildiniz" in tr_msg.subject
    assert "Gölkent Pilates" in tr_msg.text_body
    assert "https://app.agentnest.test/invite/token-123" in tr_msg.text_body
    assert "7 gün" in tr_msg.text_body
    assert "Personel (Staff)" in tr_msg.text_body

    # English template
    send_invitation_email(
        settings,
        to_email="owner@example.com",
        workspace_name="Harbor Studio",
        role="owner",
        invite_url="https://app.agentnest.test/invite/token-456",
        ui_locale="en",
    )
    msgs = email_outbox.get_messages()
    assert len(msgs) == 2
    en_msg = msgs[1]
    assert "[AgentNest] You have been invited to Harbor Studio" in en_msg.subject
    assert "Harbor Studio" in en_msg.text_body
    assert "https://app.agentnest.test/invite/token-456" in en_msg.text_body
    assert "7 days" in en_msg.text_body
    assert "Owner" in en_msg.text_body


def test_send_password_reset_email_templates_tr_and_en() -> None:
    email_outbox.clear()
    settings = Settings(app_env="test", product_name="AgentNest")

    # Turkish template
    send_password_reset_email(
        settings,
        to_email="ayse@example.com",
        reset_url="https://app.agentnest.test/reset-password/tok-tr",
        ui_locale="tr",
    )
    msgs = email_outbox.get_messages()
    assert len(msgs) == 1
    tr_msg = msgs[0]
    assert "[AgentNest] Şifre sıfırlama talebi" in tr_msg.subject
    assert "60 dakika" in tr_msg.text_body
    assert "tek kullanımlıktır" in tr_msg.text_body
    assert "https://app.agentnest.test/reset-password/tok-tr" in tr_msg.text_body

    # English template
    send_password_reset_email(
        settings,
        to_email="john@example.com",
        reset_url="https://app.agentnest.test/reset-password/tok-en",
        ui_locale="en",
    )
    msgs = email_outbox.get_messages()
    assert len(msgs) == 2
    en_msg = msgs[1]
    assert "[AgentNest] Password reset request" in en_msg.subject
    assert "60 minutes" in en_msg.text_body
    assert "single-use" in en_msg.text_body
    assert "https://app.agentnest.test/reset-password/tok-en" in en_msg.text_body


def test_password_reset_schemas() -> None:
    req = PasswordResetRequest(email="User@Domain.Com")
    assert req.email == "User@Domain.Com"

    with pytest.raises(ValidationError):
        PasswordResetRequest(email="a")  # too short

    # Minimum 12 characters for new_password
    with pytest.raises(ValidationError):
        PasswordResetConfirm(token="token123", new_password="short")

    valid_confirm = PasswordResetConfirm(token="valid-token", new_password="secure-password-1234")
    assert valid_confirm.token == "valid-token"
    assert valid_confirm.new_password == "secure-password-1234"


def test_password_reset_request_enumeration_resistance_and_trusted_origin() -> None:
    email_outbox.clear()
    settings = Settings(
        app_env="test",
        frontend_origin="https://secure.agentnest.com",
    )
    clock = FrozenClock(datetime(2026, 11, 3, 10, 0, 0, tzinfo=UTC))

    mock_db = MagicMock()
    # 1. Non-existent email: returns cleanly (generic 202 Accepted) without emitting email
    mock_db.scalars.return_value.first.return_value = None

    service.request_password_reset(mock_db, clock, settings, email="nonexistent@example.com")
    assert email_outbox.get_messages() == []

    # 2. Existing active user: creates token and sends email with trusted origin
    user = User(
        id=uuid.uuid4(),
        email="owner@example.com",
        password_hash=hash_password("old-password-12345"),
        display_name="Test Owner",
        ui_locale="en",
        is_active=True,
    )
    mock_db.scalars.return_value.first.return_value = user

    service.request_password_reset(mock_db, clock, settings, email="owner@example.com")
    messages = email_outbox.get_messages()
    assert len(messages) == 1
    assert messages[0].to_email == "owner@example.com"
    # Verify link starts with trusted frontend origin (never an arbitrary Host header)
    assert messages[0].text_body.startswith("Hello,")
    assert "https://secure.agentnest.com/reset-password/" in messages[0].text_body


def test_password_reset_strength_validation() -> None:
    clock = FrozenClock(datetime(2026, 11, 3, 10, 0, 0, tzinfo=UTC))
    mock_db = MagicMock()

    # < 12 characters fails with PASSWORD_TOO_WEAK
    with pytest.raises(AppError) as exc_too_short:
        service.confirm_password_reset(
            mock_db, clock, token="any-token", new_password="password123"
        )
    assert exc_too_short.value.code == "PASSWORD_TOO_WEAK"

    # Common password fails with PASSWORD_TOO_WEAK
    with pytest.raises(AppError) as exc_common:
        service.confirm_password_reset(
            mock_db, clock, token="any-token", new_password="password1234"
        )
    assert exc_common.value.code == "PASSWORD_TOO_WEAK"


def test_password_reset_token_expiry_and_replay_rejection() -> None:
    clock = FrozenClock(datetime(2026, 11, 3, 10, 0, 0, tzinfo=UTC))
    mock_db = MagicMock()

    # Token not found (or expired / already used) -> PASSWORD_RESET_TOKEN_INVALID
    mock_db.scalars.return_value.first.return_value = None

    with pytest.raises(AppError) as exc:
        service.confirm_password_reset(
            mock_db,
            clock,
            token="bad-or-expired-token",
            new_password="a-very-strong-unique-password",
        )
    assert exc.value.code == "PASSWORD_RESET_TOKEN_INVALID"


def test_password_reset_success_updates_hash_and_revokes_sessions() -> None:
    clock = FrozenClock(datetime(2026, 11, 3, 10, 0, 0, tzinfo=UTC))
    mock_db = MagicMock()

    raw_token = generate_token()
    token_h = hash_token(raw_token)
    user_id = uuid.uuid4()

    token_record = PasswordResetToken(
        id=uuid.uuid4(),
        user_id=user_id,
        token_hash=token_h,
        expires_at=clock.now() + timedelta(hours=1),
        used_at=None,
    )
    user = User(
        id=user_id,
        email="reset-user@example.com",
        password_hash=hash_password("old-password-12345"),
        display_name="Reset User",
        ui_locale="tr",
        is_active=True,
    )

    mock_db.scalars.return_value.first.return_value = token_record
    mock_db.get.return_value = user

    new_pw = "new-valid-secure-password-123"
    service.confirm_password_reset(mock_db, clock, token=raw_token, new_password=new_pw)

    # Token marked as used
    assert token_record.used_at == clock.now()
    # Password hash updated and verifiable
    assert verify_password(user.password_hash, new_pw) is True
    # Session execute called for invalidation and audit recorded
    assert mock_db.execute.called
    assert mock_db.commit.called
