"""Schedule rules of a content item (workflows.md section E step 4, plan.md G5/G13/G16).

Pure: no database, no clock of its own (``now`` is passed in), so every rule is a unit test.

- The owner gives a **local** date and time (workspace timezone) or ``"now"``. The instant is
  stored in UTC (INV-19).
- A local time that does not exist (the hour skipped when clocks go forward) is an error,
  ``SCHEDULE_TIME_NONEXISTENT``. One that exists twice (the hour repeated when they go back)
  is the **earlier** instant (``fold=0``); ``schedule_local`` shows it back to the owner.
- The instant must be within ``now - 1 min <= t <= now + 60 days``. When the item waits for a
  person's approval the instant must also be at least 15 minutes ahead.
- No rolling 24 h window around the instant may hold more posts than the daily limit.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta, tzinfo
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

SCHEDULE_IN_PAST = "SCHEDULE_IN_PAST"
SCHEDULE_TOO_FAR = "SCHEDULE_TOO_FAR"
SCHEDULE_TIME_NONEXISTENT = "SCHEDULE_TIME_NONEXISTENT"
SCHEDULE_TOO_SOON_FOR_APPROVAL = "SCHEDULE_TOO_SOON_FOR_APPROVAL"

PAST_TOLERANCE = timedelta(minutes=1)
MAX_AHEAD = timedelta(days=60)
# Someone has to decide before the post goes out (plan.md: staff cannot "publish now").
MIN_LEAD_FOR_APPROVAL = timedelta(minutes=15)
QUOTA_WINDOW = timedelta(hours=24)


class ScheduleError(Exception):
    """The requested schedule is not acceptable; ``code`` is one of the ``SCHEDULE_*`` codes."""

    def __init__(self, code: str, **params: object) -> None:
        super().__init__(code)
        self.code = code
        self.params = params


@dataclass(frozen=True)
class ResolvedSchedule:
    scheduled_at: datetime  # UTC
    # What the owner asked for, kept on the item (``schedule_input``).
    input: dict[str, object]


def _zone(timezone: str) -> tzinfo:
    try:
        return ZoneInfo(timezone)
    except ZoneInfoNotFoundError:  # a workspace always has a valid zone; stay safe
        return UTC


def local_to_utc(local_date: date, local_time: str, timezone: str) -> tuple[datetime, bool]:
    """``(instant in UTC, ambiguous)`` for a wall-clock time in ``timezone`` (G13).

    Raises ``ScheduleError(SCHEDULE_TIME_NONEXISTENT)`` for a time inside a clock gap.
    """
    hour, minute = (int(part) for part in local_time.split(":"))
    zone = _zone(timezone)
    naive = datetime(local_date.year, local_date.month, local_date.day, hour, minute)
    earlier = naive.replace(tzinfo=zone, fold=0)
    later = naive.replace(tzinfo=zone, fold=1)
    instant = earlier.astimezone(UTC)
    if instant.astimezone(zone).replace(tzinfo=None) != naive:
        raise ScheduleError(
            SCHEDULE_TIME_NONEXISTENT,
            local_date=local_date.isoformat(),
            local_time=local_time,
            timezone=timezone,
        )
    return instant, earlier.utcoffset() != later.utcoffset()


def resolve(
    *,
    now: datetime,
    timezone: str,
    local_date: date | None = None,
    local_time: str | None = None,
    publish_now: bool = False,
    needs_approval: bool,
) -> ResolvedSchedule:
    """The UTC instant for a request, or a ``ScheduleError``.

    ``needs_approval`` is true when a person other than the submitter's own grant must decide
    first: the instant must then be at least 15 minutes ahead (so "now" is impossible).
    """
    if publish_now:
        instant = now
        schedule_input: dict[str, object] = {"mode": "now"}
    else:
        if local_date is None or local_time is None:
            raise ValueError("a local schedule needs a date and a time")
        instant, ambiguous = local_to_utc(local_date, local_time, timezone)
        schedule_input = {
            "mode": "local",
            "local_date": local_date.isoformat(),
            "local_time": local_time,
            "timezone": timezone,
        }
        if ambiguous:
            schedule_input["ambiguous"] = True  # the earlier of the two instants was taken

    if instant < now - PAST_TOLERANCE:
        raise ScheduleError(SCHEDULE_IN_PAST)
    if instant > now + MAX_AHEAD:
        raise ScheduleError(SCHEDULE_TOO_FAR)
    if needs_approval and instant < now + MIN_LEAD_FOR_APPROVAL:
        raise ScheduleError(
            SCHEDULE_TOO_SOON_FOR_APPROVAL,
            minutes=int(MIN_LEAD_FOR_APPROVAL.total_seconds() // 60),
        )
    return ResolvedSchedule(scheduled_at=instant, input=schedule_input)


def quota_forecast_exceeded(existing: Iterable[datetime], instant: datetime, limit: int) -> bool:
    """Would adding a post at ``instant`` put more than ``limit`` posts in some rolling 24 h
    window that contains ``instant``? ``existing`` are the instants of the posts that already
    are, or will be, on the account (a post leaves the window exactly 24 h after it goes out,
    as in the mock's quota)."""
    times = sorted([*existing, instant])
    for start in times:
        if not (instant - QUOTA_WINDOW < start <= instant):
            continue  # this window does not contain ``instant``
        count = sum(1 for other in times if start <= other < start + QUOTA_WINDOW)
        if count > limit:
            return True
    return False
