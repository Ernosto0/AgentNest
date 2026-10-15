"""Request/job scoped context that every workspace-scoped service and repository requires."""

import uuid
from dataclasses import dataclass
from typing import Literal

ActorType = Literal["user", "system", "agent", "provider"]


@dataclass(frozen=True)
class ActorRef:
    type: ActorType
    id: str | None = None

    @classmethod
    def user(cls, user_id: uuid.UUID) -> "ActorRef":
        return cls("user", str(user_id))

    @classmethod
    def system(cls, name: str | None = None) -> "ActorRef":
        return cls("system", name)


@dataclass(frozen=True)
class WorkspaceContext:
    workspace_id: uuid.UUID
    actor: ActorRef
    role: str | None
    timezone: str
    locale: str
    is_demo: bool
