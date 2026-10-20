"""Another workspace's media is invisible, even through *my own* workspace URL (INV-01)."""

import pytest

from tests.isolation.conftest import TwoWorkspaces


@pytest.mark.invariant("INV-01")
def test_b_media_is_not_found_through_a_workspace_url(two_workspaces: TwoWorkspaces) -> None:
    media_id = two_workspaces.foreign_ids["media_id"]
    client = two_workspaces.a_client
    for workspace in (two_workspaces.a, two_workspaces.b):
        url = f"/api/v1/workspaces/{workspace.id}/media/{media_id}/content"
        response = client.get(url)
        assert response.status_code == 404, url
        assert response.json()["code"] == "NOT_FOUND"
