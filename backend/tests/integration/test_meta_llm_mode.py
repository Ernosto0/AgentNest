"""``/meta`` tells the SPA whether the AI is the offline demo one (the status-strip indicator)."""

from collections.abc import Callable

from fastapi import FastAPI
from fastapi.testclient import TestClient


def _mode(app: FastAPI) -> str:
    with TestClient(app) as client:
        return str(client.get("/api/v1/meta").json()["llm_mode"])


def test_the_default_is_the_offline_demo_ai(build_app: Callable[..., FastAPI]) -> None:
    assert _mode(build_app()) == "fake"


def test_a_real_provider_is_reported_as_real_without_leaking_the_key(
    build_app: Callable[..., FastAPI],
) -> None:
    app = build_app(llm_provider="openai", openai_api_key="sk-secret-value")
    with TestClient(app) as client:
        response = client.get("/api/v1/meta")
    assert response.json()["llm_mode"] == "real"
    assert "sk-secret-value" not in response.text
