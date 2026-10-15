import re
import uuid

import pytest
from fastapi import FastAPI

from tests.helpers.routes import ApiRoute, dependency_names, iter_api_routes
from tests.isolation.conftest import TwoWorkspaces

WORKSPACE_PREFIX = "/api/v1/workspaces/{workspace_id}"
PARAM = re.compile(r"\{(\w+)(?::\w+)?\}")


def workspace_routes(app: FastAPI) -> list[tuple[str, ApiRoute]]:
    """(method, route) for every route under /api/v1/workspaces/{workspace_id}."""
    return [
        (method, route)
        for route in iter_api_routes(app)
        if route.path.startswith(WORKSPACE_PREFIX)
        for method in sorted(route.methods)
    ]


def fill(path: str, ids: dict[str, str]) -> str:
    return PARAM.sub(lambda m: ids.get(m.group(1)) or str(uuid.uuid4()), path)


def test_the_harness_finds_the_phase_1_workspace_routes(two_workspaces: TwoWorkspaces) -> None:
    routes = {(m, r.path) for m, r in workspace_routes(two_workspaces.app)}
    assert {
        ("GET", "/api/v1/workspaces/{workspace_id}"),
        ("PATCH", "/api/v1/workspaces/{workspace_id}"),
        ("GET", "/api/v1/workspaces/{workspace_id}/members"),
    } <= routes


@pytest.mark.invariant("INV-01")
def test_every_workspace_route_returns_404_for_a_foreign_workspace(
    two_workspaces: TwoWorkspaces,
) -> None:
    """AC-X1: an A member using B's IDs gets 404 on every workspace-scoped endpoint."""
    routes = workspace_routes(two_workspaces.app)
    assert len(routes) >= 3, "route enumeration found too few routes: the harness is broken"
    failures = []
    for method, route in routes:
        url = fill(route.path, two_workspaces.foreign_ids)
        response = two_workspaces.a_client.request(
            method, url, json={} if method != "GET" else None, headers=two_workspaces.a_headers
        )
        if response.status_code != 404 or response.json().get("code") != "NOT_FOUND":
            failures.append(f"{method} {url} -> {response.status_code} {response.text[:120]}")
    assert not failures, "foreign-workspace requests were not answered with 404:\n" + "\n".join(
        failures
    )


@pytest.mark.invariant("INV-01")
def test_foreign_routes_stay_404_even_for_a_member_with_every_permission(
    two_workspaces: TwoWorkspaces,
) -> None:
    """The owner role of A grants nothing in B (not 403, which would reveal existence)."""
    response = two_workspaces.a_client.patch(
        f"/api/v1/workspaces/{two_workspaces.b.id}",
        json={"name": "Taken over"},
        headers=two_workspaces.a_headers,
    )
    assert response.status_code == 404


def test_the_same_requests_succeed_for_the_member_own_workspace(
    two_workspaces: TwoWorkspaces,
) -> None:
    """Guards the harness: a 404 above must come from tenancy, not from a broken URL."""
    own_ids = {"workspace_id": str(two_workspaces.a.id)}
    checked = 0
    for method, route in workspace_routes(two_workspaces.app):
        if set(PARAM.findall(route.path)) != {"workspace_id"}:
            continue  # routes with sub-resource IDs are checked by their own phases
        response = two_workspaces.a_client.request(
            method,
            fill(route.path, own_ids),
            json={} if method != "GET" else None,
            headers=two_workspaces.a_headers,
        )
        assert response.status_code != 404, (method, route.path, response.text)
        checked += 1
    assert checked >= 3


@pytest.mark.invariant("INV-01")
def test_every_workspace_route_is_guarded_by_require_membership(app: FastAPI) -> None:
    """A route added without ``require_membership`` fails here, before any request is made."""
    routes = workspace_routes(app)
    assert len(routes) >= 3, "route enumeration found too few routes: the harness is broken"
    unguarded = [
        f"{method} {route.path}"
        for method, route in routes
        if not any(n.startswith("require_membership.") for n in dependency_names(route.dependant))
    ]
    assert not unguarded, f"workspace routes without require_membership: {unguarded}"


@pytest.mark.invariant("INV-01")
def test_listings_never_contain_the_other_workspaces_rows(two_workspaces: TwoWorkspaces) -> None:
    listing = two_workspaces.a_client.get("/api/v1/workspaces").json()
    assert [i["workspace_id"] for i in listing["items"]] == [str(two_workspaces.a.id)]

    members = two_workspaces.a_client.get(f"/api/v1/workspaces/{two_workspaces.a.id}/members")
    user_ids = {m["user_id"] for m in members.json()["items"]}
    assert user_ids == {str(two_workspaces.a_owner.id)}
    assert str(two_workspaces.b_owner.id) not in members.text

    me = two_workspaces.a_client.get("/api/v1/auth/me").json()
    assert [m["workspace_id"] for m in me["memberships"]] == [str(two_workspaces.a.id)]
