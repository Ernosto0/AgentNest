"""Phase 5 routes beyond the content and media items: publish approvals, content creation and
generation, accounts (reconnect), automation review and the simulator listing (INV-01, AC-X1).

A is signed in as the owner of A only. B's identifiers are real (see ``foreign_ids``); every
answer must be 404, through A's URL and through B's.
"""

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.approvals.models import Approval
from app.content.models import ContentItem, MediaAsset
from app.integrations.instagram.models import SocialAccount
from tests.helpers.images import png_bytes
from tests.isolation.conftest import TwoWorkspaces


def count(session: Session, model: type) -> int:
    return session.scalar(select(func.count()).select_from(model)) or 0


@pytest.mark.invariant("INV-01")
def test_b_publish_authorisation_is_not_found_through_any_workspace_url(
    two_workspaces: TwoWorkspaces, db_session: Session
) -> None:
    approval_id = two_workspaces.foreign_ids["content_approval_id"]
    client, headers = two_workspaces.a_client, two_workspaces.a_headers
    decision = {"decision": "approve", "payload_hash": "0" * 64}
    for workspace in (two_workspaces.a, two_workspaces.b):
        base = f"/api/v1/workspaces/{workspace.id}/approvals/{approval_id}"
        for method, url, body in (("GET", base, None), ("POST", f"{base}/decision", decision)):
            response = client.request(method, url, json=body, headers=headers)
            assert response.status_code == 404, (method, url)
            assert response.json()["code"] == "NOT_FOUND"
    assert (
        two_workspaces.foreign_ids["content_approval_id"]
        not in client.get(
            f"/api/v1/workspaces/{two_workspaces.a.id}/approvals", headers=headers
        ).text
    )
    approval = db_session.get(Approval, approval_id)
    assert approval is not None and approval.status == "pending"  # nothing was decided


@pytest.mark.invariant("INV-01")
def test_creating_uploading_and_generating_through_b_url_is_404_and_creates_nothing(
    two_workspaces: TwoWorkspaces, db_session: Session
) -> None:
    client, headers = two_workspaces.a_client, two_workspaces.a_headers
    base = f"/api/v1/workspaces/{two_workspaces.b.id}"
    items_before = count(db_session, ContentItem)
    media_before = count(db_session, MediaAsset)

    requests = [
        ("GET", f"{base}/content-items", {}),
        ("POST", f"{base}/content-items", {"json": {"content_type": "feed_image", "title": "x"}}),
        (
            "POST",
            f"{base}/content-items/generate",
            {"json": {"content_type": "feed_image", "objective": "x", "client_request_id": "c1"}},
        ),
        ("POST", f"{base}/media", {"files": {"file": ("a.png", png_bytes(), "image/png")}}),
    ]
    for method, url, kwargs in requests:
        response = client.request(method, url, headers=headers, **kwargs)
        assert response.status_code == 404, (method, url, response.text[:100])
        assert response.json()["code"] == "NOT_FOUND"

    assert count(db_session, ContentItem) == items_before
    assert count(db_session, MediaAsset) == media_before


@pytest.mark.invariant("INV-01")
def test_b_account_cannot_be_reconnected_or_disconnected_by_a(
    two_workspaces: TwoWorkspaces, db_session: Session
) -> None:
    account_id = two_workspaces.foreign_ids["account_id"]
    client, headers = two_workspaces.a_client, two_workspaces.a_headers
    for workspace in (two_workspaces.a, two_workspaces.b):
        base = f"/api/v1/workspaces/{workspace.id}/social-accounts/{account_id}"
        for action in ("reconnect", "disconnect"):
            response = client.post(f"{base}/{action}", headers=headers)
            assert response.status_code == 404, (workspace.id, action)
            assert response.json()["code"] == "NOT_FOUND"
    listing = client.get(f"/api/v1/workspaces/{two_workspaces.a.id}/social-accounts")
    assert account_id not in listing.text
    account = db_session.get(SocialAccount, account_id)
    assert account is not None and account.status == "connected"  # untouched


@pytest.mark.invariant("INV-01")
def test_b_automation_settings_are_not_reachable_or_reviewable_by_a(
    two_workspaces: TwoWorkspaces,
) -> None:
    client, headers = two_workspaces.a_client, two_workspaces.a_headers
    base = f"/api/v1/workspaces/{two_workspaces.b.id}/automation-policies"
    for method, url, body in (
        ("GET", base, None),
        ("PUT", base, {"items": []}),
        ("POST", f"{base}/review", None),
    ):
        response = client.request(method, url, json=body, headers=headers)
        assert response.status_code == 404, (method, url)
        assert response.json()["code"] == "NOT_FOUND"


@pytest.mark.invariant("INV-01")
def test_the_simulator_listing_of_a_never_shows_what_b_published(
    two_workspaces: TwoWorkspaces,
) -> None:
    client, headers = two_workspaces.a_client, two_workspaces.a_headers
    own = client.get(
        f"/api/v1/dev/workspaces/{two_workspaces.a.id}/simulator/published", headers=headers
    )
    assert own.status_code == 200
    assert own.json()["items"] == []
    assert two_workspaces.foreign_ids["sim_media_id"] not in own.text

    foreign = client.get(
        f"/api/v1/dev/workspaces/{two_workspaces.b.id}/simulator/published", headers=headers
    )
    assert foreign.status_code == 404
    assert two_workspaces.foreign_ids["sim_media_id"] not in foreign.text
