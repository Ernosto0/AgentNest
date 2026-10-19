"""Scheduler tick (background-jobs.md §4).

Every ``scheduler_interval`` seconds one worker process enqueues the periodic jobs. A
PostgreSQL advisory lock guarantees that only one process does so per tick. Periodic jobs
use deterministic ``dedup_key``s (e.g. ``expire_approvals:2026-10-15T16:04``), so even a
repeated tick cannot create duplicates. No periodic jobs are registered in Phase 1.
"""

from collections.abc import Callable, Iterator
from contextlib import contextmanager

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.clock import Clock
from app.core.logging import get_logger

# Arbitrary constant identifying "the AgentNest scheduler" among advisory locks.
SCHEDULER_LOCK_KEY = 7_201_410_001

# A periodic function enqueues jobs through the given session/clock and returns how many it
# attempted to enqueue. It must not commit.
PeriodicFn = Callable[[Session, Clock], int]

_PERIODIC: list[PeriodicFn] = []
_log = get_logger("app.jobs.scheduler")


def register_periodic(func_: PeriodicFn) -> PeriodicFn:
    _PERIODIC.append(func_)
    return func_


@contextmanager
def periodic_snapshot(*, clear: bool = False) -> Iterator[None]:
    """Restore the periodic registry on exit (tests). ``clear`` starts from an empty registry,
    so a test sees only the periodic functions it registers itself."""
    saved = list(_PERIODIC)
    if clear:
        _PERIODIC.clear()
    try:
        yield
    finally:
        _PERIODIC[:] = saved


def scheduler_tick(session_factory: sessionmaker[Session], clock: Clock) -> int | None:
    """Run the periodic functions if this process wins the advisory lock.

    Returns the number of jobs the periodic functions tried to enqueue, or ``None`` when
    another process holds the lock (nothing was done).
    """
    with session_factory() as session:
        # Transaction-scoped lock: released automatically by the commit below.
        if not session.scalar(select(func.pg_try_advisory_xact_lock(SCHEDULER_LOCK_KEY))):
            return None
        total = 0
        for periodic in list(_PERIODIC):
            try:
                with session.begin_nested():  # one failing periodic must not block the others
                    total += periodic(session, clock)
            except Exception:
                _log.exception("periodic_failed", periodic=getattr(periodic, "__name__", "?"))
        session.commit()
        return total
