"""Fixtures for the approvals tests: a workspace env and a controllable approval subject."""

import uuid
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.approvals import callbacks
from app.approvals.models import Approval
from app.core.clock import FrozenClock
from app.core.context import WorkspaceContext
from tests.helpers.env import Env, build_env


@pytest.fixture
def env(db_session: Session, make_client: Callable[[], TestClient], clock: FrozenClock) -> Env:
    return build_env(db_session, make_client, clock)


@dataclass
class FakeSubject:
    """What a subject module provides: a version, a status and a decided-callback."""

    version: int = 1
    status: str = "awaiting"
    decided: list[tuple[str, uuid.UUID]] = field(default_factory=list)
    fail: bool = False

    def on_decided(
        self, session: Session, clock: FrozenClock, ctx: WorkspaceContext, approval: Approval
    ) -> None:
        self.decided.append((approval.status, approval.id))
        self.status = approval.status
        if self.fail:
            raise RuntimeError("callback failed")


@pytest.fixture
def subject() -> Iterator[FakeSubject]:
    """Register a throw-away handler for the ``owner_command`` subject type."""
    fake = FakeSubject()
    with callbacks.callbacks_snapshot(clear=True):
        callbacks.register(
            "owner_command",
            fake.on_decided,  # type: ignore[arg-type]
            current_version=lambda _s, _c, _i: fake.version,
            status_of=lambda _s, _c, _i: fake.status,
        )
        yield fake
