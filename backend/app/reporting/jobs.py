"""``generate_daily_report``: the scheduled daily report (workflows.md section F, ADR-006).

Every scheduler tick looks at the active workspaces. One whose **local** time has reached its
``daily_report_hour`` (default 20:00) gets exactly one job for that local day, keyed
``daily_report:{workspace}:{local_date}``. The dedup key only covers queued and running jobs, so
the tick also looks for any job with that key: a finished (or dead) job means the day is done and
the tick must not enqueue it again every minute.
"""

import uuid
from datetime import date
from zoneinfo import ZoneInfo

from pydantic import BaseModel
from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from app.core.clock import Clock
from app.core.context import ActorRef, WorkspaceContext
from app.identity.models import Workspace
from app.jobs.models import Job
from app.jobs.queue import enqueue
from app.jobs.registry import JobContext, job_handler
from app.jobs.scheduler import register_periodic
from app.reporting import service

DEFAULT_REPORT_HOUR = 20


class GenerateDailyReportPayload(BaseModel):
    workspace_id: uuid.UUID
    local_date: date


def dedup_key(workspace_id: uuid.UUID, local_date: date) -> str:
    return f"daily_report:{workspace_id}:{local_date.isoformat()}"


def report_hour(settings: dict[str, object] | None) -> int:
    """The workspace's ``daily_report_hour`` (0-23); a missing or invalid value means 20."""
    value = (settings or {}).get("daily_report_hour", DEFAULT_REPORT_HOUR)
    if isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= 23:
        return value
    return DEFAULT_REPORT_HOUR


@job_handler("generate_daily_report", GenerateDailyReportPayload, max_attempts=3)
def generate_daily_report(job: JobContext) -> None:
    payload = job.payload
    if not isinstance(payload, GenerateDailyReportPayload):
        return
    with job.session_factory() as session:
        workspace = session.get(Workspace, payload.workspace_id)
        if workspace is None or workspace.status != "active":
            return  # gone or suspended meanwhile: nothing to report
        ctx = WorkspaceContext(
            workspace.id,
            ActorRef.system("reporting.daily"),
            None,
            workspace.timezone,
            workspace.default_locale,
            workspace.is_demo,
        )
        service.generate_daily_report(session, job.clock, ctx, payload.local_date, scheduled=True)
        session.commit()


@register_periodic
def enqueue_daily_reports(session: Session, clock: Clock) -> int:
    now = clock.now()
    rows = session.execute(
        select(Workspace.id, Workspace.timezone, Workspace.settings).where(
            Workspace.status == "active"
        )
    ).all()
    enqueued = 0
    for workspace_id, timezone, settings in rows:
        local_now = now.astimezone(ZoneInfo(timezone))
        if local_now.hour < report_hour(settings):
            continue
        local_date = local_now.date()
        key = dedup_key(workspace_id, local_date)
        if session.scalar(select(exists().where(Job.dedup_key == key))):
            continue  # queued, running, done or dead: this day has had its job
        enqueue(
            session,
            "generate_daily_report",
            GenerateDailyReportPayload(workspace_id=workspace_id, local_date=local_date),
            workspace_id=workspace_id,
            correlation_id=None,
            dedup_key=key,
            clock=clock,
        )
        enqueued += 1
    return enqueued
