"""Knowledge resources of another workspace are invisible even through *my own* workspace URL
(INV-01, AC-X1). The generic harness covers foreign workspace IDs; this covers foreign
sub-resource IDs on a legitimate workspace path."""

import pytest

from tests.isolation.conftest import TwoWorkspaces

PRICE_KEY = "pricing.membership_monthly"


@pytest.mark.invariant("INV-01")
def test_b_resources_are_not_found_through_a_workspace_url(
    two_workspaces: TwoWorkspaces,
) -> None:
    a_base = f"/api/v1/workspaces/{two_workspaces.a.id}"
    fact_id = two_workspaces.foreign_ids["fact_id"]
    candidate_id = two_workspaces.foreign_ids["candidate_id"]
    client, headers = two_workspaces.a_client, two_workspaces.a_headers
    requests = [
        ("PATCH", f"/facts/{fact_id}", {"expected_version": 1, "value": {"amount": "1"}}),
        ("POST", f"/facts/{fact_id}/verify", {"expected_version": 1}),
        ("POST", f"/facts/{fact_id}/archive", {"expected_version": 1}),
        ("POST", f"/facts/{fact_id}/restore", {"expected_version": 1}),
        ("GET", f"/facts/{fact_id}/versions", None),
        ("POST", f"/fact-candidates/{candidate_id}/accept", None),
        ("POST", f"/fact-candidates/{candidate_id}/reject", None),
    ]
    for method, path, body in requests:
        response = client.request(method, a_base + path, json=body, headers=headers)
        assert response.status_code == 404, f"{method} {path} -> {response.status_code}"
        assert response.json()["code"] == "NOT_FOUND"


@pytest.mark.invariant("INV-01")
def test_listings_never_contain_the_other_workspaces_knowledge(
    two_workspaces: TwoWorkspaces,
) -> None:
    a_base = f"/api/v1/workspaces/{two_workspaces.a.id}"
    client = two_workspaces.a_client
    assert client.get(f"{a_base}/facts").json()["items"] == []
    assert client.get(f"{a_base}/fact-candidates").json()["items"] == []
    readiness = client.get(f"{a_base}/readiness").json()
    assert readiness["level"] == "not_ready"  # B's facts do not count for A
    template = {i["identifier"]: i for i in client.get(f"{a_base}/facts/template").json()}
    assert template[PRICE_KEY]["status"] == "missing"
    assert template[PRICE_KEY]["fact_ids"] == []
