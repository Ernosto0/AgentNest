"""Fixtures for the content integration tests: an app whose media root is a temp folder."""

from collections.abc import Callable
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.clock import FrozenClock
from tests.helpers.env import Env, build_env


@pytest.fixture
def media_root(tmp_path: Path) -> Path:
    return tmp_path / "media"


@pytest.fixture
def app(build_app: Callable[..., FastAPI], media_root: Path) -> FastAPI:
    return build_app(media_local_root=str(media_root))


@pytest.fixture
def env(db_session: Session, make_client: Callable[[], TestClient], clock: FrozenClock) -> Env:
    return build_env(db_session, make_client, clock)
