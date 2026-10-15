"""Fixtures for the knowledge integration tests: one gym workspace with an owner, a manager and
a staff member, each with an independent signed-in client."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.clock import FrozenClock
from app.identity.models import User, Workspace
from tests.factories import login, workspace_with_members


@dataclass
class Role:
    user: User
    client: TestClient
    headers: dict[str, str]


@dataclass
class KnowledgeEnv:
    workspace: Workspace
    owner: Role
    manager: Role
    staff: Role
    session: Session
    clock: FrozenClock

    @property
    def base(self) -> str:
        return f"/api/v1/workspaces/{self.workspace.id}"

    def call(self, role: Role, method: str, path: str, **kwargs: Any) -> Any:
        """Request ``{base}{path}`` as ``role`` (state-changing calls carry the CSRF header)."""
        return role.client.request(method, f"{self.base}{path}", headers=role.headers, **kwargs)


@pytest.fixture
def env(
    db_session: Session, make_client: Callable[[], TestClient], clock: FrozenClock
) -> KnowledgeEnv:
    workspace, users = workspace_with_members(
        db_session, roles=("owner", "manager", "staff"), name="Gölkent", slug="golkent"
    )
    roles = {}
    for name, user in users.items():
        client = make_client()
        roles[name] = Role(user=user, client=client, headers=login(client, user))
    return KnowledgeEnv(
        workspace=workspace,
        owner=roles["owner"],
        manager=roles["manager"],
        staff=roles["staff"],
        session=db_session,
        clock=clock,
    )
