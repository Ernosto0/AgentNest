"""An old timer cannot resume a newer pause or restore revoked owner authority."""

import uuid
from datetime import datetime

from pydantic import BaseModel

from app.agent.repository import AgentScopeError, scoped_account
from app.agent.state import change_state
from app.core.context import ActorRef
from app.identity import repository, service
from app.identity.models import User
from app.jobs.registry import JobContext, RescheduleJob, job_handler


class ResumePayload(BaseModel):
    account_id: uuid.UUID
    config_version: int
    controller_epoch: int
    user_id: uuid.UUID
    resume_at: datetime


@job_handler("agent_resume_due", ResumePayload)
def resume_due(job: JobContext) -> None:
    payload = ResumePayload.model_validate(job.payload)
    if job.workspace_id is None:
        return
    if job.clock.now() < payload.resume_at:
        raise RescheduleJob(payload.resume_at)
    with job.session_factory() as db:
        try:
            account = scoped_account(db, job.workspace_id, payload.account_id, lock=True)
        except AgentScopeError:
            return
        if (
            account.state != "paused"
            or account.controller_mode != "agent"
            or account.config_version != payload.config_version
            or account.controller_epoch != payload.controller_epoch
        ):
            return
        found = repository.get_membership(db, job.workspace_id, payload.user_id)
        user = db.get(User, payload.user_id)
        if found is None or found[0].role != "owner" or user is None or not user.is_active:
            return
        ctx = service.workspace_context(found[1], ActorRef.user(payload.user_id), found[0].role)
        change_state(db, job.clock, ctx, payload.account_id, payload.config_version, "active")
        db.commit()
