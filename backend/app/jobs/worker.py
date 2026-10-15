"""Job execution and the worker loop (background-jobs.md §3).

``execute_job`` runs one claimed job and records the outcome. ``Worker`` runs
``WORKER_CONCURRENCY`` claim loops plus a scheduler loop. All state is in PostgreSQL, so a
restarted worker simply claims whatever is due (INV-07).
"""

import contextlib
import os
import re
import signal
import socket
import threading
import time
import uuid
from datetime import timedelta
from typing import Literal

from pydantic import ValidationError
from sqlalchemy.orm import Session, sessionmaker

from app.core.clock import Clock
from app.core.errors import AppError, RetryableError
from app.core.logging import bind_context, get_logger, unbind_context
from app.jobs import queue
from app.jobs.queue import ClaimedJob
from app.jobs.registry import JobContext, JobLeaseLost, RegisteredHandler, get_handler
from app.jobs.scheduler import scheduler_tick

Outcome = Literal["succeeded", "retry", "dead", "lease_lost"]

SHUTDOWN_GRACE_SECONDS = 30.0
DETAIL_MAX_CHARS = 500
_SENSITIVE_DETAIL = re.compile(
    r"(token|secret|password|passwd|authorization|api[_-]?key|cookie)(\s*[=:]\s*)\S+", re.I
)
_log = get_logger("app.jobs")


def sanitize_detail(detail: str | None) -> str | None:
    """Truncate and redact error text before it is stored in ``jobs.last_error_detail``."""
    if not detail:
        return None
    return _SENSITIVE_DETAIL.sub(r"\1\2[REDACTED]", detail)[:DETAIL_MAX_CHARS]


def _validation_summary(exc: ValidationError) -> str:
    # Field names and error types only: pydantic's messages can echo input values.
    return "; ".join(f"{'.'.join(str(p) for p in e['loc'])}: {e['type']}" for e in exc.errors())


def _dead(
    session_factory: sessionmaker[Session],
    clock: Clock,
    job: ClaimedJob,
    handler: RegisteredHandler | None,
    ctx: JobContext | None,
    code: str,
    detail: str | None,
) -> Outcome:
    if not queue.mark_dead(session_factory, job, clock.now(), code, sanitize_detail(detail)):
        _log.warning("job_lease_lost", outcome="dead")
        return "lease_lost"
    _log.error("job_dead", error_code=code, attempts=job.attempts)
    if handler is not None and handler.on_dead is not None and ctx is not None:
        try:
            handler.on_dead(ctx, code)
        except Exception:
            _log.exception("on_dead_failed")  # the job stays dead; the hook failure is visible
    return "dead"


def execute_job(
    session_factory: sessionmaker[Session],
    clock: Clock,
    job: ClaimedJob,
    *,
    lease_seconds: float,
) -> Outcome:
    """Run a claimed job to an outcome: succeeded, requeued for retry, or dead."""
    bind_context(
        job_id=str(job.id),
        job_type=job.job_type,
        workspace_id=str(job.workspace_id) if job.workspace_id else None,
        correlation_id=str(job.correlation_id) if job.correlation_id else None,
    )
    try:
        return _execute(session_factory, clock, job, lease_seconds)
    finally:
        unbind_context("job_id", "job_type", "workspace_id", "correlation_id")


def _execute(
    session_factory: sessionmaker[Session],
    clock: Clock,
    job: ClaimedJob,
    lease_seconds: float,
) -> Outcome:
    handler = get_handler(job.job_type)
    if handler is None:
        return _dead(
            session_factory,
            clock,
            job,
            None,
            None,
            "JOB_PAYLOAD_INVALID",
            f"no handler registered for job type {job.job_type!r}",
        )
    if job.attempts > job.max_attempts:
        # Reclaimed after lease expiry more often than allowed: the handler keeps crashing.
        return _dead(
            session_factory,
            clock,
            job,
            handler,
            None,
            "INTERNAL_ERROR",
            "lease expired on every attempt (worker crashed or hung)",
        )
    try:
        payload = handler.payload_model.model_validate(job.payload)
    except ValidationError as exc:
        return _dead(
            session_factory,
            clock,
            job,
            handler,
            None,
            "JOB_PAYLOAD_INVALID",
            _validation_summary(exc),
        )

    effective_lease = max(lease_seconds, handler.timeout_seconds or 0)
    if effective_lease > lease_seconds:
        queue.extend_lease(session_factory, job, clock, effective_lease)

    def heartbeat() -> None:
        if not queue.extend_lease(session_factory, job, clock, effective_lease):
            raise JobLeaseLost

    ctx = JobContext(
        job_id=job.id,
        job_type=job.job_type,
        workspace_id=job.workspace_id,
        correlation_id=job.correlation_id,
        payload=payload,
        attempt=job.attempts,
        max_attempts=job.max_attempts,
        session_factory=session_factory,
        clock=clock,
        _heartbeat=heartbeat,
    )

    try:
        handler.func(ctx)
    except JobLeaseLost:
        _log.warning("job_lease_lost", outcome="handler_aborted")
        return "lease_lost"
    except RetryableError as exc:
        if job.attempts >= job.max_attempts:
            return _dead(session_factory, clock, job, handler, ctx, exc.code, exc.detail)
        delay = exc.retry_after_seconds or queue.backoff_seconds(
            job.attempts, handler.backoff_seconds
        )
        run_at = clock.now() + timedelta(seconds=delay)
        if not queue.mark_retry(
            session_factory, job, run_at, exc.code, sanitize_detail(exc.detail)
        ):
            return "lease_lost"
        _log.warning(
            "job_retry",
            error_code=exc.code,
            attempts=job.attempts,
            retry_in_seconds=round(delay, 1),
        )
        return "retry"
    except AppError as exc:  # a permanent, expected failure
        return _dead(session_factory, clock, job, handler, ctx, exc.code, str(exc.params) or None)
    except Exception as exc:
        _log.exception("job_failed")
        return _dead(
            session_factory,
            clock,
            job,
            handler,
            ctx,
            "INTERNAL_ERROR",
            f"{type(exc).__name__}: {exc}",
        )

    if not queue.mark_succeeded(session_factory, job, clock.now()):
        _log.warning("job_lease_lost", outcome="succeeded")
        return "lease_lost"
    _log.info("job_succeeded", attempts=job.attempts)
    return "succeeded"


class Worker:
    """``concurrency`` claim loops and one scheduler loop, all backed by PostgreSQL."""

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        clock: Clock,
        *,
        concurrency: int = 2,
        poll_interval: float = 1.0,
        lease_seconds: float = 120.0,
        scheduler_interval: float = 60.0,
        worker_id: str | None = None,
    ) -> None:
        self.session_factory = session_factory
        self.clock = clock
        self.concurrency = concurrency
        self.poll_interval = poll_interval
        self.lease_seconds = lease_seconds
        self.scheduler_interval = scheduler_interval
        self.worker_id = worker_id or f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:8]}"
        self._stop = threading.Event()
        self._threads: list[threading.Thread] = []

    # --- single steps (used by the loops and by tests) ---------------------------------

    def run_once(self, slot: int = 0) -> bool:
        """Claim and run at most one job. True if a job was run."""
        job = queue.claim_one(
            self.session_factory, self.clock, f"{self.worker_id}/{slot}", self.lease_seconds
        )
        if job is None:
            return False
        execute_job(self.session_factory, self.clock, job, lease_seconds=self.lease_seconds)
        return True

    # --- loops ------------------------------------------------------------------------

    def _claim_loop(self, slot: int) -> None:
        while not self._stop.is_set():
            try:
                if self.run_once(slot):
                    continue  # more work may be waiting: do not sleep
            except Exception:
                _log.exception("worker_loop_error")  # e.g. database briefly unavailable
            self._stop.wait(self.poll_interval)

    def _scheduler_loop(self) -> None:
        while not self._stop.is_set():
            try:
                scheduler_tick(self.session_factory, self.clock)
            except Exception:
                _log.exception("scheduler_error")
            self._stop.wait(self.scheduler_interval)

    # --- lifecycle --------------------------------------------------------------------

    def start(self) -> None:
        if self._threads:
            raise RuntimeError("worker already started")
        self._stop.clear()
        threads = [
            threading.Thread(target=self._claim_loop, args=(slot,), name=f"job-{slot}")
            for slot in range(self.concurrency)
        ]
        threads.append(threading.Thread(target=self._scheduler_loop, name="scheduler"))
        for thread in threads:
            thread.start()
        self._threads = threads
        _log.info("worker_started", worker_id=self.worker_id, concurrency=self.concurrency)

    def stop(self, grace_seconds: float = SHUTDOWN_GRACE_SECONDS) -> None:
        """Stop claiming; let running jobs finish for up to ``grace_seconds``.

        Jobs still running afterwards are recovered through lease expiry.
        """
        self._stop.set()
        deadline = time.monotonic() + grace_seconds  # one shared deadline, not one per thread
        for thread in self._threads:
            thread.join(timeout=max(deadline - time.monotonic(), 0))
        still_running = [t.name for t in self._threads if t.is_alive()]
        if still_running:
            _log.warning("worker_shutdown_timeout", threads=still_running)
        self._threads = []
        _log.info("worker_stopped", worker_id=self.worker_id)

    def run_forever(self) -> None:
        """Start and block until SIGINT/SIGTERM, then shut down gracefully."""
        self.start()

        def request_stop(signum: int, _frame: object) -> None:
            _log.info("shutdown_requested", signal=signum)
            self._stop.set()

        for sig in (signal.SIGINT, signal.SIGTERM):
            # Fails when not on the main thread or unsupported on this OS: then only stop() works.
            with contextlib.suppress(ValueError, OSError):
                signal.signal(sig, request_stop)
        # A timed wait keeps Ctrl+C responsive on Windows.
        while not self._stop.wait(0.5):
            pass
        self.stop()
