"""Pure tests for Reel polling backoff schedule and constants."""

from datetime import timedelta

from app.operations.jobs import STUCK_AFTER
from app.operations.publish import (
    REEL_POLL_SCHEDULE,
    REEL_PROCESSING_TIMEOUT,
    reel_poll_delay_seconds,
)


def test_reel_poll_schedule_repeats_last_value_and_stays_under_stuck_after() -> None:
    assert REEL_POLL_SCHEDULE == (15, 30, 60, 60, 120, 120, 180, 180, 300)
    assert timedelta(minutes=30) == REEL_PROCESSING_TIMEOUT
    assert all(timedelta(seconds=s) < STUCK_AFTER for s in REEL_POLL_SCHEDULE)
    for idx, expected in enumerate(REEL_POLL_SCHEDULE):
        assert reel_poll_delay_seconds(idx) == expected
    assert reel_poll_delay_seconds(-1) == REEL_POLL_SCHEDULE[0]
    assert reel_poll_delay_seconds(len(REEL_POLL_SCHEDULE)) == REEL_POLL_SCHEDULE[-1]
    assert reel_poll_delay_seconds(100) == REEL_POLL_SCHEDULE[-1]
