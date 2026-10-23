"""The scheduled daily report: one job per workspace and local day, at the workspace's own hour
(workflows.md section F, background-jobs.md section 4)."""

from datetime import UTC, date, datetime

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.clock import FrozenClock
from app.identity.models import Workspace
from app.jobs.models import Job
from app.jobs.scheduler import periodic_snapshot, register_periodic, scheduler_tick
from app.jobs.testing import run_due_jobs
from app.notifications.models import Notification
from app.reporting import jobs as report_jobs
from app.reporting.models import DailyReport
from tests.factories import add_member, create_user, create_workspace


def _workspace(
    session: Session,
    *,
    timezone: str = "Europe/Istanbul",
    hour: int | None = None,
    status: str = "active",
) -> Workspace:
    workspace = create_workspace(session, timezone=timezone)
    workspace.status = status
    workspace.settings = {} if hour is None else {"daily_report_hour": hour}
    for role in ("owner", "manager", "staff"):
        add_member(session, workspace, create_user(session), role)
    session.commit()
    return workspace


def _jobs(session: Session, workspace: Workspace | None = None) -> list[Job]:
    statement = select(Job).where(Job.job_type == "generate_daily_report")
    if workspace is not None:
        statement = statement.where(Job.workspace_id == workspace.id)
    return list(session.scalars(statement))


def _tick(session: Session, at: datetime) -> int:
    """One scheduler tick of the report function at ``at`` (UTC)."""
    count = report_jobs.enqueue_daily_reports(session, FrozenClock(at))
    session.commit()
    return count


def utc(*parts: int) -> datetime:
    return datetime(*parts, tzinfo=UTC)


def test_nothing_is_enqueued_before_the_workspace_hour(db_session: Session) -> None:
    workspace = _workspace(db_session)  # default hour 20, Istanbul (UTC+3)
    assert _tick(db_session, utc(2026, 3, 10, 16, 59)) == 0  # 19:59 local
    assert _jobs(db_session) == []
    assert _tick(db_session, utc(2026, 3, 10, 17, 0)) == 1  # 20:00 local
    [job] = _jobs(db_session)
    assert job.workspace_id == workspace.id
    assert job.dedup_key == f"daily_report:{workspace.id}:2026-03-10"
    assert job.payload == {"workspace_id": str(workspace.id), "local_date": "2026-03-10"}
    assert job.max_attempts == 3


def test_exactly_one_job_per_workspace_per_local_day(
    db_session: Session, shared_session_factory: sessionmaker[Session]
) -> None:
    workspace = _workspace(db_session)
    assert _tick(db_session, utc(2026, 3, 10, 17, 0)) == 1
    assert _tick(db_session, utc(2026, 3, 10, 17, 1)) == 0  # queued: the dedup key holds

    clock = FrozenClock(utc(2026, 3, 10, 17, 2))
    assert run_due_jobs(clock, session_factory=shared_session_factory) == 1
    db_session.expire_all()
    assert [j.status for j in _jobs(db_session)] == ["succeeded"]

    # The job is done; the next minutes of the evening must not enqueue it again.
    for minute in (3, 4, 30):
        assert _tick(db_session, utc(2026, 3, 10, 17, minute)) == 0
    assert _tick(db_session, utc(2026, 3, 10, 20, 59)) == 0  # 23:59 local
    assert len(_jobs(db_session, workspace)) == 1

    assert _tick(db_session, utc(2026, 3, 10, 21, 0)) == 0  # 00:00 local of the next day
    assert _tick(db_session, utc(2026, 3, 11, 17, 0)) == 1  # 20:00 of the next local day
    assert [j.payload["local_date"] for j in _jobs(db_session, workspace)] == [
        "2026-03-10",
        "2026-03-11",
    ]


def test_a_dead_job_is_not_replaced_every_minute(db_session: Session) -> None:
    workspace = _workspace(db_session)
    _tick(db_session, utc(2026, 3, 10, 17, 0))
    [job] = _jobs(db_session)
    job.status = "dead"
    db_session.commit()
    assert _tick(db_session, utc(2026, 3, 10, 17, 5)) == 0
    assert len(_jobs(db_session, workspace)) == 1


def test_each_workspace_follows_its_own_clock_and_hour(db_session: Session) -> None:
    istanbul = _workspace(db_session, timezone="Europe/Istanbul")
    lisbon = _workspace(db_session, timezone="Europe/Lisbon")
    early = _workspace(db_session, timezone="Europe/Istanbul", hour=9)
    # 2026-01-15, 19:30 UTC: Lisbon is on UTC (19:30), Istanbul on UTC+3 (22:30).
    assert _tick(db_session, utc(2026, 1, 15, 19, 30)) == 2
    assert {j.workspace_id for j in _jobs(db_session)} == {istanbul.id, early.id}
    assert _tick(db_session, utc(2026, 1, 15, 20, 0)) == 1  # 20:00 in Lisbon
    assert {j.workspace_id for j in _jobs(db_session)} == {istanbul.id, early.id, lisbon.id}


def test_lisbon_summer_time_moves_the_hour_by_one_utc_hour(db_session: Session) -> None:
    """2026-03-29 is the day Lisbon moves to UTC+1: 20:00 local is 19:00 UTC from then on."""
    lisbon = _workspace(db_session, timezone="Europe/Lisbon")
    assert _tick(db_session, utc(2026, 3, 29, 18, 59)) == 0  # 19:59 local (UTC+1)
    assert _tick(db_session, utc(2026, 3, 29, 19, 0)) == 1  # 20:00 local
    [job] = _jobs(db_session, lisbon)
    assert job.payload["local_date"] == "2026-03-29"


def test_lisbon_the_day_before_the_change_is_still_utc(db_session: Session) -> None:
    lisbon = _workspace(db_session, timezone="Europe/Lisbon")
    assert _tick(db_session, utc(2026, 3, 28, 19, 59)) == 0  # 19:59 local (UTC)
    assert _tick(db_session, utc(2026, 3, 28, 20, 0)) == 1
    [job] = _jobs(db_session, lisbon)
    assert job.payload["local_date"] == "2026-03-28"


def test_a_workspace_that_is_not_active_gets_no_report(db_session: Session) -> None:
    _workspace(db_session, status="deleting")
    assert _tick(db_session, utc(2026, 3, 10, 18, 0)) == 0
    assert _jobs(db_session) == []


def test_an_invalid_hour_falls_back_to_twenty(db_session: Session) -> None:
    assert report_jobs.report_hour({"daily_report_hour": 99}) == 20
    assert report_jobs.report_hour({"daily_report_hour": "8"}) == 20
    assert report_jobs.report_hour({"daily_report_hour": True}) == 20
    assert report_jobs.report_hour({}) == 20
    assert report_jobs.report_hour(None) == 20
    assert report_jobs.report_hour({"daily_report_hour": 0}) == 0


def test_the_job_stores_the_report_and_announces_it_once(
    db_session: Session, shared_session_factory: sessionmaker[Session]
) -> None:
    workspace = _workspace(db_session)
    _tick(db_session, utc(2026, 3, 10, 17, 0))
    clock = FrozenClock(utc(2026, 3, 10, 17, 1))
    assert run_due_jobs(clock, session_factory=shared_session_factory) == 1

    db_session.expire_all()
    report = db_session.scalars(select(DailyReport)).one()
    assert report.workspace_id == workspace.id and report.local_date == date(2026, 3, 10)
    assert report.period_end == clock.now()  # 20:01 local: the day so far
    notices = db_session.scalars(
        select(Notification).where(Notification.type == "report.daily_ready")
    ).all()
    assert len(notices) == 2  # owner and manager
    # Re-running captures another immutable generation, without another unread announcement.
    [job] = _jobs(db_session)
    job.status, job.finished_at = "queued", None
    db_session.commit()
    assert (
        run_due_jobs(FrozenClock(utc(2026, 3, 10, 17, 5)), session_factory=shared_session_factory)
        == 1
    )
    db_session.expire_all()
    assert db_session.scalar(select(func.count()).select_from(DailyReport)) == 2
    assert (
        db_session.scalar(
            select(func.count())
            .select_from(Notification)
            .where(Notification.type == "report.daily_ready")
        )
        == 2
    )


def test_the_job_ignores_a_workspace_that_disappeared(
    db_session: Session, shared_session_factory: sessionmaker[Session]
) -> None:
    workspace = _workspace(db_session)
    _tick(db_session, utc(2026, 3, 10, 17, 0))
    workspace.status = "deleting"
    db_session.commit()
    run_due_jobs(FrozenClock(utc(2026, 3, 10, 17, 1)), session_factory=shared_session_factory)
    assert db_session.scalar(select(func.count()).select_from(DailyReport)) == 0
    assert [j.status for j in _jobs(db_session)] == ["succeeded"]


@pytest.mark.commits
def test_the_scheduler_tick_runs_the_report_function_and_survives_a_restart(
    session_factory: sessionmaker[Session],
) -> None:
    """INV-07: the schedule is in the database. A second tick (a restarted worker) adds nothing."""
    with session_factory() as session:
        _workspace(session)
    clock = FrozenClock(utc(2026, 3, 10, 17, 0))
    with periodic_snapshot(clear=True):
        register_periodic(report_jobs.enqueue_daily_reports)
        assert scheduler_tick(session_factory, clock) == 1
        assert scheduler_tick(session_factory, clock) == 0  # "restart": a new tick, same day
    with session_factory() as session:
        assert len(_jobs(session)) == 1
    assert run_due_jobs(clock, session_factory=session_factory) == 1
    with session_factory() as session:
        assert session.scalar(select(func.count()).select_from(DailyReport)) == 1
