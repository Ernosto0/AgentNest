"""When may a fact be used? (business-knowledge.md §1) Pure functions, no database.

A fact is **usable** when it is verified, not archived, inside its validity window (compared
as a date in the *workspace* timezone, INV-19) and has no pending ``contest`` candidate. Only
usable facts are given to LLM tasks or rendered into customer-facing text (INV-02).
"""

from datetime import date, datetime
from zoneinfo import ZoneInfo


def local_today(now: datetime, timezone: str) -> date:
    """The calendar date of the instant ``now`` in the workspace timezone."""
    return now.astimezone(ZoneInfo(timezone)).date()


def window_state(valid_from: date | None, valid_until: date | None, today: date) -> str:
    """``active`` | ``not_started`` | ``expired`` (both bounds inclusive)."""
    if valid_from is not None and today < valid_from:
        return "not_started"
    if valid_until is not None and today > valid_until:
        return "expired"
    return "active"


def display_state(
    *,
    status: str,
    valid_from: date | None,
    valid_until: date | None,
    today: date,
    contested: bool,
) -> str:
    """One UI label: archived, unverified, contested, expired, not_started or verified."""
    if status != "verified":
        return status
    if contested:
        return "contested"
    window = window_state(valid_from, valid_until, today)
    return "verified" if window == "active" else window


def is_usable(
    *,
    status: str,
    valid_from: date | None,
    valid_until: date | None,
    today: date,
    contested: bool,
) -> bool:
    return (
        status == "verified"
        and not contested
        and window_state(valid_from, valid_until, today) == "active"
    )
