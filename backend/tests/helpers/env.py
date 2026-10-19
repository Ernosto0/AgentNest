"""A gym workspace with an owner, a manager and a staff member, each with a signed-in client.

Shared by the approvals and commands integration tests.
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.clock import FrozenClock
from app.core.context import WorkspaceContext
from app.identity.models import User, Workspace
from tests.factories import knowledge_ctx, login, workspace_with_members


@dataclass
class Role:
    name: str
    user: User
    client: TestClient
    headers: dict[str, str]


@dataclass
class Env:
    workspace: Workspace
    owner: Role
    manager: Role
    staff: Role
    session: Session
    clock: FrozenClock

    @property
    def base(self) -> str:
        return f"/api/v1/workspaces/{self.workspace.id}"

    def ctx(self, role: Role) -> WorkspaceContext:
        """A service-level context for ``role``'s user."""
        return knowledge_ctx(self.workspace, role.user, role.name)

    def call(self, role: Role, method: str, path: str, **kwargs: Any) -> Any:
        """Request ``{base}{path}`` as ``role`` (state-changing calls carry the CSRF header)."""
        return role.client.request(method, f"{self.base}{path}", headers=role.headers, **kwargs)


def build_env(
    db_session: Session, make_client: Callable[[], TestClient], clock: FrozenClock
) -> Env:
    workspace, users = workspace_with_members(
        db_session, roles=("owner", "manager", "staff"), name="Gölkent", slug="golkent"
    )
    roles = {}
    for name, user in users.items():
        client = make_client()
        roles[name] = Role(name, user, client, login(client, user))
    return Env(
        workspace=workspace,
        owner=roles["owner"],
        manager=roles["manager"],
        staff=roles["staff"],
        session=db_session,
        clock=clock,
    )
