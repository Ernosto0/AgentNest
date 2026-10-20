"""AC-X5 / INV-07: queued and scheduled jobs survive a worker restart."""

import threading
import time
from collections.abc import Callable
from datetime import date, timedelta
from pathlib import Path

import pytest
from sqlalchemy import func, select

from app.content.models import ContentItem
from app.content.service import ScheduleRequest
from app.core.clock import FrozenClock, SystemClock
from app.core.config import Settings
from app.integrations.instagram.models import SimContainer, SimPublishedMedia
from app.jobs import queue
from app.jobs.registry import JobContext
from app.jobs.worker import Worker
from app.operations.models import Operation
from tests.helpers.publishing import committing_publishing
from tests.integration.jobs.conftest import SessionFactory, enqueue_committed, load_job

pytestmark = [pytest.mark.commits, pytest.mark.invariant("INV-07")]


def make_worker(
    factory: SessionFactory, clock: FrozenClock | SystemClock, **kwargs: float
) -> Worker:
    return Worker(factory, clock, concurrency=2, poll_interval=0.02, lease_seconds=120, **kwargs)


def test_a_new_worker_instance_picks_up_queued_and_scheduled_jobs(
    session_factory: SessionFactory,
    clock: FrozenClock,
    register_echo: Callable[..., None],
    calls: list[JobContext],
) -> None:
    register_echo()
    queued = enqueue_committed(session_factory, clock)
    scheduled = enqueue_committed(
        session_factory, clock, run_at=clock.now() + timedelta(minutes=10)
    )

    first = make_worker(session_factory, clock)
    del first  # "stop the worker": it never ran anything, and holds no state we depend on

    second = make_worker(session_factory, clock)  # "restart": a brand-new instance
    assert second.run_once() is True
    assert load_job(session_factory, queued).status == "succeeded"
    assert second.run_once() is False  # the scheduled job is not due yet
    assert load_job(session_factory, scheduled).status == "queued"

    clock.advance(minutes=10)
    assert second.run_once() is True
    assert load_job(session_factory, scheduled).status == "succeeded"
    assert len(calls) == 2


def test_a_job_interrupted_by_a_worker_stop_is_recovered_by_the_next_instance(
    session_factory: SessionFactory,
    clock: FrozenClock,
    register_echo: Callable[..., None],
    calls: list[JobContext],
) -> None:
    register_echo()
    job_id = enqueue_committed(session_factory, clock)
    from app.jobs import queue

    # Worker one claims the job, then is stopped before it can finish.
    assert queue.claim_one(session_factory, clock, "worker-one/0", 120) is not None

    second = make_worker(session_factory, clock)
    assert second.run_once() is False  # lease still valid: do not steal
    clock.advance(seconds=121)
    assert second.run_once() is True
    job = load_job(session_factory, job_id)
    assert (job.status, job.attempts) == ("succeeded", 2)


def test_threaded_worker_runs_jobs_and_a_restarted_one_continues(
    session_factory: SessionFactory, register_echo: Callable[..., None], calls: list[JobContext]
) -> None:
    """End-to-end with real threads and the real clock: start, stop, start again."""
    register_echo()
    clock = SystemClock()
    ids = [enqueue_committed(session_factory, clock) for _ in range(5)]  # type: ignore[arg-type]

    one = make_worker(session_factory, clock)
    one.start()
    _wait_until(lambda: all(load_job(session_factory, i).status == "succeeded" for i in ids))
    one.stop(grace_seconds=5)

    later = enqueue_committed(session_factory, clock, run_at=clock.now() + timedelta(seconds=0.3))  # type: ignore[arg-type]
    two = make_worker(session_factory, clock)  # restart
    two.start()
    _wait_until(lambda: load_job(session_factory, later).status == "succeeded")
    two.stop(grace_seconds=5)
    assert len(calls) == 6


def test_graceful_shutdown_lets_the_running_job_finish_and_claims_nothing_new(
    session_factory: SessionFactory, register_echo: Callable[..., None], calls: list[JobContext]
) -> None:
    clock = SystemClock()
    started, release = threading.Event(), threading.Event()

    def slow(ctx: JobContext) -> None:
        started.set()
        release.wait(timeout=5)

    register_echo(slow)
    running = enqueue_committed(session_factory, clock)  # type: ignore[arg-type]
    worker = make_worker(session_factory, clock)
    worker.start()
    assert started.wait(timeout=5)

    waiting = enqueue_committed(session_factory, clock)  # type: ignore[arg-type]
    stopper = threading.Thread(target=worker.stop, kwargs={"grace_seconds": 5})
    stopper.start()
    time.sleep(0.2)  # stop() is now waiting for the in-flight job
    assert stopper.is_alive()
    release.set()
    stopper.join(timeout=5)

    assert not stopper.is_alive()
    assert load_job(session_factory, running).status == "succeeded"  # finished, not abandoned
    assert load_job(session_factory, waiting).status in {"queued", "succeeded"}
    assert len([c for c in calls if c.job_id == waiting]) <= 1


def _wait_until(condition: Callable[[], bool], timeout: float = 10.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return
        time.sleep(0.05)
    raise AssertionError("condition not met within timeout")


# --- AC-X5, publish case: a scheduled post survives a worker restart ---------------------------


def _count(factory: SessionFactory, model: type) -> int:
    with factory() as session:
        return session.scalar(select(func.count()).select_from(model)) or 0


def _item_status(factory: SessionFactory, item_id: object) -> str:
    with factory() as session:
        item = session.get(ContentItem, item_id)
        assert item is not None
        return item.status


def test_ac_x5_a_scheduled_publish_survives_a_worker_restart(
    session_factory: SessionFactory,
    clock: FrozenClock,
    settings: Settings,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scheduled at 19:00 Istanbul (16:00Z); the worker that was running when the owner
    scheduled it is gone, and a brand-new instance publishes the post exactly once."""
    pub = committing_publishing(session_factory, clock, settings, tmp_path / "media")
    monkeypatch.setattr("app.operations.jobs.get_settings", lambda: pub.settings)
    item = pub.schedule(
        pub.draft(), ScheduleRequest(local_date=date(2026, 1, 15), local_time="19:00")
    )
    assert item.scheduled_at == pub.at(16)
    (job,) = pub.jobs("publish_content")
    assert (job.status, job.run_at) == ("queued", pub.at(16))  # the schedule is a row, not memory
    item_id = item.id
    pub.session.close()  # no open transaction may outlive the setup (the teardown truncates)

    first = make_worker(session_factory, clock)
    del first  # the worker of the "old process": it never held the schedule in memory

    second = make_worker(session_factory, clock)  # "restart": a brand-new instance
    assert second.run_once() is False  # not due yet: nothing is published early
    assert _count(session_factory, SimPublishedMedia) == 0
    assert _item_status(session_factory, item_id) == "scheduled"

    clock.advance(hours=4)  # 12:00Z -> 16:00Z
    assert second.run_once() is True
    assert _item_status(session_factory, item_id) == "published"
    assert _count(session_factory, SimPublishedMedia) == 1
    assert second.run_once() is False  # and nothing is left to do twice
    assert _count(session_factory, SimPublishedMedia) == 1


def test_a_publish_job_whose_worker_died_after_claiming_it_is_published_once_by_the_next(
    session_factory: SessionFactory,
    clock: FrozenClock,
    settings: Settings,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The lease of a crashed worker expires; the next instance reclaims the job and publishes
    (the executor re-checks the domain state, INV-07, INV-06)."""
    pub = committing_publishing(session_factory, clock, settings, tmp_path / "media")
    monkeypatch.setattr("app.operations.jobs.get_settings", lambda: pub.settings)
    item = pub.scheduled()  # "publish now": due at once
    item_id = item.id
    pub.session.close()

    # Worker one claims the publish job and dies before running anything.
    assert queue.claim_one(session_factory, clock, "worker-one/0", 120) is not None
    second = make_worker(session_factory, clock)
    assert second.run_once() is False  # the lease is still valid: do not steal it
    assert _count(session_factory, SimPublishedMedia) == 0

    clock.advance(seconds=121)
    assert second.run_once() is True
    assert _item_status(session_factory, item_id) == "published"
    assert _count(session_factory, SimPublishedMedia) == 1
    assert _count(session_factory, SimContainer) == 1
    with session_factory() as session:
        operations = session.scalars(select(Operation)).all()
    assert [(o.operation_type, o.status) for o in operations] == [("publish_content", "succeeded")]
