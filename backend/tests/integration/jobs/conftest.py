"""Helpers for the queue tests. They all use real commits (``@pytest.mark.commits``)."""

import uuid
from collections.abc import Callable, Iterator
from datetime import datetime

import pytest
from pydantic import BaseModel
from sqlalchemy.orm import Session, sessionmaker

from app.core.clock import FrozenClock
from app.jobs import queue
from app.jobs.models import Job
from app.jobs.registry import JobContext, job_handler, registry_snapshot
from app.jobs.scheduler import periodic_snapshot

pytestmark = pytest.mark.commits

SessionFactory = sessionmaker[Session]


class EchoPayload(BaseModel):
    item_id: uuid.UUID


@pytest.fixture(autouse=True)
def isolated_registries() -> Iterator[None]:
    """Handlers registered by a test disappear with it."""
    with registry_snapshot(), periodic_snapshot():
        yield


@pytest.fixture
def calls() -> list[JobContext]:
    return []


@pytest.fixture
def register_echo(calls: list[JobContext]) -> Callable[..., None]:
    """Register a ``test.echo`` handler that records its contexts, optionally via ``behaviour``."""

    def _register(
        behaviour: Callable[[JobContext], None] | None = None, **handler_options: object
    ) -> None:
        @job_handler("test.echo", EchoPayload, **handler_options)  # type: ignore[arg-type]
        def echo(ctx: JobContext) -> None:
            calls.append(ctx)
            if behaviour is not None:
                behaviour(ctx)

    return _register


def enqueue_committed(
    factory: SessionFactory,
    clock: FrozenClock,
    job_type: str = "test.echo",
    *,
    payload: BaseModel | None = None,
    run_at: datetime | None = None,
    dedup_key: str | None = None,
    priority: int = 100,
    max_attempts: int | None = None,
) -> uuid.UUID:
    with factory() as session:
        job_id = queue.enqueue(
            session,
            job_type,
            payload or EchoPayload(item_id=uuid.uuid4()),
            workspace_id=None,
            correlation_id=uuid.uuid4(),
            run_at=run_at,
            dedup_key=dedup_key,
            priority=priority,
            max_attempts=max_attempts,
            clock=clock,
        )
        session.commit()
    return job_id


def load_job(factory: SessionFactory, job_id: uuid.UUID) -> Job:
    with factory() as session:
        job = session.get(Job, job_id)
        assert job is not None
        return job
