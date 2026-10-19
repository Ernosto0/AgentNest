"""Contexts for work that has no signed-in user (webhooks, jobs)."""

import uuid

from sqlalchemy.orm import Session

from app.core.context import ActorRef, WorkspaceContext
from app.identity import service as identity_service
from app.identity.models import Workspace


def system_context(
    session: Session, workspace_id: uuid.UUID, name: str = "inbox"
) -> WorkspaceContext | None:
    """The workspace acting as the system, or ``None`` if it no longer exists."""
    workspace = session.get(Workspace, workspace_id)
    if workspace is None:
        return None
    return identity_service.workspace_context(workspace, ActorRef.system(name), None)
