"""AI-related periodic jobs. Imported by ``app.worker.load_handlers``.

``sweep_agent_runs``: a crash mid-call leaves ``agent_runs.status = running``. After
10 minutes the run is marked ``failed (ABANDONED)``; the job's lease expiry has already
re-run the task under a new run (agent-runtime.md §2).
"""

from datetime import timedelta

from pydantic import BaseModel
from sqlalchemy import update
from sqlalchemy.orm import Session

from app.ai.models import AgentRun
from app.core.clock import Clock
from app.jobs.queue import enqueue
from app.jobs.registry import JobContext, job_handler
from app.jobs.scheduler import register_periodic

ABANDONED_AFTER = timedelta(minutes=10)


class SweepAgentRunsPayload(BaseModel):
    pass


@job_handler("sweep_agent_runs", SweepAgentRunsPayload, max_attempts=1)
def sweep_agent_runs(ctx: JobContext) -> None:
    cutoff = ctx.clock.now() - ABANDONED_AFTER
    with ctx.session_factory() as session:
        session.execute(
            update(AgentRun)
            .where(AgentRun.status == "running", AgentRun.started_at < cutoff)
            .values(status="failed", error_code="ABANDONED", completed_at=ctx.clock.now())
            .execution_options(synchronize_session=False)
        )
        session.commit()


@register_periodic
def enqueue_agent_run_sweep(session: Session, clock: Clock) -> int:
    enqueue(
        session,
        "sweep_agent_runs",
        SweepAgentRunsPayload(),
        workspace_id=None,
        correlation_id=None,
        dedup_key=f"sweep_agent_runs:{clock.now():%Y-%m-%dT%H:%M}",
        clock=clock,
    )
    return 1
