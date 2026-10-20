"""Report periods in the workspace timezone (INV-19)."""

from datetime import UTC, date, datetime, timedelta

import pytest

from app.reporting.periods import day_bounds, local_date_of, period_bounds

ISTANBUL = "Europe/Istanbul"
LISBON = "Europe/Lisbon"


def utc(*args: int) -> datetime:
    return datetime(*args, tzinfo=UTC)


def test_a_local_day_in_a_fixed_offset_zone() -> None:
    # Istanbul is UTC+3 all year.
    assert day_bounds(date(2026, 3, 10), ISTANBUL) == (utc(2026, 3, 9, 21), utc(2026, 3, 10, 21))
    assert day_bounds(date(2026, 7, 10), ISTANBUL) == (utc(2026, 7, 9, 21), utc(2026, 7, 10, 21))


def test_day_bounds_are_utc_instants() -> None:
    start, end = day_bounds(date(2026, 3, 10), ISTANBUL)
    assert start.tzinfo is UTC and end.tzinfo is UTC


def test_a_dst_day_is_23_or_25_hours_long() -> None:
    spring = day_bounds(date(2026, 3, 29), LISBON)  # clocks forward at 01:00 UTC
    fall = day_bounds(date(2026, 10, 25), LISBON)  # clocks back at 01:00 UTC
    normal = day_bounds(date(2026, 4, 15), LISBON)
    assert spring == (utc(2026, 3, 29, 0), utc(2026, 3, 29, 23))
    assert fall == (utc(2026, 10, 24, 23), utc(2026, 10, 26, 0))
    assert spring[1] - spring[0] == timedelta(hours=23)
    assert fall[1] - fall[0] == timedelta(hours=25)
    assert normal[1] - normal[0] == timedelta(hours=24)


def test_consecutive_days_tile_the_timeline() -> None:
    day = date(2026, 10, 20)
    for _ in range(10):  # crosses the Lisbon fall-back
        start, end = day_bounds(day, LISBON)
        next_start, _ = day_bounds(day + timedelta(days=1), LISBON)
        assert end == next_start
        day += timedelta(days=1)


def test_local_date_of_uses_the_workspace_timezone() -> None:
    instant = utc(2026, 3, 9, 21, 30)  # 00:30 on 10 March in Istanbul
    assert local_date_of(instant, ISTANBUL) == date(2026, 3, 10)
    assert local_date_of(instant, LISBON) == date(2026, 3, 9)


def test_today_ends_now() -> None:
    now = utc(2026, 3, 10, 12, 30)  # 15:30 in Istanbul
    assert period_bounds("today", now, ISTANBUL) == (utc(2026, 3, 9, 21), now)


def test_yesterday_is_the_previous_local_day() -> None:
    now = utc(2026, 3, 10, 12, 30)
    assert period_bounds("yesterday", now, ISTANBUL) == (utc(2026, 3, 8, 21), utc(2026, 3, 9, 21))


def test_last_seven_days_starts_six_local_midnights_back() -> None:
    now = utc(2026, 3, 10, 12, 30)
    assert period_bounds("last_7_days", now, ISTANBUL) == (utc(2026, 3, 3, 21), now)


def test_today_follows_the_local_date_not_the_utc_date() -> None:
    now = utc(2026, 3, 9, 22, 0)  # already the 10th in Istanbul, still the 9th in UTC
    start, end = period_bounds("today", now, ISTANBUL)
    assert start == utc(2026, 3, 9, 21)
    assert end == now


def test_periods_across_a_dst_change_use_local_midnights() -> None:
    now = utc(2026, 3, 30, 10, 0)  # 11:00 in Lisbon, the day after the change
    assert period_bounds("yesterday", now, LISBON) == (utc(2026, 3, 29, 0), utc(2026, 3, 29, 23))
    start, _ = period_bounds("last_7_days", now, LISBON)
    assert start == utc(2026, 3, 24, 0)  # 24 March 00:00 WET


@pytest.mark.parametrize("period", ["today", "yesterday", "last_7_days"])
def test_period_bounds_keep_the_timezone_of_now(period: str) -> None:
    start, end = period_bounds(period, utc(2026, 3, 10, 12), ISTANBUL)
    assert start.tzinfo is UTC and end.tzinfo is UTC
