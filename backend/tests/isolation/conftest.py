"""Isolation harness fixtures (INV-01, AC-X1).

Two workspaces, A and B. ``a_client`` is signed in as the *owner of A and of nothing else*.
Every workspace-scoped route is then called with B's identifiers; the answer must be 404.

Later phases register the IDs of the resources they create in B through ``foreign_ids``
(path parameter name -> B's value), so their routes are tested with real foreign IDs.
"""

import uuid
from dataclasses import dataclass, field
from datetime import timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.ai.models import AgentRun
from app.approvals import service as approvals_service
from app.commands.models import OwnerCommand
from app.core.clock import FrozenClock
from app.identity.models import User, Workspace
from app.integrations.instagram.models import SocialAccount
from app.notifications import service as notifications_service
from tests.factories import (
    create_candidate,
    create_fact,
    knowledge_ctx,
    login,
    money,
    workspace_with_members,
)


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
    # An approval and a notification in B (Phase 3).
    clock = FrozenClock()
    b_ctx = knowledge_ctx(b, b_users["owner"], "owner")
    b_approval = approvals_service.request(
        db_session,
        clock,
        b_ctx,
        kind="confirmation",
        action="command.update_fact",
        subject_type="owner_command",
        subject_id=uuid.uuid4(),
        subject_version=1,
        payload={"x": 1},
        summary={"label": "B"},
        required_permission="knowledge.verify",
        expires_at=clock.now() + timedelta(minutes=30),
    )
    b_notification = notifications_service.notify(
        db_session, clock, b_ctx, recipient_user_id=b_users["owner"].id, type="test.note"
    )
    assert b_notification is not None
    b_command = OwnerCommand(
        workspace_id=b.id,
        user_id=b_users["owner"].id,
        channel="web",
        client_request_id="isolation",
        raw_text="Aylık üyelik ne kadar?",
        status="needs_clarification",
        correlation_id=uuid.uuid4(),
        created_at=clock.now(),
    )
    db_session.add(b_command)
    b_run = AgentRun(
        workspace_id=b.id,
        task="extract_fact_candidates",
        status="queued",
        input_snapshot={"user_id": str(b_users["owner"].id), "client_request_id": "isolation"},
        created_at=clock.now(),
    )
    db_session.add(b_run)
    # Phase 4: B's simulated Instagram account.
    b_account = SocialAccount(
        workspace_id=b.id,
        provider_kind="mock",
        external_account_id="mock-isolation-b",
        username="b.demo",
        status="connected",
    )
    db_session.add(b_account)
    db_session.commit()
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
            "approval_id": str(b_approval.id),
            "notification_id": str(b_notification.id),
            "command_id": str(b_command.id),
            "run_id": str(b_run.id),
            "account_id": str(b_account.id),
        },
    )
