"""Approvals and notifications of another workspace are invisible, even through *my own*
workspace URL (INV-01, AC-X1)."""

import pytest

from tests.isolation.conftest import TwoWorkspaces


@pytest.mark.invariant("INV-01")
def test_b_approvals_and_notifications_are_not_found_through_a_workspace_url(
    two_workspaces: TwoWorkspaces,
) -> None:
    a_base = f"/api/v1/workspaces/{two_workspaces.a.id}"
    approval_id = two_workspaces.foreign_ids["approval_id"]
    notification_id = two_workspaces.foreign_ids["notification_id"]
    client, headers = two_workspaces.a_client, two_workspaces.a_headers
    decision = {"decision": "approve", "payload_hash": "0" * 64}
    requests = [
        ("GET", f"/approvals/{approval_id}", None),
        ("POST", f"/approvals/{approval_id}/decision", decision),
        ("POST", f"/approvals/{approval_id}/decision", {**decision, "decision": "reject"}),
        ("POST", f"/notifications/{notification_id}/read", None),
    ]
    for method, path, body in requests:
        response = client.request(method, a_base + path, json=body, headers=headers)
        assert response.status_code == 404, f"{method} {path} -> {response.status_code}"
        assert response.json()["code"] == "NOT_FOUND"


@pytest.mark.invariant("INV-01")
def test_listings_never_contain_the_other_workspaces_approvals_or_notifications(
    two_workspaces: TwoWorkspaces,
) -> None:
    a_base = f"/api/v1/workspaces/{two_workspaces.a.id}"
    client = two_workspaces.a_client
    assert client.get(f"{a_base}/approvals").json()["items"] == []
    assert client.get(f"{a_base}/approvals?status=pending").json()["items"] == []
    listing = client.get(f"{a_base}/notifications").json()
    assert listing["items"] == [] and listing["unread_count"] == 0


@pytest.mark.invariant("INV-01")
def test_b_commands_are_not_found_through_a_workspace_url(two_workspaces: TwoWorkspaces) -> None:
    a_base = f"/api/v1/workspaces/{two_workspaces.a.id}"
    command_id = two_workspaces.foreign_ids["command_id"]
    client, headers = two_workspaces.a_client, two_workspaces.a_headers
    requests = [
        ("GET", f"/commands/{command_id}", None),
        ("POST", f"/commands/{command_id}/cancel", None),
        ("POST", f"/commands/{command_id}/clarification", {"option_id": "x"}),
    ]
    for method, path, body in requests:
        response = client.request(method, a_base + path, json=body, headers=headers)
        assert response.status_code == 404, f"{method} {path} -> {response.status_code}"
        assert response.json()["code"] == "NOT_FOUND"
    assert client.get(f"{a_base}/commands").json()["items"] == []
