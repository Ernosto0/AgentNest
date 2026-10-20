"""Command jobs (workflows.md §B). Imported by ``app.handlers.load_handlers``.

``interpret_command`` has three phases, and the model is called in the middle with **no
transaction open**:

1. a short transaction gathers the context (facts, requester, registry);
2. ``ai.run_task`` calls the model (retries are the job's: ``RetryableError`` from the runner);
3. a second transaction resolves the proposal and records the outcome, discarding it if the
   command was cancelled meanwhile.
"""

from sqlalchemy.orm import Session

from app.ai.runner import run_task
from app.ai.runtime import runner_deps
from app.ai.tasks.interpret_command import INTERPRET_COMMAND
from app.commands import service
from app.commands.payloads import ExpireCommandsPayload, InterpretCommandPayload
from app.core.clock import Clock
from app.jobs.queue import enqueue
from app.jobs.registry import JobContext, job_handler
from app.jobs.scheduler import register_periodic

# Two model calls (the call and one repair) at 30 s each, plus the database work.
INTERPRET_TIMEOUT_SECONDS = 90


def _on_dead(job: JobContext, error_code: str) -> None:
    payload = job.payload
    if not isinstance(payload, InterpretCommandPayload) or job.workspace_id is None:
        return
    with job.session_factory() as session:
        service.fail_after_dead_job(
            session, job.clock, job.workspace_id, payload.command_id, error_code
        )


@job_handler(
    "interpret_command",
    InterpretCommandPayload,
    max_attempts=3,  # agent-runtime.md §2: 10 s / 60 s / 300 s backoff
    timeout=INTERPRET_TIMEOUT_SECONDS,
    on_dead=_on_dead,
    backoff=(10, 60, 300),
)
def interpret_command(job: JobContext) -> None:
    payload = job.payload
    if not isinstance(payload, InterpretCommandPayload) or job.workspace_id is None:
        return
    with job.session_factory() as session:  # [T1]
        prepared = service.prepare_interpretation(
            session, job.clock, job.workspace_id, payload.command_id
        )
        session.commit()
    if prepared is None:  # gone, cancelled, or already resolved by an earlier attempt
        return
    outcome = run_task(  # no transaction is open here
        runner_deps(job.session_factory, job.clock),
        prepared.ctx,
        INTERPRET_COMMAND,
        prepared.task_input,
        prepared.correlation_id,
        job_id=job.job_id,
    )
    with job.session_factory() as session:  # [T2]
        service.finish_interpretation(
            session,
            job.clock,
            job.workspace_id,
            payload.command_id,
            output=outcome.output,
            error_code=outcome.error_code,
            agent_run_id=outcome.agent_run_id,
            content_aliases=prepared.content_aliases,
        )


@job_handler("expire_commands", ExpireCommandsPayload, max_attempts=1)
def expire_commands(job: JobContext) -> None:
    """Clarifications nobody answered in 30 minutes. (Confirmations expire through their
    approvals; reads also expire both lazily.)"""
    with job.session_factory() as session:
        service.expire_clarifications(session, job.clock)


@register_periodic
def enqueue_command_expiry(session: Session, clock: Clock) -> int:
    enqueue(
        session,
        "expire_commands",
        ExpireCommandsPayload(),
        workspace_id=None,
        correlation_id=None,
        dedup_key=f"expire_commands:{clock.now():%Y-%m-%dT%H:%M}",
        clock=clock,
    )
    return 1
