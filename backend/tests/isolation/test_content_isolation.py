"""Another workspace's content items are invisible, even through *my own* workspace URL (INV-01)."""

import uuid

import pytest
from sqlalchemy.orm import Session

from app.content.models import ContentItem
from tests.isolation.conftest import TwoWorkspaces


@pytest.mark.invariant("INV-01")
def test_b_content_item_is_not_found_through_any_workspace_url(
    two_workspaces: TwoWorkspaces,
) -> None:
    content_id = two_workspaces.foreign_ids["content_id"]
    client, headers = two_workspaces.a_client, two_workspaces.a_headers
    for workspace in (two_workspaces.a, two_workspaces.b):
        base = f"/api/v1/workspaces/{workspace.id}/content-items/{content_id}"
        for method, url, body in (
            ("GET", base, None),
            ("PATCH", base, {"expected_version": 1, "caption": "ele geçirildi"}),
            ("POST", f"{base}/validate", None),
            (
                "POST",
                f"{base}/submit",
                {"schedule": "now", "self_approve": True, "expected_version": 1},
            ),
            ("POST", f"{base}/cancel", None),
            (
                "POST",
                f"{base}/reapprove",
                {"schedule": "now", "expected_version": 1},
            ),
        ):
            response = client.request(method, url, json=body, headers=headers)
            assert response.status_code == 404, (method, url)
            assert response.json()["code"] == "NOT_FOUND"


@pytest.mark.invariant("INV-01")
def test_the_listing_of_a_never_contains_the_item_of_b(two_workspaces: TwoWorkspaces) -> None:
    url = f"/api/v1/workspaces/{two_workspaces.a.id}/content-items"
    response = two_workspaces.a_client.get(url, headers=two_workspaces.a_headers)
    assert response.status_code == 200
    assert response.json()["items"] == []
    assert two_workspaces.foreign_ids["content_id"] not in response.text


@pytest.mark.invariant("INV-01")
def test_b_media_cannot_be_attached_to_an_item_of_a(two_workspaces: TwoWorkspaces) -> None:
    url = f"/api/v1/workspaces/{two_workspaces.a.id}/content-items"
    response = two_workspaces.a_client.post(
        url,
        json={
            "content_type": "feed_image",
            "title": "x",
            "media_asset_id": two_workspaces.foreign_ids["media_id"],
        },
        headers=two_workspaces.a_headers,
    )
    assert response.status_code == 404
    assert two_workspaces.a_client.get(url, headers=two_workspaces.a_headers).json()["items"] == []


@pytest.mark.invariant("INV-01")
def test_b_item_is_untouched_after_every_attempt_through_a(
    two_workspaces: TwoWorkspaces, db_session: Session
) -> None:
    """Besides the 404, nothing happened: the foreign item is still a draft with no approval."""
    content_id = two_workspaces.foreign_ids["content_id"]
    base = f"/api/v1/workspaces/{two_workspaces.a.id}/content-items/{content_id}"
    client, headers = two_workspaces.a_client, two_workspaces.a_headers
    client.post(
        f"{base}/submit",
        json={"schedule": "now", "self_approve": True, "expected_version": 1},
        headers=headers,
    )
    client.post(f"{base}/cancel", headers=headers)
    item = db_session.get(ContentItem, uuid.UUID(content_id))
    assert item is not None
    assert (item.status, item.approval_id, item.scheduled_at) == ("draft", None, None)
