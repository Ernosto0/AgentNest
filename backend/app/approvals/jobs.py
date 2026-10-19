"""``expire_approvals``: periodic sweep (workflows.md §D step 4, ADR-006).

Every scheduler tick enqueues one job per minute (deterministic dedup key). The job expires due
approvals one transaction each, so a failing subject callback blocks only its own approval.
Reads and decisions also expire lazily, so correctness never depends on this job running.
"""

from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.approvals import repository as repo
from app.approvals import service
from app.approvals.models import Approval
from app.core.clock import Clock
from app.core.context import ActorRef, WorkspaceContext
from app.core.logging import get_logger
from app.identity.models import Workspace
from app.jobs.queue import enqueue
from app.jobs.registry import JobContext, job_handler
from app.jobs.scheduler import register_periodic

BATCH = 100
_log = get_logger("app.approvals.jobs")


class ExpireApprovalsPayload(BaseModel):
    pass


@job_handler("expire_approvals", ExpireApprovalsPayload, max_attempts=1)
def expire_approvals(ctx: JobContext) -> None:
    with ctx.session_factory() as session:
        due_ids = repo.due_ids_all_workspaces(session, ctx.clock.now(), limit=BATCH)
    for approval_id in due_ids:
        try:
            with ctx.session_factory() as session:
                _expire(session, ctx.clock, approval_id)
        except Exception:
            _log.exception("approval_expiry_failed", approval_id=str(approval_id))


def _expire(session: Session, clock: Clock, approval_id: object) -> None:
    approval = session.get(Approval, approval_id, with_for_update=True)
    if approval is None or approval.status != "pending" or approval.expires_at > clock.now():
        return  # decided or cancelled meanwhile
    workspace = session.get(Workspace, approval.workspace_id)
    if workspace is None:
        return
    system = WorkspaceContext(
        workspace.id,
        ActorRef.system("approvals.expire"),
        None,
        workspace.timezone,
        workspace.default_locale,
        workspace.is_demo,
    )
    service.expire_one(session, clock, system, approval)
    session.commit()


@register_periodic
def enqueue_approval_expiry(session: Session, clock: Clock) -> int:
    enqueue(
        session,
        "expire_approvals",
        ExpireApprovalsPayload(),
        workspace_id=None,
        correlation_id=None,
        dedup_key=f"expire_approvals:{clock.now():%Y-%m-%dT%H:%M}",
        clock=clock,
    )
    return 1
