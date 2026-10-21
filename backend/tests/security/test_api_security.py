"""Cross-cutting API security checks that cover routes added in later phases automatically."""

import re
import uuid
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.deps import CSRF_EXEMPT_PATHS, UNSAFE_METHODS
from tests.factories import create_user, login
from tests.helpers.routes import iter_api_routes

PARAM = re.compile(r"\{(\w+)(?::\w+)?\}")

# Fields that legitimately carry a secret-looking name. Everything else is a failure.
# ``csrf_token`` is handed to the signed-in user so the SPA can echo it in X-CSRF-Token.
# ``payload_hash`` is the public integrity binding of an approval (a SHA-256 of what will
# happen): the client must send back the hash it displayed (ADR-014). It is not a credential.
ALLOWED_SECRETISH_FIELDS = {"csrf_token", "payload_hash"}
SECRETISH = re.compile(r"password|secret|token|hash|cipher|api_key|credential", re.I)


def unsafe_api_routes(app: FastAPI) -> list[tuple[str, str]]:
    return [
        (method, route.path)
        for route in iter_api_routes(app)
        if route.path.startswith("/api/v1")
        for method in sorted(route.methods & UNSAFE_METHODS)
    ]


@pytest.mark.invariant("INV-10")
def test_every_unsafe_api_route_rejects_requests_without_the_csrf_token(
    app: FastAPI, client: TestClient, db_session: Session
) -> None:
    """Signed in, but no X-CSRF-Token header: 403 CSRF_FAILED everywhere, except the exempt list."""
    login(client, create_user(db_session))
    routes = unsafe_api_routes(app)
    assert len(routes) >= 4, "route enumeration found too few routes: the harness is broken"
    failures = []
    for method, path in routes:
        if path in CSRF_EXEMPT_PATHS:
            continue
        url = PARAM.sub(lambda _m: str(uuid.uuid4()), path)
        response = client.request(method, url, json={})
        if response.status_code != 403 or response.json().get("code") != "CSRF_FAILED":
            failures.append(f"{method} {url} -> {response.status_code}")
    assert not failures, "unsafe routes that accept requests without CSRF:\n" + "\n".join(failures)


def test_the_csrf_exemption_list_is_only_login_and_invite_accept() -> None:
    # Invite accept works signed out (a new user is created), so it is exempt exactly like login.
    assert {"/api/v1/auth/login", "/api/v1/invites/accept"} == set(CSRF_EXEMPT_PATHS)


def _walk(schema: Any, definitions: dict[str, Any], seen: set[str], out: set[str]) -> None:
    if isinstance(schema, dict):
        ref = schema.get("$ref")
        if ref:
            name = ref.rsplit("/", 1)[-1]
            if name not in seen:
                seen.add(name)
                _walk(definitions.get(name, {}), definitions, seen, out)
        for field_name, sub in (schema.get("properties") or {}).items():
            out.add(field_name)
            _walk(sub, definitions, seen, out)
        for key in ("items", "anyOf", "allOf", "oneOf", "additionalProperties"):
            _walk(schema.get(key), definitions, seen, out)
    elif isinstance(schema, list):
        for sub in schema:
            _walk(sub, definitions, seen, out)


@pytest.mark.invariant("INV-10")
def test_no_response_schema_exposes_secret_fields(app: FastAPI) -> None:
    """AC-X7 (schema part): response models are allow-lists without token/secret/hash fields."""
    spec = app.openapi()
    definitions = spec.get("components", {}).get("schemas", {})
    offenders: set[str] = set()
    for path, operations in spec["paths"].items():
        for operation in operations.values():
            for response in (operation.get("responses") or {}).values():
                content = (response.get("content") or {}).get("application/json", {})
                fields: set[str] = set()
                _walk(content.get("schema", {}), definitions, set(), fields)
                offenders |= {
                    f"{path}: {f}"
                    for f in fields
                    if SECRETISH.search(f) and f not in ALLOWED_SECRETISH_FIELDS
                }
    assert not offenders, f"secret-looking fields in response schemas: {sorted(offenders)}"


def test_openapi_is_served_outside_production(client: TestClient) -> None:
    assert client.get("/openapi.json").status_code == 200


@pytest.mark.invariant("INV-01")
def test_every_workspace_and_dev_route_requires_a_session(app: FastAPI, client: TestClient) -> None:
    """Without a session cookie every workspace-scoped and dev route answers 401 AUTH_REQUIRED
    (also the unsafe ones: authentication comes before the CSRF check). Covers the routes of
    every phase, content, media, reconnect, automation review and the simulator included."""
    protected = [
        (method, route.path)
        for route in iter_api_routes(app)
        if route.path.startswith(("/api/v1/workspaces/{", "/api/v1/dev/"))
        for method in sorted(route.methods)
    ]
    assert len(protected) >= 50, "route enumeration found too few routes: the harness is broken"
    failures = []
    for method, path in protected:
        url = PARAM.sub(lambda _m: str(uuid.uuid4()), path)
        response = client.request(method, url, json={} if method != "GET" else None)
        if response.status_code != 401 or response.json().get("code") != "AUTH_REQUIRED":
            failures.append(f"{method} {url} -> {response.status_code} {response.text[:80]}")
    assert not failures, "routes reachable without a session:\n" + "\n".join(failures)
