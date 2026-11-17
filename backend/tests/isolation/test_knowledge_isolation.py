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


def test_import_run_and_account_are_workspace_scoped(two_workspaces: TwoWorkspaces) -> None:
    base = f"/api/v1/workspaces/{two_workspaces.a.id}"
    client = two_workspaces.a_client
    response = client.get(f"{base}/knowledge/extractions/{two_workspaces.foreign_ids['run_id']}")
    assert response.status_code == 404 and response.json()["code"] == "NOT_FOUND"
    response = client.post(
        f"{base}/knowledge/imports/instagram",
        json={"client_request_id": "foreign-account"},
        headers=two_workspaces.a_headers,
    )
    assert response.status_code == 409 and response.json()["code"] == "CONFLICT_STATE"
    assert client.get(f"{base}/fact-candidates").json()["items"] == []


def test_website_import_prefill_run_and_candidates_are_isolated(
    two_workspaces: TwoWorkspaces,
    db_session,
    clock,
) -> None:
    import uuid

    from app.ai.models import AgentRun
    from app.core.context import ActorRef
    from app.identity.service import workspace_context
    from app.knowledge import imports
    from tests.factories import create_candidate, money

    create_candidate(
        db_session,
        two_workspaces.b,
        "pricing.membership_3_months",
        money("16500"),
        source_type="website",
    )
    b_ctx = workspace_context(two_workspaces.b, ActorRef.user(two_workspaces.b_owner.id), "owner")
    foreign = imports.create_import_run(
        db_session,
        clock,
        b_ctx,
        source_type="website",
        snapshot_extra={"website_url": "https://private-business.example/"},
        client_request_id="foreign-website",
    )
    db_session.commit()
    a_base = f"/api/v1/workspaces/{two_workspaces.a.id}"
    client = two_workspaces.a_client
    assert client.get(f"{a_base}/knowledge/imports/website/prefill").json() == {"url": None}
    assert client.get(f"{a_base}/knowledge/extractions/{foreign.id}").status_code == 404
    assert client.get(f"{a_base}/fact-candidates").json()["items"] == []
    response = client.post(
        f"{a_base}/knowledge/imports/website",
        json={"url": "https://own-business.example/", "client_request_id": "own-website"},
        headers=two_workspaces.a_headers,
    )
    assert response.status_code == 202
    own = db_session.get(AgentRun, uuid.UUID(response.json()["run_id"]))
    assert own.workspace_id == two_workspaces.a.id and own.id != foreign.id
    assert client.get(f"{a_base}/knowledge/imports/website/prefill").json() == {
        "url": "https://own-business.example/"
    }
