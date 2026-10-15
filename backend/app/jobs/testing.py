"""Test and dev hooks: run due jobs synchronously with a controllable clock.

Combine with ``FrozenClock.advance(...)`` to simulate time passing (scheduled publishing,
expiry, backoff, debounce) without sleeping (background-jobs.md §8).
"""

from sqlalchemy.orm import Session, sessionmaker

from app.core.clock import Clock
from app.core.config import get_settings
from app.core.db import get_session_factory
from app.jobs import queue
from app.jobs.worker import execute_job

RUN_DUE_WORKER_ID = "run-due-jobs"


def run_due_jobs(
    clock: Clock,
    limit: int = 100,
    *,
    session_factory: sessionmaker[Session] | None = None,
    lease_seconds: float | None = None,
) -> int:
    """Claim and run due jobs in the calling thread until none are due (or ``limit`` is hit).

    Jobs enqueued by the jobs it runs, and retries that become due at the clock's current
    time, are picked up in the same call. Returns the number of executions.
    """
    factory = session_factory or get_session_factory()
    lease = lease_seconds if lease_seconds is not None else get_settings().job_lease_seconds
    executed = 0
    while executed < limit:
        job = queue.claim_one(factory, clock, RUN_DUE_WORKER_ID, lease)
        if job is None:
            break
        execute_job(factory, clock, job, lease_seconds=lease)
        executed += 1
    return executed
