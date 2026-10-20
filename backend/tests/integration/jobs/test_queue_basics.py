"""Enqueue, run, dedup, retry, dead-letter (background-jobs.md §2-3)."""

import uuid
from collections.abc import Callable
from datetime import timedelta

import pytest
from pydantic import BaseModel
from sqlalchemy import func, select, update

from app.core.clock import FrozenClock
from app.core.errors import AppError, RetryableError
from app.jobs import enqueue, queue, run_due_jobs
from app.jobs.models import Job
from app.jobs.registry import JobContext, RescheduleJob, job_handler
from tests.integration.jobs.conftest import (
    EchoPayload,
    SessionFactory,
    enqueue_committed,
    load_job,
)

pytestmark = pytest.mark.commits


def run(factory: SessionFactory, clock: FrozenClock) -> int:
    return run_due_jobs(clock, session_factory=factory)


# --- enqueue + run -------------------------------------------------------------------------


def test_enqueue_and_run_calls_the_handler_once_and_records_success(
    session_factory: SessionFactory,
    clock: FrozenClock,
    register_echo: Callable[..., None],
    calls: list[JobContext],
) -> None:
    register_echo()
    item_id = uuid.uuid4()
    job_id = enqueue_committed(session_factory, clock, payload=EchoPayload(item_id=item_id))

    assert run(session_factory, clock) == 1

    (ctx,) = calls
    assert ctx.job_id == job_id
    assert ctx.payload == EchoPayload(item_id=item_id)  # validated model, not a raw dict
    assert (ctx.attempt, ctx.max_attempts) == (1, 3)
    job = load_job(session_factory, job_id)
    assert job.status == "succeeded"
    assert job.attempts == 1
    assert job.finished_at == clock.now()
    assert (job.locked_by, job.lease_expires_at) == (None, None)
    assert run(session_factory, clock) == 0  # nothing runs twice


def test_handlers_get_a_session_factory_and_manage_their_own_transactions(
    session_factory: SessionFactory, clock: FrozenClock, register_echo: Callable[..., None]
) -> None:
    seen: list[int] = []

    def behaviour(ctx: JobContext) -> None:
        with ctx.session_factory() as session:
            seen.append(session.scalar(select(func.count()).select_from(Job)) or 0)

    register_echo(behaviour)
    enqueue_committed(session_factory, clock)
    run(session_factory, clock)
    assert seen == [1]


def test_enqueue_is_part_of_the_callers_transaction(
    session_factory: SessionFactory, clock: FrozenClock, register_echo: Callable[..., None]
) -> None:
    """Transactional outbox: if the state change rolls back, so does the job."""
    register_echo()
    with session_factory() as session:
        enqueue(
            session,
            "test.echo",
            EchoPayload(item_id=uuid.uuid4()),
            workspace_id=None,
            correlation_id=None,
            clock=clock,
        )
        session.rollback()
    assert run(session_factory, clock) == 0


def test_enqueue_rejects_unknown_types_wrong_payloads_and_non_id_payloads(
    session_factory: SessionFactory, clock: FrozenClock, register_echo: Callable[..., None]
) -> None:
    class WithText(BaseModel):
        text: str

    @job_handler("test.text", WithText)
    def _(ctx: JobContext) -> None:
        raise AssertionError("must never run")

    register_echo()
    with session_factory() as session:
        with pytest.raises(ValueError, match="unknown job type"):
            enqueue(
                session,
                "nope",
                EchoPayload(item_id=uuid.uuid4()),
                workspace_id=None,
                correlation_id=None,
            )
        with pytest.raises(TypeError):
            enqueue(
                session, "test.echo", WithText(text="hi"), workspace_id=None, correlation_id=None
            )
        with pytest.raises(ValueError, match="IDs only"):
            enqueue(
                session,
                "test.text",
                WithText(text="a customer message"),
                workspace_id=None,
                correlation_id=None,
            )


# --- dedup / debounce ----------------------------------------------------------------------


def test_dedup_returns_the_existing_job(
    session_factory: SessionFactory, clock: FrozenClock, register_echo: Callable[..., None]
) -> None:
    register_echo()
    first = enqueue_committed(session_factory, clock, dedup_key="draft:abc")
    second = enqueue_committed(session_factory, clock, dedup_key="draft:abc")
    assert first == second
    with session_factory() as session:
        assert session.scalar(select(func.count()).select_from(Job)) == 1
    assert run(session_factory, clock) == 1


def test_dedup_keeps_the_original_run_at_so_debounce_cannot_postpone_forever(
    session_factory: SessionFactory, clock: FrozenClock, register_echo: Callable[..., None]
) -> None:
    register_echo()
    start = clock.now()
    job_id = enqueue_committed(
        session_factory, clock, dedup_key="draft:abc", run_at=start + timedelta(seconds=8)
    )
    clock.advance(seconds=5)
    again = enqueue_committed(
        session_factory, clock, dedup_key="draft:abc", run_at=clock.now() + timedelta(seconds=8)
    )
    assert again == job_id
    assert load_job(session_factory, job_id).run_at == start + timedelta(seconds=8)


def test_a_finished_job_no_longer_blocks_its_dedup_key(
    session_factory: SessionFactory, clock: FrozenClock, register_echo: Callable[..., None]
) -> None:
    register_echo()
    first = enqueue_committed(session_factory, clock, dedup_key="k")
    run(session_factory, clock)
    second = enqueue_committed(session_factory, clock, dedup_key="k")
    assert second != first
    assert run(session_factory, clock) == 1


def test_jobs_without_a_dedup_key_are_independent(
    session_factory: SessionFactory, clock: FrozenClock, register_echo: Callable[..., None]
) -> None:
    register_echo()
    ids = {enqueue_committed(session_factory, clock) for _ in range(3)}
    assert len(ids) == 3
    assert run(session_factory, clock) == 3


# --- scheduling and ordering ---------------------------------------------------------------


def test_a_future_run_at_is_not_claimed_until_the_clock_advances(
    session_factory: SessionFactory, clock: FrozenClock, register_echo: Callable[..., None]
) -> None:
    register_echo()
    job_id = enqueue_committed(session_factory, clock, run_at=clock.now() + timedelta(hours=1))
    assert run(session_factory, clock) == 0
    clock.advance(minutes=59)
    assert run(session_factory, clock) == 0
    assert load_job(session_factory, job_id).status == "queued"
    clock.advance(minutes=1)
    assert run(session_factory, clock) == 1
    assert load_job(session_factory, job_id).status == "succeeded"


def test_lower_priority_number_runs_first_then_earlier_run_at(
    session_factory: SessionFactory, clock: FrozenClock, register_echo: Callable[..., None]
) -> None:
    order: list[uuid.UUID] = []
    register_echo(lambda ctx: order.append(ctx.job_id))
    start = clock.now()
    late_urgent = enqueue_committed(session_factory, clock, priority=10, run_at=start)
    early_normal = enqueue_committed(
        session_factory, clock, priority=100, run_at=start - timedelta(minutes=5)
    )
    later_normal = enqueue_committed(session_factory, clock, priority=100, run_at=start)
    run(session_factory, clock)
    assert order == [late_urgent, early_normal, later_normal]


def test_run_due_jobs_respects_its_limit(
    session_factory: SessionFactory, clock: FrozenClock, register_echo: Callable[..., None]
) -> None:
    register_echo()
    for _ in range(5):
        enqueue_committed(session_factory, clock)
    assert run_due_jobs(clock, limit=2, session_factory=session_factory) == 2
    assert run_due_jobs(clock, session_factory=session_factory) == 3


# --- retry, backoff, dead ------------------------------------------------------------------


def test_retryable_error_requeues_with_backoff_then_succeeds(
    session_factory: SessionFactory,
    clock: FrozenClock,
    register_echo: Callable[..., None],
    calls: list[JobContext],
) -> None:
    def flaky(ctx: JobContext) -> None:
        if ctx.attempt == 1:
            raise RetryableError("PROVIDER_UNAVAILABLE", "503 from provider")

    register_echo(flaky)
    job_id = enqueue_committed(session_factory, clock)

    assert run(session_factory, clock) == 1
    job = load_job(session_factory, job_id)
    assert (job.status, job.attempts) == ("queued", 1)
    assert job.last_error_code == "PROVIDER_UNAVAILABLE"
    delay = (job.run_at - clock.now()).total_seconds()
    assert 8 <= delay <= 12  # 10 s +/- 20 % jitter
    assert (job.locked_by, job.lease_expires_at) == (None, None)

    assert run(session_factory, clock) == 0  # not yet due
    clock.advance(seconds=13)
    assert run(session_factory, clock) == 1
    job = load_job(session_factory, job_id)
    assert (job.status, job.attempts) == ("succeeded", 2)
    assert [c.attempt for c in calls] == [1, 2]


def test_reschedule_requeues_the_same_row_and_gives_the_attempt_back(
    session_factory: SessionFactory,
    clock: FrozenClock,
    register_echo: Callable[..., None],
    calls: list[JobContext],
) -> None:
    def later(ctx: JobContext) -> None:
        if len(calls) == 1:
            raise RescheduleJob(clock.now() + timedelta(seconds=8))

    register_echo(later)
    job_id = enqueue_committed(session_factory, clock, dedup_key="draft:abc")

    assert run(session_factory, clock) == 1
    job = load_job(session_factory, job_id)
    assert (job.status, job.attempts) == ("queued", 0)  # not consumed
    assert job.run_at == clock.now() + timedelta(seconds=8)
    assert job.last_error_code is None  # not a failure
    assert (job.locked_by, job.lease_expires_at) == (None, None)
    # still the one row for its key: a new trigger does not create a second job
    assert enqueue_committed(session_factory, clock, dedup_key="draft:abc") == job_id

    assert run(session_factory, clock) == 0  # not yet due
    clock.advance(seconds=9)
    assert run(session_factory, clock) == 1
    job = load_job(session_factory, job_id)
    assert (job.id, job.status, job.attempts) == (job_id, "succeeded", 1)
    assert [c.attempt for c in calls] == [1, 1]


def test_rescheduling_never_exhausts_the_retry_budget(
    session_factory: SessionFactory, clock: FrozenClock, register_echo: Callable[..., None]
) -> None:
    def always_later(ctx: JobContext) -> None:
        raise RescheduleJob(clock.now() + timedelta(seconds=1))

    register_echo(always_later, max_attempts=2)
    job_id = enqueue_committed(session_factory, clock)
    for _ in range(5):
        assert run(session_factory, clock) == 1
        clock.advance(seconds=2)
    job = load_job(session_factory, job_id)
    assert (job.status, job.attempts) == ("queued", 0)


def test_expedite_makes_a_queued_job_due_now(
    session_factory: SessionFactory, clock: FrozenClock, register_echo: Callable[..., None]
) -> None:
    register_echo()
    job_id = enqueue_committed(
        session_factory, clock, dedup_key="send:1", run_at=clock.now() + timedelta(minutes=5)
    )
    assert run(session_factory, clock) == 0
    with session_factory() as session:
        assert queue.expedite(session, "send:1", clock) is True
        session.commit()
    assert load_job(session_factory, job_id).run_at == clock.now()
    assert run(session_factory, clock) == 1


def test_expedite_leaves_running_finished_due_and_unknown_jobs_alone(
    session_factory: SessionFactory, clock: FrozenClock, register_echo: Callable[..., None]
) -> None:
    register_echo()
    due = enqueue_committed(session_factory, clock, dedup_key="due")
    running = enqueue_committed(
        session_factory, clock, dedup_key="running", run_at=clock.now() + timedelta(minutes=5)
    )
    queued_run_at = load_job(session_factory, running).run_at
    with session_factory() as session:
        session.execute(update(Job).where(Job.id == running).values(status="running"))
        session.commit()
        assert queue.expedite(session, "running", clock) is False  # already being done
        assert queue.expedite(session, "due", clock) is False  # already due
        assert queue.expedite(session, "nope", clock) is False
        session.commit()
    assert load_job(session_factory, running).run_at == queued_run_at
    run(session_factory, clock)  # "due" runs and finishes
    assert load_job(session_factory, due).status == "succeeded"
    with session_factory() as session:
        assert queue.expedite(session, "due", clock) is False  # finished: no queued row


def test_cancel_queued_removes_a_waiting_job_and_frees_its_key(
    session_factory: SessionFactory, clock: FrozenClock, register_echo: Callable[..., None]
) -> None:
    register_echo()
    job_id = enqueue_committed(
        session_factory, clock, dedup_key="publish:1", run_at=clock.now() + timedelta(minutes=5)
    )
    with session_factory() as session:
        assert queue.cancel_queued(session, "publish:1", clock) is True
        assert queue.cancel_queued(session, "publish:1", clock) is False  # nothing left queued
        session.commit()
    job = load_job(session_factory, job_id)
    assert (job.status, job.finished_at) == ("cancelled", clock.now())
    clock.advance(minutes=10)
    assert run(session_factory, clock) == 0  # a cancelled job never runs
    # The dedup key is free again: the same work can be scheduled anew.
    again = enqueue_committed(session_factory, clock, dedup_key="publish:1")
    assert again != job_id


def test_cancel_queued_leaves_running_finished_and_unknown_jobs_alone(
    session_factory: SessionFactory, clock: FrozenClock, register_echo: Callable[..., None]
) -> None:
    register_echo()
    running = enqueue_committed(session_factory, clock, dedup_key="running")
    done = enqueue_committed(session_factory, clock, dedup_key="done")
    with session_factory() as session:
        session.execute(update(Job).where(Job.id == running).values(status="running"))
        session.execute(update(Job).where(Job.id == done).values(status="succeeded"))
        session.commit()
        assert queue.cancel_queued(session, "running") is False  # being done: it re-checks itself
        assert queue.cancel_queued(session, "done") is False
        assert queue.cancel_queued(session, "nope") is False
        session.commit()
    assert load_job(session_factory, running).status == "running"
    assert load_job(session_factory, done).status == "succeeded"


def test_retry_after_overrides_the_backoff_schedule(
    session_factory: SessionFactory, clock: FrozenClock, register_echo: Callable[..., None]
) -> None:
    def rate_limited(ctx: JobContext) -> None:
        raise RetryableError("PROVIDER_RATE_LIMITED", retry_after_seconds=90)

    register_echo(rate_limited)
    job_id = enqueue_committed(session_factory, clock)
    run(session_factory, clock)
    assert load_job(session_factory, job_id).run_at == clock.now() + timedelta(seconds=90)


def test_exhausted_retries_end_dead_and_call_on_dead_once(
    session_factory: SessionFactory, clock: FrozenClock, register_echo: Callable[..., None]
) -> None:
    dead_calls: list[tuple[uuid.UUID, str]] = []

    def always_fails(ctx: JobContext) -> None:
        raise RetryableError("PROVIDER_UNAVAILABLE", "still down")

    register_echo(
        always_fails,
        max_attempts=2,
        on_dead=lambda ctx, code: dead_calls.append((ctx.job_id, code)),
    )
    job_id = enqueue_committed(session_factory, clock)

    run(session_factory, clock)
    assert load_job(session_factory, job_id).status == "queued"
    assert dead_calls == []
    clock.advance(minutes=1)
    run(session_factory, clock)

    job = load_job(session_factory, job_id)
    assert (job.status, job.attempts) == ("dead", 2)
    assert job.last_error_code == "PROVIDER_UNAVAILABLE"
    assert job.finished_at == clock.now()
    assert dead_calls == [(job_id, "PROVIDER_UNAVAILABLE")]
    clock.advance(days=1)
    assert run(session_factory, clock) == 0  # dead jobs are never picked up again


def test_unexpected_exception_is_dead_immediately_with_redacted_truncated_detail(
    session_factory: SessionFactory, clock: FrozenClock, register_echo: Callable[..., None]
) -> None:
    dead_codes: list[str] = []

    def explodes(ctx: JobContext) -> None:
        raise RuntimeError("login failed password=hunter2 " + "x" * 2000)

    register_echo(explodes, on_dead=lambda ctx, code: dead_codes.append(code))
    job_id = enqueue_committed(session_factory, clock)
    run(session_factory, clock)

    job = load_job(session_factory, job_id)
    assert (job.status, job.attempts) == ("dead", 1)  # no retry for unexpected errors
    assert job.last_error_code == "INTERNAL_ERROR"
    assert job.last_error_detail is not None
    assert len(job.last_error_detail) <= 500
    assert "hunter2" not in job.last_error_detail
    assert "RuntimeError" in job.last_error_detail
    assert dead_codes == ["INTERNAL_ERROR"]


def test_app_error_is_a_permanent_failure_with_its_own_code(
    session_factory: SessionFactory, clock: FrozenClock, register_echo: Callable[..., None]
) -> None:
    def refuses(ctx: JobContext) -> None:
        raise AppError("CONFLICT_STATE")

    register_echo(refuses)
    job_id = enqueue_committed(session_factory, clock)
    run(session_factory, clock)
    job = load_job(session_factory, job_id)
    assert (job.status, job.last_error_code) == ("dead", "CONFLICT_STATE")


def test_a_failing_on_dead_hook_does_not_unmake_the_dead_state(
    session_factory: SessionFactory, clock: FrozenClock, register_echo: Callable[..., None]
) -> None:
    def explodes(ctx: JobContext) -> None:
        raise RuntimeError("boom")

    def bad_hook(ctx: JobContext, code: str) -> None:
        raise RuntimeError("hook boom")

    register_echo(explodes, on_dead=bad_hook)
    job_id = enqueue_committed(session_factory, clock)
    assert run(session_factory, clock) == 1
    assert load_job(session_factory, job_id).status == "dead"


def test_invalid_payload_is_dead_without_calling_the_handler_or_echoing_values(
    session_factory: SessionFactory,
    clock: FrozenClock,
    register_echo: Callable[..., None],
    calls: list[JobContext],
) -> None:
    register_echo()
    with session_factory() as session:
        job = Job(
            job_type="test.echo",
            payload={"item_id": "not-a-uuid-SENSITIVE"},
            run_at=clock.now(),
            max_attempts=3,
        )
        session.add(job)
        session.commit()
        job_id = job.id

    run(session_factory, clock)

    assert calls == []
    stored = load_job(session_factory, job_id)
    assert (stored.status, stored.last_error_code) == ("dead", "JOB_PAYLOAD_INVALID")
    assert stored.last_error_detail is not None
    assert "item_id" in stored.last_error_detail
    assert "SENSITIVE" not in stored.last_error_detail


def test_unknown_job_type_is_dead_not_silently_dropped_or_retried_forever(
    session_factory: SessionFactory, clock: FrozenClock
) -> None:
    with session_factory() as session:
        job = Job(job_type="ghost", payload={}, run_at=clock.now(), max_attempts=3)
        session.add(job)
        session.commit()
        job_id = job.id
    assert run(session_factory, clock) == 1
    assert load_job(session_factory, job_id).status == "dead"
    assert run(session_factory, clock) == 0
