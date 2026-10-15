"""Scheduler tick: advisory lock, deterministic dedup keys (background-jobs.md §4)."""

import threading
import uuid

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.clock import Clock, FrozenClock
from app.jobs import enqueue
from app.jobs.models import Job
from app.jobs.scheduler import register_periodic, scheduler_tick
from tests.integration.jobs.conftest import EchoPayload, SessionFactory

pytestmark = pytest.mark.commits


def job_count(factory: SessionFactory) -> int:
    with factory() as session:
        return session.scalar(select(func.count()).select_from(Job)) or 0


def test_with_no_periodic_jobs_registered_a_tick_does_nothing(
    session_factory: SessionFactory, clock: FrozenClock
) -> None:
    assert scheduler_tick(session_factory, clock) == 0
    assert job_count(session_factory) == 0


def test_periodic_jobs_use_dedup_keys_so_repeated_ticks_do_not_duplicate(
    session_factory: SessionFactory, clock: FrozenClock, register_echo: object
) -> None:
    register_echo()  # type: ignore[operator]

    @register_periodic
    def every_minute(session: Session, tick_clock: Clock) -> int:
        bucket = tick_clock.now().strftime("%Y-%m-%dT%H:%M")
        enqueue(
            session,
            "test.echo",
            EchoPayload(item_id=uuid.uuid4()),
            workspace_id=None,
            correlation_id=None,
            dedup_key=f"test_periodic:{bucket}",
            clock=tick_clock,
        )
        return 1

    scheduler_tick(session_factory, clock)
    scheduler_tick(session_factory, clock)  # a second process, or a retried tick
    assert job_count(session_factory) == 1
    clock.advance(minutes=1)
    scheduler_tick(session_factory, clock)
    assert job_count(session_factory) == 2


def test_only_one_process_wins_the_advisory_lock(
    session_factory: SessionFactory, clock: FrozenClock
) -> None:
    inside, release = threading.Event(), threading.Event()
    runs: list[str] = []

    @register_periodic
    def slow(session: Session, tick_clock: Clock) -> int:
        runs.append("ran")
        inside.set()
        release.wait(timeout=5)
        return 0

    results: list[int | None] = []
    first = threading.Thread(target=lambda: results.append(scheduler_tick(session_factory, clock)))
    first.start()
    assert inside.wait(timeout=5)

    contender = scheduler_tick(session_factory, clock)  # the first tick still holds the lock
    release.set()
    first.join(timeout=5)

    assert contender is None
    assert results == [0]
    assert runs == ["ran"]  # the periodic function ran exactly once
    assert scheduler_tick(session_factory, clock) == 0  # the lock was released with the commit


def test_a_failing_periodic_function_does_not_block_the_others(
    session_factory: SessionFactory, clock: FrozenClock, register_echo: object
) -> None:
    register_echo()  # type: ignore[operator]

    @register_periodic
    def broken(session: Session, tick_clock: Clock) -> int:
        enqueue(
            session,
            "test.echo",
            EchoPayload(item_id=uuid.uuid4()),
            workspace_id=None,
            correlation_id=None,
            clock=tick_clock,
        )
        raise RuntimeError("periodic failed after enqueueing")

    @register_periodic
    def healthy(session: Session, tick_clock: Clock) -> int:
        enqueue(
            session,
            "test.echo",
            EchoPayload(item_id=uuid.uuid4()),
            workspace_id=None,
            correlation_id=None,
            clock=tick_clock,
        )
        return 1

    assert scheduler_tick(session_factory, clock) == 1
    assert job_count(session_factory) == 1  # the broken one was rolled back to its savepoint
