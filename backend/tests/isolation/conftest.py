"""Isolation harness fixtures (INV-01, AC-X1).

Two workspaces, A and B. ``a_client`` is signed in as the *owner of A and of nothing else*.
Every workspace-scoped route is then called with B's identifiers; the answer must be 404.

Later phases register the IDs of the resources they create in B through ``foreign_ids``
(path parameter name -> B's value), so their routes are tested with real foreign IDs.
"""

from dataclasses import dataclass, field

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.identity.models import User, Workspace
from tests.factories import create_candidate, create_fact, login, money, workspace_with_members


@dataclass
class TwoWorkspaces:
    app: FastAPI
    a: Workspace
    b: Workspace
    a_owner: User
    b_owner: User
    a_client: TestClient
    a_headers: dict[str, str]
    # Path parameter name -> a real identifier that belongs to workspace B.
    foreign_ids: dict[str, str] = field(default_factory=dict)


@pytest.fixture
def two_workspaces(app: FastAPI, client: TestClient, db_session: Session) -> TwoWorkspaces:
    a, a_users = workspace_with_members(db_session, name="Workspace A")
    b, b_users = workspace_with_members(db_session, name="Workspace B")
    headers = login(client, a_users["owner"])
    # Real knowledge rows in B, so fact/candidate routes are probed with genuine foreign IDs.
    b_fact = create_fact(db_session, b, "pricing.membership_monthly", money())
    b_candidate = create_candidate(db_session, b, "pricing.membership_monthly", money("5500"))
    return TwoWorkspaces(
        app=app,
        a=a,
        b=b,
        a_owner=a_users["owner"],
        b_owner=b_users["owner"],
        a_client=client,
        a_headers=headers,
        foreign_ids={
            "workspace_id": str(b.id),
            "fact_id": str(b_fact.id),
            "candidate_id": str(b_candidate.id),
        },
    )
