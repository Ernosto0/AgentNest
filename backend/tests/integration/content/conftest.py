"""Fixtures for the content integration tests: an app whose media root is a temp folder."""

from collections.abc import Callable
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.core.clock import FrozenClock
from app.core.config import Settings
from tests.helpers.env import Env, build_env
from tests.helpers.publishing import Publishing


@pytest.fixture
def media_root(tmp_path: Path) -> Path:
    return tmp_path / "media"


@pytest.fixture
def app(build_app: Callable[..., FastAPI], media_root: Path) -> FastAPI:
    return build_app(media_local_root=str(media_root))


@pytest.fixture
def env(db_session: Session, make_client: Callable[[], TestClient], clock: FrozenClock) -> Env:
    return build_env(db_session, make_client, clock)


@pytest.fixture
def make_pub(
    env: Env,
    shared_session_factory: sessionmaker[Session],
    settings: Settings,
    media_root: Path,
    clock: FrozenClock,
    monkeypatch: pytest.MonkeyPatch,
) -> Callable[..., Publishing]:
    """Build the publish harness; keyword arguments override settings. By default containers
    finish at once (``sim_container_delay_seconds=0``), so a job run never has to sleep."""

    def _make(**overrides: object) -> Publishing:
        values: dict[str, object] = {
            "media_local_root": str(media_root),
            "sim_container_delay_seconds": 0,
            **overrides,
        }
        cfg = settings.model_copy(update=values)
        monkeypatch.setattr("app.operations.jobs.get_settings", lambda: cfg)
        return Publishing(
            env.session, shared_session_factory, clock, cfg, env.workspace, env.owner.user
        )

    return _make


@pytest.fixture
def pub(make_pub: Callable[..., Publishing]) -> Publishing:
    return make_pub()
