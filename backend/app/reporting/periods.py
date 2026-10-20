"""Report periods in the workspace timezone (INV-19).

A local day is ``[local 00:00, next local 00:00)`` converted to UTC with ``zoneinfo``, so a day
that contains a DST change is 23 or 25 hours long. Wall-clock arithmetic is done on aware local
datetimes (never by adding 24 h to an instant).
"""

from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo


def local_midnight(local_date: date, zone: ZoneInfo) -> datetime:
    """00:00 of ``local_date`` on the wall clock of ``zone``."""
    return datetime.combine(local_date, time.min, tzinfo=zone)


def day_bounds(local_date: date, timezone: str) -> tuple[datetime, datetime]:
    """``[start, end)`` in UTC of the local day ``local_date`` in ``timezone``."""
    zone = ZoneInfo(timezone)
    start = local_midnight(local_date, zone)
    end = local_midnight(local_date + timedelta(days=1), zone)
    return start.astimezone(UTC), end.astimezone(UTC)


def local_date_of(instant: datetime, timezone: str) -> date:
    """The local calendar date of ``instant`` in ``timezone``."""
    return instant.astimezone(ZoneInfo(timezone)).date()


def period_bounds(period: str, now: datetime, timezone: str) -> tuple[datetime, datetime]:
    """``[start, end)`` in UTC for ``period`` in the workspace timezone (INV-19).

    ``today`` and ``last_7_days`` end now; ``yesterday`` ends at local midnight. The result is
    expressed in the time zone of ``now``.
    """
    zone = ZoneInfo(timezone)
    local_now = now.astimezone(zone)
    midnight = local_midnight(local_now.date(), zone)
    if period == "yesterday":
        start, end = midnight - timedelta(days=1), midnight
    elif period == "last_7_days":
        start, end = midnight - timedelta(days=6), local_now
    else:
        start, end = midnight, local_now
    return start.astimezone(now.tzinfo), end.astimezone(now.tzinfo)
