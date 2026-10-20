"""Schedule rules (plan.md G13, G17): zones, DST gaps and folds, the window and the quota."""

from datetime import UTC, date, datetime, timedelta

import pytest

from app.content import scheduling as s

NOW = datetime(2026, 1, 15, 12, 0, tzinfo=UTC)


def local(
    local_date: date, local_time: str, tz: str = "Europe/Istanbul", **kwargs: object
) -> s.ResolvedSchedule:
    return s.resolve(
        now=kwargs.pop("now", NOW),  # type: ignore[arg-type]
        timezone=tz,
        local_date=local_date,
        local_time=local_time,
        needs_approval=bool(kwargs.pop("needs_approval", False)),
    )


def code_of(**kwargs: object) -> str:
    with pytest.raises(s.ScheduleError) as raised:
        local(**kwargs)  # type: ignore[arg-type]
    return raised.value.code


# --- zones ------------------------------------------------------------------------------------


def test_19_00_in_istanbul_is_16_00_utc() -> None:
    resolved = local(date(2026, 1, 15), "19:00")
    assert resolved.scheduled_at == datetime(2026, 1, 15, 16, 0, tzinfo=UTC)
    assert resolved.input == {
        "mode": "local",
        "local_date": "2026-01-15",
        "local_time": "19:00",
        "timezone": "Europe/Istanbul",
    }


def test_istanbul_has_no_gap_or_fold_since_2016() -> None:
    # The nights on which Europe/Lisbon changes are ordinary nights in Istanbul (UTC+3).
    spring = local(date(2027, 3, 28), "01:30", now=datetime(2027, 3, 1, tzinfo=UTC))
    autumn = local(date(2026, 10, 25), "01:30", now=datetime(2026, 10, 1, tzinfo=UTC))
    assert spring.scheduled_at == datetime(2027, 3, 27, 22, 30, tzinfo=UTC)
    assert autumn.scheduled_at == datetime(2026, 10, 24, 22, 30, tzinfo=UTC)
    assert "ambiguous" not in spring.input and "ambiguous" not in autumn.input


def test_lisbon_summer_and_winter_offsets() -> None:
    summer = local(date(2026, 7, 1), "19:00", "Europe/Lisbon", now=datetime(2026, 6, 1, tzinfo=UTC))
    winter = local(date(2026, 1, 20), "19:00", "Europe/Lisbon")
    assert summer.scheduled_at == datetime(2026, 7, 1, 18, 0, tzinfo=UTC)  # WEST, UTC+1
    assert winter.scheduled_at == datetime(2026, 1, 20, 19, 0, tzinfo=UTC)  # WET, UTC+0


def test_a_time_in_the_spring_forward_gap_does_not_exist() -> None:
    # Lisbon, 2027-03-28: 01:00 -> 02:00, so 01:30 never happens.
    now = datetime(2027, 3, 1, tzinfo=UTC)
    with pytest.raises(s.ScheduleError) as raised:
        local(date(2027, 3, 28), "01:30", "Europe/Lisbon", now=now)
    assert raised.value.code == s.SCHEDULE_TIME_NONEXISTENT
    assert raised.value.params["local_time"] == "01:30"
    # The minutes on either side of the gap are fine.
    before = local(date(2027, 3, 28), "00:59", "Europe/Lisbon", now=now)
    after = local(date(2027, 3, 28), "02:00", "Europe/Lisbon", now=now)
    assert before.scheduled_at == datetime(2027, 3, 28, 0, 59, tzinfo=UTC)
    assert after.scheduled_at == datetime(2027, 3, 28, 1, 0, tzinfo=UTC)


def test_a_time_in_the_fall_back_fold_is_the_earlier_instant_and_is_flagged() -> None:
    # Lisbon, 2026-10-25: 02:00 WEST -> 01:00 WET, so 01:30 happens twice (00:30Z and 01:30Z).
    resolved = local(
        date(2026, 10, 25), "01:30", "Europe/Lisbon", now=datetime(2026, 10, 1, tzinfo=UTC)
    )
    assert resolved.scheduled_at == datetime(2026, 10, 25, 0, 30, tzinfo=UTC)
    assert resolved.input["ambiguous"] is True
    # Next to the fold nothing is ambiguous.
    clear = local(
        date(2026, 10, 25), "02:30", "Europe/Lisbon", now=datetime(2026, 10, 1, tzinfo=UTC)
    )
    assert clear.scheduled_at == datetime(2026, 10, 25, 2, 30, tzinfo=UTC)
    assert "ambiguous" not in clear.input


# --- the window -------------------------------------------------------------------------------


def test_the_window_is_one_minute_back_and_sixty_days_ahead() -> None:
    assert code_of(local_date=date(2026, 1, 15), local_time="14:58") == s.SCHEDULE_IN_PAST  # 11:58Z
    assert local(date(2026, 1, 15), "15:00").scheduled_at == NOW  # exactly now is fine
    far = NOW + timedelta(days=60)  # 2026-03-16 12:00Z = 15:00 in Istanbul
    assert local(far.date(), "15:00").scheduled_at == far
    assert code_of(local_date=far.date(), local_time="15:01") == s.SCHEDULE_TOO_FAR


def test_one_minute_in_the_past_is_still_accepted_for_a_slow_form() -> None:
    assert s.resolve(
        now=NOW, timezone="UTC", local_date=NOW.date(), local_time="11:59", needs_approval=False
    ).scheduled_at == NOW - timedelta(minutes=1)


def test_publish_now_is_the_current_instant() -> None:
    resolved = s.resolve(
        now=NOW, timezone="Europe/Istanbul", publish_now=True, needs_approval=False
    )
    assert resolved.scheduled_at == NOW and resolved.input == {"mode": "now"}


def test_waiting_for_approval_needs_15_minutes_of_lead() -> None:
    kwargs = {"needs_approval": True}
    assert (
        code_of(local_date=date(2026, 1, 15), local_time="15:14", **kwargs)
        == s.SCHEDULE_TOO_SOON_FOR_APPROVAL
    )
    assert local(date(2026, 1, 15), "15:15", needs_approval=True).scheduled_at == (
        NOW + timedelta(minutes=15)
    )
    with pytest.raises(s.ScheduleError) as raised:
        s.resolve(now=NOW, timezone="UTC", publish_now=True, needs_approval=True)
    assert raised.value.code == s.SCHEDULE_TOO_SOON_FOR_APPROVAL
    assert raised.value.params == {"minutes": 15}


def test_the_past_beats_the_lead_rule() -> None:
    assert (
        code_of(local_date=date(2026, 1, 14), local_time="10:00", needs_approval=True)
        == s.SCHEDULE_IN_PAST
    )


# --- quota forecast ---------------------------------------------------------------------------


def hours(*values: float) -> list[datetime]:
    return [NOW + timedelta(hours=h) for h in values]


def test_the_quota_forecast_counts_the_busiest_24_hour_window_around_the_instant() -> None:
    existing = hours(*range(0, 5))  # 5 posts in the first 5 hours
    assert not s.quota_forecast_exceeded(existing, NOW + timedelta(hours=5), limit=6)
    assert s.quota_forecast_exceeded(existing, NOW + timedelta(hours=5), limit=5)


def test_a_post_leaves_the_window_exactly_24_hours_after_it_goes_out() -> None:
    existing = hours(0, 1)
    # At +24h the first post has left the window [+1h, +25h).
    assert not s.quota_forecast_exceeded(existing, NOW + timedelta(hours=24), limit=2)
    # At +23h59 all three are inside one window.
    assert s.quota_forecast_exceeded(existing, NOW + timedelta(hours=23, minutes=59), limit=2)


def test_posts_after_the_instant_count_too() -> None:
    later = hours(10, 11)
    assert s.quota_forecast_exceeded(later, NOW, limit=2)  # a window of 3: now, +10h, +11h
    assert not s.quota_forecast_exceeded(later, NOW, limit=3)


def test_posts_far_away_do_not_count() -> None:
    assert not s.quota_forecast_exceeded(hours(-100, -60, 100, 200), NOW, limit=1)


def test_an_empty_account_is_never_over_a_limit_of_one() -> None:
    assert not s.quota_forecast_exceeded([], NOW, limit=1)
