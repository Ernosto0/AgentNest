"""Safe pre-coordinator registration of the durable agent wake job.

Session 05 replaces this handler with the coordinator. Until then an inactive account has
nothing to do and an active account fails closed rather than silently consuming work.
"""

import uuid

from pydantic import BaseModel

from app.agent.models import AccountAgent, AgentThread
from app.jobs.registry import JobContext, job_handler


class AgentWakePayload(BaseModel):
    thread_id: uuid.UUID


@job_handler("agent_wake", AgentWakePayload)
def agent_wake(ctx: JobContext) -> None:
    payload = AgentWakePayload.model_validate(ctx.payload)
    with ctx.session_factory() as session:
        thread = session.get(AgentThread, payload.thread_id)
        if thread is None or thread.workspace_id != ctx.workspace_id:
            return
        account = (
            session.query(AccountAgent)
            .filter_by(workspace_id=thread.workspace_id, social_account_id=thread.social_account_id)
            .one_or_none()
        )
        if account is None or account.state != "active" or account.controller_mode != "agent":
            return
    raise RuntimeError("agent coordinator is not registered yet")
