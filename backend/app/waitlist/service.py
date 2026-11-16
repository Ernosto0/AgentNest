"""Waitlist submissions: validate (schema), throttle, store once per email, tell the operator.

The operator email is sent after the commit and only for a new email, so a repeated submission
changes nothing and sends nothing (idempotent). A failing mail transport never fails the request:
the row is already stored, and ``waitlist-list`` shows it. The email address is personal data and
never appears in a log line; log events carry a short hash instead.
"""

import hashlib

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.core.clock import Clock
from app.core.config import Settings
from app.core.email import send_email
from app.core.logging import get_logger
from app.identity import throttling
from app.waitlist.models import WaitlistEntry
from app.waitlist.schemas import WaitlistRequest, normalize_email

_log = get_logger("app.waitlist")


def email_tag(email: str) -> str:
    """A short, non-reversible tag for log lines."""
    return hashlib.sha256(normalize_email(email).encode("utf-8")).hexdigest()[:12]


def submit(
    session: Session,
    clock: Clock,
    *,
    body: WaitlistRequest,
    ip_address: str,
) -> WaitlistRequest | None:
    """Throttle, then store the entry. Returns ``body`` when the email is new, else ``None``."""
    throttling.enforce_waitlist_throttle(session, clock, email=body.email, ip_address=ip_address)
    inserted = session.execute(
        pg_insert(WaitlistEntry)
        .values(
            email=body.email,
            email_normalized=normalize_email(body.email),
            business_name=body.business_name,
            category=body.category,
            instagram_handle=body.instagram_handle,
            city=body.city,
            locale=body.locale,
        )
        .on_conflict_do_nothing(index_elements=["email_normalized"])
        .returning(WaitlistEntry.id)
    ).first()
    session.commit()
    _log.info("waitlist_submission", email_tag=email_tag(body.email), is_new=inserted is not None)
    return body if inserted is not None else None


def notify_operator(settings: Settings, entry: WaitlistRequest) -> None:
    """Email ``OPERATOR_ALERT_EMAIL`` about a new entry. Best effort: never raises."""
    recipient = settings.operator_alert_email.strip()
    if not recipient:
        _log.info("waitlist_notice_skipped_no_recipient", email_tag=email_tag(entry.email))
        return
    lines = [
        f"A new pilot waitlist request arrived on {settings.product_name}.",
        "",
        f"Email:     {entry.email}",
        f"Business:  {entry.business_name or '-'}",
        f"Type:      {entry.category or '-'}",
        f"Instagram: {entry.instagram_handle or '-'}",
        f"City:      {entry.city or '-'}",
        f"Language:  {entry.locale}",
        "",
        "All entries: uv run python -m app.cli waitlist-list",
    ]
    try:
        send_email(
            settings,
            recipient,
            f"[{settings.product_name}] New pilot waitlist request",
            "\n".join(lines),
        )
    except Exception as exc:  # best effort: the row is stored, the operator can list it
        _log.warning(
            "waitlist_notice_failed", email_tag=email_tag(entry.email), error=type(exc).__name__
        )


def list_entries(session: Session) -> list[WaitlistEntry]:
    return list(session.scalars(select(WaitlistEntry).order_by(WaitlistEntry.created_at)))


def delete_by_email(session: Session, email: str) -> int:
    """Remove an entry on the person's request. Returns the number of rows deleted."""
    result = session.execute(
        delete(WaitlistEntry).where(WaitlistEntry.email_normalized == normalize_email(email))
    )
    session.commit()
    return int(result.rowcount)  # type: ignore[attr-defined]
