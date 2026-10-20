"""AC-F4 on real commits: a worker killed right after the container id was committed (T2) (INV-06).

``test_publish_reconcile`` proves the same flow inside the test transaction. This one uses
``@pytest.mark.commits``: nothing is shared with the "dead" worker except what it really
committed, and every check reads through a **new connection**, as the next worker would.
"""

from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.content.models import ContentItem
from app.core.clock import FrozenClock
from app.core.config import Settings
from app.integrations.instagram.models import SimContainer, SimPublishedMedia
from app.jobs.queue import enqueue
from app.operations.models import Operation
from app.operations.payloads import ReconcileStuckPayload
from tests.helpers.publishing import Crash, Publishing, committing_publishing

pytestmark = [pytest.mark.commits, pytest.mark.invariant("INV-06")]


@pytest.fixture
def pub(
    session_factory: sessionmaker[Session],
    clock: FrozenClock,
    settings: Settings,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[Publishing]:
    harness = committing_publishing(session_factory, clock, settings, tmp_path / "media")
    monkeypatch.setattr("app.operations.jobs.get_settings", lambda: harness.settings)
    yield harness
    harness.session.close()  # an open transaction would block the table truncation


def fresh_state(
    factory: sessionmaker[Session], item_id: object
) -> tuple[ContentItem, Operation | None, list[SimContainer], list[SimPublishedMedia]]:
    """What a new worker would see: read through a brand-new session."""
    with factory() as session:
        item = session.get(ContentItem, item_id)
        assert item is not None
        op = session.scalars(select(Operation)).one_or_none()
        containers = list(session.scalars(select(SimContainer)))
        posts = list(session.scalars(select(SimPublishedMedia)))
        session.expunge_all()
    return item, op, containers, posts


def sweep(pub: Publishing) -> None:
    enqueue(
        pub.session,
        "reconcile_stuck_operations",
        ReconcileStuckPayload(),
        workspace_id=None,
        correlation_id=None,
        clock=pub.clock,
    )
    pub.session.commit()
    pub.process()


def test_ac_f4_commits_a_crash_right_after_the_container_commit_publishes_once_with_the_stored_id(
    pub: Publishing, session_factory: sessionmaker[Session]
) -> None:
    item = pub.scheduled()
    item_id = item.id

    def kill() -> None:
        raise Crash  # the worker dies on its first look at the container

    pub.before["get_container_status"] = kill
    with pytest.raises(Crash):
        pub.execute(item)

    # Only what was committed is left: T1 (operation in_progress) and T2 (the container id).
    row, op, containers, posts = fresh_state(session_factory, item_id)
    (container,) = containers
    assert row.status == "publishing" and posts == []
    assert op is not None and op.status == "in_progress"
    assert op.provider_ref.get("container_id") == container.container_id

    # A re-run of the job never starts a second attempt or a second container.
    pub.calls.clear()
    assert pub.execute(item).detail == "not_due:publishing"
    assert "create_media_container" not in pub.calls

    # The stuck sweep hands the operation to reconciliation, which reads the stored container:
    # FINISHED proves it was never published, so it is published now.
    pub.clock.advance(minutes=16)
    sweep(pub)
    _, op, _, _ = fresh_state(session_factory, item_id)
    assert op is not None and op.status == "outcome_unknown"
    pub.clock.advance(minutes=1)
    pub.process()

    row, op, containers, posts = fresh_state(session_factory, item_id)
    (post,) = posts  # exactly one publication
    assert row.status == "published" and op is not None and op.status == "succeeded"
    assert post.container_id == container.container_id  # the stored id ...
    assert len(containers) == 1  # ... and no second container
    assert op.attempts == 2
