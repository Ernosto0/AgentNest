"""Abandoned agent runs are marked failed after 10 minutes (agent-runtime.md §2)."""

import uuid
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.ai.jobs import (
    ABANDONED_AFTER,
    SweepAgentRunsPayload,
    enqueue_agent_run_sweep,
    sweep_agent_runs,
)
from app.ai.models import AgentRun
from app.core.clock import FrozenClock
from app.jobs.models import Job
from app.jobs.registry import JobContext
from tests.factories import create_workspace


def _run(session: Session, workspace_id: uuid.UUID, clock: FrozenClock, age: timedelta) -> AgentRun:
    run = AgentRun(
        workspace_id=workspace_id,
        task="interpret_command",
        status="running",
        started_at=clock.now() - age,
        created_at=clock.now() - age,
    )
    session.add(run)
    session.commit()
    return run


def _context(factory: sessionmaker[Session], clock: FrozenClock) -> JobContext:
    return JobContext(
        job_id=uuid.uuid4(),
        job_type="sweep_agent_runs",
        workspace_id=None,
        correlation_id=None,
        payload=SweepAgentRunsPayload(),
        attempt=1,
        max_attempts=1,
        session_factory=factory,
        clock=clock,
        _heartbeat=lambda: None,
    )


def test_only_old_running_runs_are_marked_abandoned(
    db_session: Session, shared_session_factory: sessionmaker[Session], clock: FrozenClock
) -> None:
    workspace = create_workspace(db_session)
    old = _run(db_session, workspace.id, clock, ABANDONED_AFTER + timedelta(seconds=1))
    fresh = _run(db_session, workspace.id, clock, ABANDONED_AFTER - timedelta(minutes=1))

    sweep_agent_runs(_context(shared_session_factory, clock))
    db_session.expire_all()

    assert (old.status, old.error_code, old.completed_at) == ("failed", "ABANDONED", clock.now())
    assert (fresh.status, fresh.error_code) == ("running", None)


def test_the_periodic_function_enqueues_one_job_per_minute(
    db_session: Session, clock: FrozenClock
) -> None:
    enqueue_agent_run_sweep(db_session, clock)
    enqueue_agent_run_sweep(db_session, clock)  # a repeated tick in the same minute
    jobs = db_session.scalars(select(Job).where(Job.job_type == "sweep_agent_runs")).all()
    assert len(jobs) == 1
