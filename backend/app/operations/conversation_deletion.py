"""Fence authorization while a workspace has outstanding conversation erasure."""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.jobs.models import Job


def pending(
    session: Session, workspace_id: uuid.UUID, *, account_id: uuid.UUID | None = None
) -> bool:
    statement = select(Job.id).where(
        Job.workspace_id == workspace_id,
        Job.job_type == "delete_account_conversations",
        Job.status.in_(("queued", "running", "dead")),
    )
    if account_id is not None:
        statement = statement.where(Job.payload["social_account_id"].astext == str(account_id))
    return session.scalar(statement.limit(1)) is not None
