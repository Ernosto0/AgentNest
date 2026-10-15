"""Concurrent claims and lease recovery (INV-06, INV-07; RK-07)."""

import threading
import uuid
from collections.abc import Callable
from datetime import timedelta

import pytest

from app.core.clock import FrozenClock
from app.jobs import queue, run_due_jobs
from app.jobs.registry import JobContext
from app.jobs.worker import execute_job
from tests.integration.jobs.conftest import SessionFactory, enqueue_committed, load_job

pytestmark = pytest.mark.commits

LEASE = 120.0


def race_two_claims(
    session_factory: SessionFactory, clock: FrozenClock
) -> list[queue.ClaimedJob | None]:
    """Two threads call ``claim_one`` at the same instant; returns what each of them got."""
    barrier = threading.Barrier(2)
    claimed: list[queue.ClaimedJob | None] = []

    def attempt(name: str) -> None:
        barrier.wait()
        claimed.append(queue.claim_one(session_factory, clock, name, LEASE))

    threads = [threading.Thread(target=attempt, args=(f"w{i}",)) for i in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return claimed


def test_two_threads_claiming_one_job_yield_exactly_one_winner(
    session_factory: SessionFactory, clock: FrozenClock, register_echo: Callable[..., None]
) -> None:
    register_echo()
    for round_number in range(25):  # repeat: a race that passes once proves little
        job_id = enqueue_committed(session_factory, clock)
        winners = [c for c in race_two_claims(session_factory, clock) if c is not None]
        assert len(winners) == 1, f"round {round_number}: {len(winners)} workers claimed the job"
        assert winners[0].id == job_id
        assert winners[0].attempts == 1
        # Finish it so the next round starts clean.
        assert queue.mark_succeeded(session_factory, winners[0], clock.now())


def test_many_threads_never_claim_the_same_job_twice(
    session_factory: SessionFactory, clock: FrozenClock, register_echo: Callable[..., None]
) -> None:
    register_echo()
    expected = {enqueue_committed(session_factory, clock) for _ in range(40)}
    claimed: list[uuid.UUID] = []
    lock = threading.Lock()

    def drain(name: str) -> None:
        while (job := queue.claim_one(session_factory, clock, name, LEASE)) is not None:
            with lock:
                claimed.append(job.id)

    threads = [threading.Thread(target=drain, args=(f"w{i}",)) for i in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(claimed) == len(set(claimed)) == 40
    assert set(claimed) == expected


def test_concurrent_run_due_jobs_execute_each_handler_once(
    session_factory: SessionFactory,
    clock: FrozenClock,
    register_echo: Callable[..., None],
    calls: list[JobContext],
) -> None:
    register_echo()
    for _ in range(30):
        enqueue_committed(session_factory, clock)
    threads = [
        threading.Thread(
            target=run_due_jobs, args=(clock,), kwargs={"session_factory": session_factory}
        )
        for _ in range(4)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(calls) == 30
    assert len({c.job_id for c in calls}) == 30


# --- leases --------------------------------------------------------------------------------


def test_a_running_job_with_a_live_lease_cannot_be_claimed(
    session_factory: SessionFactory, clock: FrozenClock, register_echo: Callable[..., None]
) -> None:
    register_echo()
    job_id = enqueue_committed(session_factory, clock)
    first = queue.claim_one(session_factory, clock, "crashed-worker", LEASE)
    assert first is not None and first.id == job_id

    clock.advance(seconds=119)
    assert queue.claim_one(session_factory, clock, "other", LEASE) is None
    job = load_job(session_factory, job_id)
    assert (job.status, job.locked_by) == ("running", "crashed-worker")


def test_expired_lease_is_reclaimed_and_the_job_completes(
    session_factory: SessionFactory,
    clock: FrozenClock,
    register_echo: Callable[..., None],
    calls: list[JobContext],
) -> None:
    """A worker claims a job and dies. After the lease expires another worker finishes it."""
    register_echo()
    job_id = enqueue_committed(session_factory, clock)
    assert queue.claim_one(session_factory, clock, "dies-here", LEASE) is not None
    # ... the process is killed: no handler ran, nothing was finalised.

    clock.advance(seconds=121)
    assert run_due_jobs(clock, session_factory=session_factory) == 1

    job = load_job(session_factory, job_id)
    assert (job.status, job.attempts) == ("succeeded", 2)
    assert [c.attempt for c in calls] == [2]


def test_a_late_finish_from_the_original_worker_cannot_overwrite_the_new_owner(
    session_factory: SessionFactory, clock: FrozenClock, register_echo: Callable[..., None]
) -> None:
    """Stale executions are fenced out by the conditional update (locked_by + attempts)."""
    register_echo()
    job_id = enqueue_committed(session_factory, clock)
    stale = queue.claim_one(session_factory, clock, "slow-worker", LEASE)
    assert stale is not None
    clock.advance(seconds=121)
    current = queue.claim_one(session_factory, clock, "fast-worker", LEASE)
    assert current is not None and current.attempts == 2

    assert queue.mark_succeeded(session_factory, stale, clock.now()) is False
    assert queue.mark_dead(session_factory, stale, clock.now(), "INTERNAL_ERROR", "late") is False
    assert queue.mark_retry(session_factory, stale, clock.now(), "X", None) is False
    job = load_job(session_factory, job_id)
    assert (job.status, job.locked_by, job.attempts) == ("running", "fast-worker", 2)

    assert queue.mark_succeeded(session_factory, current, clock.now()) is True
    assert load_job(session_factory, job_id).status == "succeeded"


def test_a_job_that_keeps_crashing_ends_dead_instead_of_looping_forever(
    session_factory: SessionFactory,
    clock: FrozenClock,
    register_echo: Callable[..., None],
    calls: list[JobContext],
) -> None:
    dead: list[str] = []
    register_echo(on_dead=lambda ctx, code: dead.append(code), max_attempts=2)
    job_id = enqueue_committed(session_factory, clock)
    for _ in range(2):  # two crashes: claimed, never finalised
        assert queue.claim_one(session_factory, clock, "crasher", LEASE) is not None
        clock.advance(seconds=121)

    third = queue.claim_one(session_factory, clock, "survivor", LEASE)
    assert third is not None and third.attempts == 3  # beyond max_attempts=2
    execute_job(session_factory, clock, third, lease_seconds=LEASE)

    job = load_job(session_factory, job_id)
    assert (job.status, job.last_error_code) == ("dead", "INTERNAL_ERROR")
    assert calls == []  # the handler is not run a third time
    assert run_due_jobs(clock, session_factory=session_factory) == 0


def test_heartbeat_extends_the_lease(
    session_factory: SessionFactory, clock: FrozenClock, register_echo: Callable[..., None]
) -> None:
    observed: list[object] = []

    def long_running(ctx: JobContext) -> None:
        clock.advance(seconds=100)
        ctx.heartbeat()
        with ctx.session_factory() as session:
            from app.jobs.models import Job

            job = session.get(Job, ctx.job_id)
            assert job is not None
            observed.append(job.lease_expires_at)

    register_echo(long_running)
    enqueue_committed(session_factory, clock)
    start = clock.now()
    run_due_jobs(clock, session_factory=session_factory, lease_seconds=LEASE)
    assert observed == [start + timedelta(seconds=100 + 120)]


def test_heartbeat_after_the_lease_was_lost_aborts_the_handler_without_finalising(
    session_factory: SessionFactory, clock: FrozenClock, register_echo: Callable[..., None]
) -> None:
    stolen: list[queue.ClaimedJob | None] = []
    finished_normally: list[bool] = []

    def hangs_then_resumes(ctx: JobContext) -> None:
        clock.advance(seconds=200)  # far beyond the lease: this worker is presumed dead
        stolen.append(queue.claim_one(session_factory, clock, "rescuer", LEASE))
        ctx.heartbeat()  # must raise JobLeaseLost
        finished_normally.append(True)

    register_echo(hangs_then_resumes)
    job_id = enqueue_committed(session_factory, clock)
    run_due_jobs(clock, limit=1, session_factory=session_factory, lease_seconds=LEASE)

    assert finished_normally == []
    assert stolen[0] is not None
    job = load_job(session_factory, job_id)
    # The rescuer owns the job; the aborted execution did not mark it dead/succeeded/queued.
    assert (job.status, job.locked_by, job.attempts) == ("running", "rescuer", 2)


def test_handler_timeout_sets_a_longer_initial_lease(
    session_factory: SessionFactory, clock: FrozenClock, register_echo: Callable[..., None]
) -> None:
    leases: list[object] = []

    def record_lease(ctx: JobContext) -> None:
        leases.append(load_job(session_factory, ctx.job_id).lease_expires_at)

    register_echo(record_lease, timeout=900)
    enqueue_committed(session_factory, clock)
    start = clock.now()
    run_due_jobs(clock, session_factory=session_factory, lease_seconds=LEASE)
    assert leases == [start + timedelta(seconds=900)]
