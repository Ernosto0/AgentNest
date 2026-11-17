from datetime import UTC, datetime

import pytest

from app.ai.schemas import CommandTime
from app.commands.manage import instant
from app.commands.resolver import ContentContext
from app.content.scheduling import ScheduleError


@pytest.mark.parametrize(("zone", "expected"), [("Europe/Istanbul", 6), ("America/New_York", 13)])
def test_tomorrow_morning_uses_workspace_day_and_dst(zone, expected):
    context = ContentContext((), {}, zone, now=datetime(2026, 3, 7, 20, tzinfo=UTC))
    assert instant(CommandTime(local_date="tomorrow", local_time="morning"), context) == datetime(
        2026, 3, 8, expected, tzinfo=UTC
    )


def test_clock_gap_is_refused_and_fold_is_explicit_earlier_instant():
    context = ContentContext((), {}, "America/New_York", now=datetime(2026, 3, 7, 20, tzinfo=UTC))
    with pytest.raises(ScheduleError, match="SCHEDULE_TIME_NONEXISTENT"):
        instant(CommandTime(local_date="tomorrow", local_time="02:30"), context)
    context = ContentContext((), {}, "America/New_York", now=datetime(2026, 10, 31, 20, tzinfo=UTC))
    assert instant(CommandTime(local_date="tomorrow", local_time="01:30"), context) == datetime(
        2026, 11, 1, 5, 30, tzinfo=UTC
    )
