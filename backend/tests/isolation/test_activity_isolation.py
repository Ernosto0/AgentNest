"""The Activity route (INV-01, AC-X1): a foreign workspace is a 404, and one workspace's audit
rows never reach another workspace's feed, directly or through a resource label."""

import uuid

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.audit.models import AuditLog
from tests.isolation.conftest import TwoWorkspaces


@pytest.mark.invariant("INV-01")
def test_the_activity_route_is_404_for_a_foreign_workspace(
    two_workspaces: TwoWorkspaces, db_session: Session
) -> None:
    client, headers = two_workspaces.a_client, two_workspaces.a_headers
    before = db_session.scalar(select(func.count()).select_from(AuditLog))
    for query in ("", "?type=messages", "?date=2026-01-15", "?cursor=abc"):
        response = client.get(
            f"/api/v1/workspaces/{two_workspaces.b.id}/activity{query}", headers=headers
        )
        assert response.status_code == 404, query
        assert response.json()["code"] == "NOT_FOUND"
    assert db_session.scalar(select(func.count()).select_from(AuditLog)) == before


@pytest.mark.invariant("INV-01")
def test_the_feed_of_a_never_shows_b_rows_or_b_labels(
    two_workspaces: TwoWorkspaces, db_session: Session
) -> None:
    clock = two_workspaces.app.state.clock
    now = clock.now()
    foreign_message = uuid.UUID(two_workspaces.foreign_ids["message_id"])
    foreign_content = two_workspaces.foreign_ids.get("content_id")
    # A row in B, and a row in A that points at B's records (a corrupt reference must not leak).
    b_row = AuditLog(
        workspace_id=two_workspaces.b.id,
        occurred_at=now,
        actor_type="system",
        action="message.received",
        resource_type="message",
        resource_id=foreign_message,
    )
    a_row = AuditLog(
        workspace_id=two_workspaces.a.id,
        occurred_at=now,
        actor_type="system",
        action="message.received",
        resource_type="message",
        resource_id=foreign_message,
    )
    db_session.add_all([b_row, a_row])
    db_session.commit()

    client, headers = two_workspaces.a_client, two_workspaces.a_headers
    response = client.get(f"/api/v1/workspaces/{two_workspaces.a.id}/activity", headers=headers)
    assert response.status_code == 200
    items = response.json()["items"]
    assert str(b_row.id) not in response.text
    own = [e for e in items if e["id"] == str(a_row.id)]
    assert len(own) == 1
    # B's conversation is not resolved through A: neutral label, no link, no handle.
    assert own[0]["resource"]["label"] == "Silinmiş kayıt" and own[0]["resource"]["link"] is None
    assert str(two_workspaces.b.id) not in response.text
    if foreign_content:
        assert foreign_content not in response.text
