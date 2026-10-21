"""Fixtures of the demo seed, history and reset tests (P6-07)."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.core.clock import FrozenClock
from app.core.config import Settings
from app.demo.seed import seed
from app.main import create_app
from tests.helpers.demo import PASSWORD, SessionFactory


@pytest.fixture
def seed_settings(settings: Settings, tmp_path: Path) -> Settings:
    return settings.model_copy(
        update={
            "demo_password": SecretStr(PASSWORD),
            "media_local_root": str(tmp_path / "media"),
        }
    )


@pytest.fixture
def seeded(
    session_factory: SessionFactory, clock: FrozenClock, seed_settings: Settings
) -> SessionFactory:
    seed(session_factory, clock, seed_settings)
    return session_factory


@pytest.fixture
def client(seed_settings: Settings, clock: FrozenClock, seeded: SessionFactory) -> TestClient:
    return TestClient(create_app(seed_settings, clock))
