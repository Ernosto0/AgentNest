"""Foreign account identifiers never change comment opt-in."""


def test_foreign_comment_automation_id(two_workspaces):
    tw = two_workspaces
    response = tw.a_client.put(
        f"/api/v1/workspaces/{tw.a.id}/accounts/{tw.foreign_ids['account_id']}/comment-automation",
        json={"enabled": True},
        headers=tw.a_headers,
    )
    assert response.status_code == 404
    assert response.json()["code"] == "NOT_FOUND"
