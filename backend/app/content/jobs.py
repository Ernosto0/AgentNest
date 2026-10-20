"""Content jobs (background-jobs.md). Imported by ``app.handlers.load_handlers``.

``generate_content``: three phases, and the model is called in the middle with **no transaction
open** (agent-runtime.md section 2). The run belongs to the draft (G7); the job only re-reads
state, so a replay stores nothing twice.
"""

from sqlalchemy import select

from app.ai.models import AgentRun
from app.ai.runner import run_task
from app.ai.runtime import runner_deps
from app.ai.tasks.draft_content import DRAFT_CONTENT
from app.content import generation
from app.content.models import ContentItem
from app.content.payload import GenerateContentPayload
from app.jobs.registry import JobContext, job_handler


def _fail_run_if_open(job: JobContext, error_code: str) -> None:
    """The job is dead (the model stayed unavailable): the draft stays manual, the run says why."""
    payload = job.payload
    if not isinstance(payload, GenerateContentPayload) or job.workspace_id is None:
        return
    with job.session_factory() as session:
        item = session.scalar(
            select(ContentItem).where(
                ContentItem.workspace_id == job.workspace_id,
                ContentItem.id == payload.content_id,
            )
        )
        run = (
            session.scalar(
                select(AgentRun)
                .where(
                    AgentRun.workspace_id == job.workspace_id,
                    AgentRun.id == item.agent_run_id,
                )
                .with_for_update()
            )
            if item is not None and item.agent_run_id is not None
            else None
        )
        unfinished = run is not None and "stored_at" not in (run.input_snapshot or {})
        if run is not None and unfinished and run.status != "succeeded":
            run.status, run.error_code = "failed", error_code
            run.completed_at = job.clock.now()
        session.commit()


@job_handler(
    "generate_content",
    GenerateContentPayload,
    max_attempts=3,  # agent-runtime.md section 2: 10 s / 60 s backoff, like draft_reply
    timeout=150,  # two model calls (the call and one repair) of 45 s each
    on_dead=_fail_run_if_open,
    backoff=(10, 60, 300),
)
def generate_content(job: JobContext) -> None:
    payload = job.payload
    if not isinstance(payload, GenerateContentPayload) or job.workspace_id is None:
        return
    with job.session_factory() as session:  # [T1] read-only
        prepared = generation.prepare(session, job.clock, job.workspace_id, payload)
        session.commit()
    if prepared is None:
        return

    proposal = prepared.proposal
    if proposal is None:
        outcome = run_task(  # no transaction is open during the model call
            runner_deps(job.session_factory, job.clock),
            prepared.ctx,
            DRAFT_CONTENT,
            prepared.task_input,
            prepared.correlation_id,
            job_id=job.job_id,
            agent_run_id=prepared.run_id,
        )
        if outcome.output is None:  # the run is recorded as failed; the draft stays manual
            with job.session_factory() as session:
                generation.record_failure(
                    session, job.clock, prepared, outcome.error_code or "LLM_UNAVAILABLE"
                )
                session.commit()
            return
        proposal = outcome.output

    with job.session_factory() as session:  # [T3] re-check, render, validate, save
        generation.store(session, job.clock, prepared, proposal)
        session.commit()
