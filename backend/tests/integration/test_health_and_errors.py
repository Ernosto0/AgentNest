import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel

from app.api.deps import get_app_settings
from app.core.config import Settings
from app.core.errors import AppError


class Body(BaseModel):
    name: str
    count: int


@pytest.fixture
def probe_app(app: FastAPI) -> FastAPI:
    """The shared app plus throw-away routes that exercise the error handlers."""

    @app.post("/_probe/validate")
    def validate(body: Body) -> dict[str, str]:
        return {"name": body.name}

    @app.get("/_probe/app-error")
    def app_error() -> None:
        raise AppError("FORBIDDEN", permission="members.manage")

    @app.get("/_probe/boom")
    def boom() -> None:
        raise RuntimeError("secret internal detail")

    return app


def test_healthz_is_ok(client: TestClient) -> None:
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_readyz_reports_database_and_migrations(client: TestClient, engine: object) -> None:
    response = client.get("/readyz")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "checks": {"database": True, "migrations": True},
    }


def test_readyz_fails_when_migrations_are_not_at_head(
    client: TestClient, engine: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("app.core.db.migration_head", lambda: "not-the-head")
    response = client.get("/readyz")
    assert response.status_code == 503
    assert response.json()["checks"] == {"database": True, "migrations": False}


def test_meta_exposes_only_public_configuration(client: TestClient) -> None:
    response = client.get("/api/v1/meta")
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {
        "product_name",
        "demo_tools_enabled",
        "llm_mode",
        "supported_locales",
        "instagram_providers",
        "mock_requires_demo_workspace",
    }
    assert body["supported_locales"] == ["tr", "en"]
    assert body["llm_mode"] == "fake"
    assert body["instagram_providers"] == ["mock"]
    assert body["mock_requires_demo_workspace"] is False


@pytest.mark.parametrize(
    ("app_env", "providers", "tools", "expected"),
    [
        ("development", "mock", False, ["mock"]),
        ("production", "mock", False, ["mock"]),
        ("test", "meta,mock", True, ["mock", "meta"]),
        ("test", "meta", False, ["meta"]),
    ],
)
def test_meta_reports_backend_provider_policy(
    app: FastAPI,
    client: TestClient,
    settings: Settings,
    app_env: str,
    providers: str,
    tools: bool,
    expected: list[str],
) -> None:
    # Already-validated settings copied to probe the public projection without live credentials.
    candidate = settings.model_copy(
        update={
            "app_env": app_env,
            "instagram_enabled_providers": providers,
            "demo_tools_enabled": tools,
        }
    )
    app.dependency_overrides[get_app_settings] = lambda: candidate
    response = client.get("/api/v1/meta")
    assert response.status_code == 200
    body = response.json()
    assert body["instagram_providers"] == expected
    assert body["mock_requires_demo_workspace"] is (app_env == "production")
    assert body["demo_tools_enabled"] is tools
    # The route is public, deterministic and carries no credentials or endpoints.
    assert body == client.get("/api/v1/meta").json()


def test_oauth_callback_openapi_declares_redirect(app: FastAPI) -> None:
    responses = app.openapi()["paths"]["/oauth/instagram/callback"]["get"]["responses"]
    assert "303" in responses
    assert "200" not in responses
    assert "content" not in responses["303"]


def test_unknown_route_is_problem_json_404(client: TestClient) -> None:
    response = client.get("/api/v1/nope", headers={"Accept-Language": "en"})
    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/problem+json")
    body = response.json()
    assert body["type"] == "about:blank"
    assert body["status"] == 404
    assert body["code"] == "NOT_FOUND"
    assert body["detail"] == "We could not find what you were looking for."
    assert body["request_id"] == response.headers["x-request-id"]


def test_detail_is_localised_from_accept_language(client: TestClient) -> None:
    turkish = client.get("/api/v1/nope", headers={"Accept-Language": "tr-TR,tr;q=0.9"}).json()
    assert turkish["detail"].startswith("Aradığınız")
    fallback = client.get("/api/v1/nope", headers={"Accept-Language": "de"}).json()
    assert fallback["detail"] == turkish["detail"]


def test_app_error_becomes_problem_json_with_params(probe_app: FastAPI) -> None:
    response = TestClient(probe_app).get("/_probe/app-error")
    assert response.status_code == 403
    body = response.json()
    assert body["code"] == "FORBIDDEN"
    assert body["params"] == {"permission": "members.manage"}


def test_validation_errors_are_422_with_field_list(probe_app: FastAPI) -> None:
    response = TestClient(probe_app).post("/_probe/validate", json={"count": "x"})
    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "VALIDATION_FAILED"
    fields = {e["field"]: e["code"] for e in body["errors"]}
    assert fields["name"] == "required"
    assert "count" in fields
    assert all(set(e) == {"field", "code", "params"} for e in body["errors"])


def test_unhandled_exception_is_500_without_leaking_details(probe_app: FastAPI) -> None:
    response = TestClient(probe_app, raise_server_exceptions=False).get("/_probe/boom")
    assert response.status_code == 500
    body = response.json()
    assert body["code"] == "INTERNAL_ERROR"
    assert "secret internal detail" not in response.text
    assert body["request_id"]


def test_incoming_request_id_is_kept_and_echoed(client: TestClient) -> None:
    response = client.get("/healthz", headers={"X-Request-ID": "trace-abc_123"})
    assert response.headers["x-request-id"] == "trace-abc_123"


def test_malformed_request_id_is_replaced(client: TestClient) -> None:
    response = client.get("/healthz", headers={"X-Request-ID": "bad id\twith spaces"})
    assert response.headers["x-request-id"] != "bad id\twith spaces"
    assert len(response.headers["x-request-id"]) == 32


def test_cors_allows_only_the_frontend_origin(client: TestClient) -> None:
    allowed = client.options(
        "/api/v1/meta",
        headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "GET"},
    )
    assert allowed.headers.get("access-control-allow-origin") == "http://localhost:5173"
    assert allowed.headers.get("access-control-allow-credentials") == "true"
    denied = client.options(
        "/api/v1/meta",
        headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "GET"},
    )
    assert "access-control-allow-origin" not in denied.headers
