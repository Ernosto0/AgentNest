"""AC-X5 / INV-07: queued and scheduled jobs survive a worker restart."""

import threading
import time
from collections.abc import Callable
from datetime import timedelta

import pytest

from app.core.clock import FrozenClock, SystemClock
from app.jobs.registry import JobContext
from app.jobs.worker import Worker
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
