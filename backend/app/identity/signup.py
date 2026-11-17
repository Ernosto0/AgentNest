"""Self-service registration and single-use, signed email verification.

Use the reset flow's random tokens, hash-only persistence, trusted frontend origin,
post-commit email delivery and injected Clock. Verification tokens have their own
purpose-bound HMAC and can never be used as password reset or session tokens.
"""

import hashlib
import hmac
from datetime import timedelta

from fastapi import BackgroundTasks
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.audit import service as audit
from app.core.clock import Clock
from app.core.config import Settings
from app.core.context import ActorRef
from app.core.email import send_signup_email
from app.core.errors import AppError
from app.core.security import generate_token, hash_password, hash_token, password_policy_problems
from app.identity.legal import TERMS_VERSION
from app.identity.models import User
from app.identity.schemas import RegisterRequest

VERIFICATION_TTL = timedelta(hours=24)


def _signature(settings: Settings, payload: str) -> str:
    return hmac.new(
        settings.secret_key.get_secret_value().encode(),
        f"email-verification:{payload}".encode(),
        hashlib.sha256,
    ).hexdigest()


def issue_token(settings: Settings, clock: Clock) -> str:
    payload = f"{generate_token()}.{int((clock.now() + VERIFICATION_TTL).timestamp())}"
    return f"{payload}.{_signature(settings, payload)}"


def validate_token(settings: Settings, clock: Clock, token: str) -> None:
    try:
        nonce, expires, signature = token.split(".")
        valid = (
            bool(nonce)
            and hmac.compare_digest(signature, _signature(settings, f"{nonce}.{expires}"))
            and int(expires) > clock.now().timestamp()
        )
    except (ValueError, UnicodeError):
        valid = False
    if not valid:
        raise AppError("EMAIL_VERIFICATION_TOKEN_INVALID")


def _queue_verification(
    db: Session, clock: Clock, settings: Settings, user: User, tasks: BackgroundTasks
) -> None:
    token = issue_token(settings, clock)
    user.verification_token_hash = hash_token(token)
    user.verification_expires_at = clock.now() + VERIFICATION_TTL
    base = (settings.frontend_origin or settings.app_base_url).rstrip("/")
    tasks.add_task(
        send_signup_email,
        settings,
        user.email,
        f"{base}/verify-email/{token}",
        user.ui_locale,
        False,
    )


def register(
    db: Session, clock: Clock, settings: Settings, body: RegisterRequest, tasks: BackgroundTasks
) -> None:
    if body.accepted_terms_version != TERMS_VERSION:
        raise AppError(
            "VALIDATION_FAILED",
            errors=[{"field": "accepted_terms_version", "code": "invalid_version", "params": {}}],
        )
    problems = password_policy_problems(body.password)
    if problems:
        raise AppError("PASSWORD_TOO_WEAK")
    # Always hash, including duplicates. ON CONFLICT makes simultaneous registrations generic.
    password_hash = hash_password(body.password)
    user_id = db.scalar(
        insert(User)
        .values(
            email=body.email,
            password_hash=password_hash,
            display_name=body.name,
            ui_locale=body.ui_locale,
            email_verified=False,
            accepted_terms_version=TERMS_VERSION,
            terms_accepted_at=clock.now(),
        )
        .on_conflict_do_nothing(index_elements=[User.email])
        .returning(User.id)
    )
    if user_id is not None:
        user = db.get(User, user_id)
        if user is None:  # INSERT RETURNING guarantees the row exists.
            raise RuntimeError("registered user missing")
        _queue_verification(db, clock, settings, user, tasks)
        audit.record(
            db,
            None,
            "auth.registered",
            "user",
            user.id,
            {"terms_version": TERMS_VERSION},
            actor=ActorRef.user(user.id),
            clock=clock,
        )
    else:
        base = (settings.frontend_origin or settings.app_base_url).rstrip("/")
        tasks.add_task(
            send_signup_email, settings, body.email, f"{base}/login", body.ui_locale, True
        )
    db.commit()


def resend(
    db: Session, clock: Clock, settings: Settings, email: str, tasks: BackgroundTasks
) -> None:
    user = db.scalar(select(User).where(User.email == email.strip().lower()).with_for_update())
    if user is not None and user.is_active:
        if not user.email_verified:
            _queue_verification(db, clock, settings, user, tasks)
            audit.record(db, None, "auth.verification_requested", "user", user.id, clock=clock)
        else:
            base = (settings.frontend_origin or settings.app_base_url).rstrip("/")
            tasks.add_task(
                send_signup_email, settings, user.email, f"{base}/login", user.ui_locale, True
            )
    db.commit()


def verify(db: Session, clock: Clock, settings: Settings, token: str) -> None:
    validate_token(settings, clock, token)
    user = db.scalar(
        select(User).where(User.verification_token_hash == hash_token(token)).with_for_update()
    )
    if (
        user is None
        or not user.is_active
        or user.email_verified
        or user.verification_expires_at is None
        or user.verification_expires_at <= clock.now()
    ):
        raise AppError("EMAIL_VERIFICATION_TOKEN_INVALID")
    user.email_verified = True
    user.email_verified_at = clock.now()
    user.verification_token_hash = None
    user.verification_expires_at = None
    audit.record(
        db, None, "auth.email_verified", "user", user.id, actor=ActorRef.user(user.id), clock=clock
    )
    db.commit()
