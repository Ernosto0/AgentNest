"""Queue primitives: enqueue, claim, finalise (background-jobs.md §2-3, ADR-006).

All state lives in the ``jobs`` table. ``enqueue`` runs inside the caller's transaction (a
transactional outbox) and never commits. ``claim_one`` and the ``mark_*`` functions own their
short transactions. Time always comes from the injected ``Clock``.
"""

import random
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from pydantic import BaseModel
from sqlalchemy import and_, or_, select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session, sessionmaker

from app.core.clock import Clock, SystemClock
from app.jobs.models import Job
from app.jobs.registry import get_handler

# Default retry schedule: attempt 1 failed -> 10 s, then 60 s, 5 min, 15 min, 1 h (then 1 h).
DEFAULT_BACKOFF_SECONDS: tuple[float, ...] = (10, 60, 300, 900, 3600)
JITTER = 0.2  # +/- 20 %

# Payloads carry IDs only (data-model.md §3.2): never secrets or message text.
_FORBIDDEN_PAYLOAD_KEYS = frozenset(
    {"text", "message", "message_text", "body", "caption", "token", "password", "secret"}
)

_DEDUP_PREDICATE = text("status IN ('queued', 'running')")


def backoff_seconds(
    attempt: int,
    schedule: Sequence[float] | None = None,
    rng: random.Random | None = None,
) -> float:
    """Delay before retrying after ``attempt`` (1-based) failed, with +/- 20 % jitter."""
    steps = schedule or DEFAULT_BACKOFF_SECONDS
    base = steps[min(max(attempt, 1), len(steps)) - 1]
    factor = 1 + (rng or random).uniform(-JITTER, JITTER)  # noqa: S311  (not security related)
    return base * factor


def _check_payload_keys(value: Any, path: str = "payload") -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            if str(key).lower() in _FORBIDDEN_PAYLOAD_KEYS:
                raise ValueError(f"job {path} must not contain {key!r} (IDs only)")
            _check_payload_keys(item, f"{path}.{key}")
    elif isinstance(value, list | tuple):
        for item in value:
            _check_payload_keys(item, path)


def enqueue(
    session: Session,
    job_type: str,
    payload: BaseModel,
    *,
    workspace_id: uuid.UUID | None,
    correlation_id: uuid.UUID | None,
    run_at: datetime | None = None,
    dedup_key: str | None = None,
    priority: int = 100,
    max_attempts: int | None = None,
    clock: Clock | None = None,
) -> uuid.UUID:
    """Insert a job in the caller's transaction and return its id.

    With ``dedup_key``: if a queued or running job already has that key, no row is created and
    the existing job's id is returned (its ``run_at`` is *not* extended, so a stream of
    triggers cannot postpone the work forever).
    """
    handler = get_handler(job_type)
    if handler is None:
        raise ValueError(f"unknown job type: {job_type}")
    if not isinstance(payload, handler.payload_model):
        raise TypeError(f"{job_type} expects {handler.payload_model.__name__}")
    data = payload.model_dump(mode="json")
    _check_payload_keys(data)

    job_id = uuid.uuid4()
    values = {
        "id": job_id,
        "workspace_id": workspace_id,
        "job_type": job_type,
        "payload": data,
        "status": "queued",
        "priority": priority,
        "run_at": run_at or (clock or SystemClock()).now(),
        "attempts": 0,
        "max_attempts": max_attempts or handler.max_attempts,
        "dedup_key": dedup_key,
        "correlation_id": correlation_id,
    }
    if dedup_key is None:
        session.execute(pg_insert(Job).values(**values))
        return job_id

    for _ in range(3):  # the winner may finish between our insert and our lookup
        inserted = session.execute(
            pg_insert(Job)
            .values(**values)
            .on_conflict_do_nothing(index_elements=[Job.dedup_key], index_where=_DEDUP_PREDICATE)
            .returning(Job.id)
        ).scalar_one_or_none()
        if inserted is not None:
            return inserted
        existing = session.execute(
            select(Job.id).where(Job.dedup_key == dedup_key, Job.status.in_(("queued", "running")))
        ).scalar_one_or_none()
        if existing is not None:
            return existing
    raise RuntimeError(f"could not enqueue or find job for dedup_key={dedup_key!r}")


@dataclass(frozen=True)
class ClaimedJob:
    id: uuid.UUID
    job_type: str
    payload: dict[str, Any]
    workspace_id: uuid.UUID | None
    correlation_id: uuid.UUID | None
    attempts: int  # already incremented by the claim
    max_attempts: int
    locked_by: str


def claim_one(
    session_factory: sessionmaker[Session],
    clock: Clock,
    worker_id: str,
    lease_seconds: float,
) -> ClaimedJob | None:
    """Claim the next due job in one short transaction (``FOR UPDATE SKIP LOCKED``).

    Due means queued with ``run_at <= now``, or running with an expired lease (the worker that
    held it crashed). Exactly one concurrent caller can claim a given job.
    """
    now = clock.now()
    due = (
        select(Job.id)
        .where(
            or_(
                and_(Job.status == "queued", Job.run_at <= now),
                and_(Job.status == "running", Job.lease_expires_at < now),
            )
        )
        .order_by(Job.priority, Job.run_at)
        .limit(1)
        .with_for_update(skip_locked=True)
        .scalar_subquery()
    )
    stmt = (
        update(Job)
        .where(Job.id == due)
        .values(
            status="running",
            attempts=Job.attempts + 1,
            locked_by=worker_id,
            lease_expires_at=now + timedelta(seconds=lease_seconds),
        )
        .returning(
            Job.id,
            Job.job_type,
            Job.payload,
            Job.workspace_id,
            Job.correlation_id,
            Job.attempts,
            Job.max_attempts,
        )
        .execution_options(synchronize_session=False)
    )
    with session_factory() as session:
        row = session.execute(stmt).one_or_none()
        session.commit()
    if row is None:
        return None
    return ClaimedJob(
        id=row.id,
        job_type=row.job_type,
        payload=row.payload,
        workspace_id=row.workspace_id,
        correlation_id=row.correlation_id,
        attempts=row.attempts,
        max_attempts=row.max_attempts,
        locked_by=worker_id,
    )


def _finalise(session_factory: sessionmaker[Session], job: ClaimedJob, **values: Any) -> bool:
    """Conditional update: only the current holder of this execution may finalise the job.

    Returns False when the lease was lost (another worker claimed the job meanwhile); the
    caller must then leave the outcome to that other execution.
    """
    stmt = (
        update(Job)
        .where(
            Job.id == job.id,
            Job.status == "running",
            Job.locked_by == job.locked_by,
            Job.attempts == job.attempts,
        )
        .values(locked_by=None, lease_expires_at=None, **values)
        .execution_options(synchronize_session=False)
    )
    with session_factory() as session:
        result = session.execute(stmt)
        session.commit()
    return result.rowcount == 1  # type: ignore[attr-defined, no-any-return]


def mark_succeeded(session_factory: sessionmaker[Session], job: ClaimedJob, now: datetime) -> bool:
    return _finalise(session_factory, job, status="succeeded", finished_at=now)


def mark_retry(
    session_factory: sessionmaker[Session],
    job: ClaimedJob,
    run_at: datetime,
    error_code: str,
    error_detail: str | None,
) -> bool:
    return _finalise(
        session_factory,
        job,
        status="queued",
        run_at=run_at,
        last_error_code=error_code,
        last_error_detail=error_detail,
    )


def mark_rescheduled(
    session_factory: sessionmaker[Session], job: ClaimedJob, run_at: datetime
) -> bool:
    """Re-queue the same row at ``run_at`` and give the claimed attempt back."""
    return _finalise(
        session_factory,
        job,
        status="queued",
        run_at=run_at,
        attempts=max(job.attempts - 1, 0),
    )


def expedite(session: Session, dedup_key: str, clock: Clock) -> bool:
    """Make a *queued* job with this dedup key due now. True if one was moved.

    A running job is left alone (it is already being done), and so is a job that is already
    due. Runs in the caller's transaction and never commits.
    """
    now = clock.now()
    result = session.execute(
        update(Job)
        .where(Job.dedup_key == dedup_key, Job.status == "queued", Job.run_at > now)
        .values(run_at=now)
        .execution_options(synchronize_session=False)
    )
    return result.rowcount == 1  # type: ignore[attr-defined, no-any-return]


def mark_dead(
    session_factory: sessionmaker[Session],
    job: ClaimedJob,
    now: datetime,
    error_code: str,
    error_detail: str | None,
) -> bool:
    return _finalise(
        session_factory,
        job,
        status="dead",
        finished_at=now,
        last_error_code=error_code,
        last_error_detail=error_detail,
    )


def extend_lease(
    session_factory: sessionmaker[Session],
    job: ClaimedJob,
    clock: Clock,
    lease_seconds: float,
) -> bool:
    """Push the lease out (heartbeat). False if this execution no longer holds the job."""
    stmt = (
        update(Job)
        .where(
            Job.id == job.id,
            Job.status == "running",
            Job.locked_by == job.locked_by,
            Job.attempts == job.attempts,
        )
        .values(lease_expires_at=clock.now() + timedelta(seconds=lease_seconds))
        .execution_options(synchronize_session=False)
    )
    with session_factory() as session:
        result = session.execute(stmt)
        session.commit()
    return result.rowcount == 1  # type: ignore[attr-defined, no-any-return]


def get_job(session: Session, job_id: uuid.UUID) -> Job | None:
    return session.get(Job, job_id)
