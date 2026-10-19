"""Fixtures for the policy integration tests."""

from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.clock import FrozenClock
from tests.helpers.env import Env, build_env


@pytest.fixture
def env(db_session: Session, make_client: Callable[[], TestClient], clock: FrozenClock) -> Env:
    return build_env(db_session, make_client, clock)
