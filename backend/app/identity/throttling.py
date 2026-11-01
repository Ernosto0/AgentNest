"""Login throttling and client IP extraction (P8-04 / ADR-025 §2)."""

import hashlib
import ipaddress
import math
from datetime import timedelta

from fastapi import Request
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.audit import service as audit
from app.core.clock import Clock
from app.core.config import Settings
from app.core.errors import AppError
from app.identity.models import LoginThrottle

THROTTLE_WINDOW_MINUTES = 15
LOCKOUT_SCHEDULE_SECONDS = (60, 300, 900, 3600)  # 5th attempt: 60s, 6th: 300s, 7th: 900s, 8+: 3600s
FAILURES_BEFORE_LOCKOUT = 5


def hash_identifier(value: str) -> str:
    """Return SHA-256 hex digest of the normalized identifier."""
    return hashlib.sha256(value.strip().lower().encode("utf-8")).hexdigest()


def extract_client_ip(request: Request, settings: Settings) -> str:
    """Extract client IP, honoring X-Forwarded-For only if peer is a trusted proxy.

    ADR-025 §2.1: Client IP is read from request.client.host by default; X-Forwarded-For is
    honored ONLY when the immediate peer IP is in configured TRUSTED_PROXY_CIDRS,
    preventing header spoofing.
    """
    peer = request.client.host if request.client else "127.0.0.1"
    try:
        peer_ip = ipaddress.ip_address(peer)
    except ValueError:
        return peer

    is_trusted = any(peer_ip in net for net in settings.trusted_proxy_networks)
    if not is_trusted:
        return peer

    xff = request.headers.get("x-forwarded-for")
    if not xff:
        return peer

    # Parse comma-separated IPs from right to left (standard secure reverse proxy parsing)
    ips = [entry.strip() for entry in xff.split(",") if entry.strip()]
    for raw in reversed(ips):
        try:
            parsed = ipaddress.ip_address(raw)
        except ValueError:
            continue
        if not any(parsed in net for net in settings.trusted_proxy_networks):
            return raw
    return ips[0] if ips else peer


def check_login_throttle(
    session: Session,
    clock: Clock,
    *,
    email: str,
    ip_address: str,
) -> None:
    """Check if either email or IP is currently locked out.

    If locked, emits auth.login_throttled audit and raises 429 RATE_LIMITED with Retry-After.
    """
    now = clock.now()
    email_h = hash_identifier(email)
    ip_h = hash_identifier(ip_address)

    throttles = list(
        session.scalars(
            select(LoginThrottle).where(
                (
                    (LoginThrottle.identifier_type == "email")
                    & (LoginThrottle.identifier_hash == email_h)
                )
                | (
                    (LoginThrottle.identifier_type == "ip")
                    & (LoginThrottle.identifier_hash == ip_h)
                )
            )
        )
    )

    locked = [t for t in throttles if t.locked_until and t.locked_until > now]
    if not locked:
        return

    max_locked = max(t.locked_until for t in locked if t.locked_until is not None)
    retry_after = max(1, math.ceil((max_locked - now).total_seconds()))

    audit.record(
        session,
        None,
        "auth.login_throttled",
        "user",
        None,
        {
            "retry_after": retry_after,
            "email_sha256": email_h,
            "ip_sha256": ip_h,
            "locked_targets": [t.identifier_type for t in locked],
        },
        clock=clock,
    )
    session.commit()

    raise AppError(
        "RATE_LIMITED",
        headers={"Retry-After": str(retry_after)},
        retry_after=retry_after,
    )


def record_login_failure(
    session: Session,
    clock: Clock,
    *,
    email: str,
    ip_address: str,
) -> None:
    """Record a failed login attempt for both email and IP with exponential lockout."""
    now = clock.now()
    targets = [
        ("email", hash_identifier(email)),
        ("ip", hash_identifier(ip_address)),
    ]

    for id_type, id_hash in targets:
        row = session.scalars(
            select(LoginThrottle)
            .where(
                (LoginThrottle.identifier_type == id_type)
                & (LoginThrottle.identifier_hash == id_hash)
            )
            .with_for_update()
        ).first()

        if row is None:
            session.add(
                LoginThrottle(
                    identifier_type=id_type,
                    identifier_hash=id_hash,
                    failed_attempts=1,
                    first_failed_at=now,
                    last_failed_at=now,
                    locked_until=None,
                )
            )
        else:
            # Check if 15-minute window has elapsed and row is not locked
            window_expired = now - row.last_failed_at > timedelta(minutes=THROTTLE_WINDOW_MINUTES)
            is_currently_locked = row.locked_until is not None and row.locked_until > now

            if window_expired and not is_currently_locked:
                row.failed_attempts = 1
                row.first_failed_at = now
                row.last_failed_at = now
                row.locked_until = None
            else:
                row.failed_attempts += 1
                row.last_failed_at = now
                if row.failed_attempts >= FAILURES_BEFORE_LOCKOUT:
                    idx = min(
                        row.failed_attempts - FAILURES_BEFORE_LOCKOUT,
                        len(LOCKOUT_SCHEDULE_SECONDS) - 1,
                    )
                    lock_duration = LOCKOUT_SCHEDULE_SECONDS[idx]
                    row.locked_until = now + timedelta(seconds=lock_duration)


def record_login_success(
    session: Session,
    *,
    email: str,
    ip_address: str,
) -> None:
    """Clear failed attempt records for email and IP upon successful login."""
    email_h = hash_identifier(email)
    ip_h = hash_identifier(ip_address)
    session.execute(
        delete(LoginThrottle).where(
            (
                (LoginThrottle.identifier_type == "email")
                & (LoginThrottle.identifier_hash == email_h)
            )
            | ((LoginThrottle.identifier_type == "ip") & (LoginThrottle.identifier_hash == ip_h))
        )
    )
