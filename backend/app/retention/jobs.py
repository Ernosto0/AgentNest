"""``retention_cleanup``: the daily cleanup job (background-jobs.md section 4, plan H17).

Every scheduler tick from 02:00 UTC on looks for the day's job. The dedup key only covers queued
and running jobs, so the tick checks for a job with the key in any status: a finished (or dead)
job means the day is done and it must not be enqueued again every minute.
"""

from pydantic import BaseModel
from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from app.audit import service as audit
from app.core.clock import Clock
from app.core.config import get_settings
from app.core.context import ActorRef
from app.jobs.models import Job
from app.jobs.queue import enqueue
from app.jobs.registry import JobContext, job_handler
from app.jobs.scheduler import register_periodic
from app.retention.cleanup import run_retention

RETENTION_HOUR_UTC = 2


class RetentionCleanupPayload(BaseModel):
    pass


def dedup_key(clock: Clock) -> str:
    return f"retention:{clock.now():%Y-%m-%d}"


@job_handler("retention_cleanup", RetentionCleanupPayload, max_attempts=1)
def retention_cleanup(job: JobContext) -> None:
    counts = run_retention(job.session_factory, get_settings(), job.clock.now())
    # The audit entry is written after the batches: it records what this run did. It is a
    # system-level row (no workspace) holding only counts.
    with job.session_factory() as session:
        audit.record(
            session,
            None,
            "retention.cleanup_ran",
            None,
            None,
            counts.as_dict(),
            clock=job.clock,
            actor=ActorRef.system("retention"),
        )
        session.commit()


@register_periodic
def enqueue_retention_cleanup(session: Session, clock: Clock) -> int:
    if clock.now().hour < RETENTION_HOUR_UTC:
        return 0
    key = dedup_key(clock)
    if session.scalar(select(exists().where(Job.dedup_key == key))):
        return 0  # queued, running, done or dead: today has had its job
    enqueue(
        session,
        "retention_cleanup",
        RetentionCleanupPayload(),
        workspace_id=None,
        correlation_id=None,
        dedup_key=key,
        clock=clock,
    )
    return 1
