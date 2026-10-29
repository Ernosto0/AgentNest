"""Content-free manual-operation reservations shared with agent admission."""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.operations.models import Operation


def unresolved(db: Session, workspace: uuid.UUID, account: uuid.UUID, target: uuid.UUID) -> bool:
    return (
        db.scalar(
            select(Operation.id)
            .where(
                Operation.workspace_id == workspace,
                Operation.social_account_id == account,
                Operation.subject_type == "public_comment",
                Operation.subject_id == target,
                Operation.status.in_(("pending", "in_progress", "outcome_unknown")),
            )
            .limit(1)
        )
        is not None
    )
