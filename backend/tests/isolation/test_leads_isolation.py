"""INV-01: list/export reject foreign workspaces and never mix lead data."""

import json

import pytest
from sqlalchemy import select

from app.audit.models import AuditLog
from tests.helpers.reporting import Builder


@pytest.mark.invariant("INV-01")
def test_leads_isolation(two_workspaces, db_session, clock):
    w = two_workspaces
    for workspace, owner, handle in ((w.a, w.a_owner, "A_handle"), (w.b, w.b_owner, "B_private")):
        # Fixture already has a connected mock account: disconnect it for this real history.
        from app.integrations.instagram.models import SocialAccount

        for account in db_session.scalars(
            select(SocialAccount).where(SocialAccount.workspace_id == workspace.id)
        ):
            account.status = "disconnected"
        db_session.flush()
        b = Builder(db_session, workspace, owner, simulated=False)
        c = b.conversation(clock.now())
        c.customer_handle = handle
        m = b.message(c, "inbound", clock.now())
        m.text = handle + " price?"
        d = b.draft(c, m, source="ai", decision="auto", created_at=clock.now())
        d.intent = "pricing"
    db_session.flush()
    foreign = f"/api/v1/workspaces/{w.b.id}/leads"
    assert w.a_client.get(foreign, headers=w.a_headers).status_code == 404
    assert w.a_client.post(foreign + "/export", json={}, headers=w.a_headers).status_code == 404
    assert not db_session.scalars(select(AuditLog).where(AuditLog.action == "leads.exported")).all()
    own = f"/api/v1/workspaces/{w.a.id}/leads"
    response = w.a_client.get(own, headers=w.a_headers)
    assert response.status_code == 200 and response.json()["total"] == 1
    assert "B_private" not in json.dumps(response.json())
    response = w.a_client.post(own + "/export", json={}, headers=w.a_headers)
    assert response.status_code == 200 and "B_private" not in response.text
    assert "A_handle" in response.text
