"""AC-F5: the same publish running twice at once yields one publication (INV-06).

Real commits and real threads: the item's row lock (T1) and the operation key decide, not luck.
"""

import threading
from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.content.models import ContentItem
from app.core.clock import FrozenClock
from app.core.config import Settings
from app.integrations.instagram.models import SimContainer, SimPublishedMedia
from app.jobs.testing import run_due_jobs
from app.operations import publish
from tests.factories import workspace_with_members
from tests.helpers.publishing import Publishing

pytestmark = pytest.mark.commits


def build(
    factory: sessionmaker[Session], clock: FrozenClock, settings: Settings, tmp_path: Path
) -> tuple[Publishing, Session]:
    session = factory()
    workspace, users = workspace_with_members(session, roles=("owner",))
    session.commit()
    cfg = settings.model_copy(
        update={"media_local_root": str(tmp_path / "media"), "sim_container_delay_seconds": 0}
    )
    return Publishing(session, factory, clock, cfg, workspace, users["owner"]), session


def count(factory: sessionmaker[Session], model: type) -> int:
    with factory() as session:
        return session.scalar(select(func.count()).select_from(model)) or 0


def race(
    factory: sessionmaker[Session], clock: FrozenClock, pub: Publishing, item: ContentItem
) -> list[publish.PublishOutcome]:
    """Two threads execute the same publish at the same instant."""
    barrier = threading.Barrier(2)
    outcomes: list[publish.PublishOutcome] = []

    def run() -> None:
        barrier.wait()
        outcomes.append(
            publish.execute_publish(
                factory,
                clock,
                pub.settings,
                pub.workspace.id,
                item.id,
                item.version,
                sleep=lambda _: None,
            )
        )

    threads = [threading.Thread(target=run) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return outcomes


def test_ac_f5_the_same_publish_executed_by_two_threads_publishes_once(
    session_factory: sessionmaker[Session],
    clock: FrozenClock,
    settings: Settings,
    tmp_path: Path,
) -> None:
    for round_number in range(5):  # a race that passes once proves little
        pub, session = build(session_factory, clock, settings, tmp_path)
        item = pub.scheduled()
        outcomes = race(session_factory, clock, pub, item)
        session.close()

        kinds = sorted(o.kind for o in outcomes)
        assert kinds == ["published", "skipped"], f"round {round_number}: {outcomes}"
        assert count(session_factory, SimPublishedMedia) == round_number + 1
        assert count(session_factory, SimContainer) == round_number + 1  # one container per item


def test_ac_f5_two_workers_running_due_jobs_publish_once(
    session_factory: sessionmaker[Session],
    clock: FrozenClock,
    settings: Settings,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pub, session = build(session_factory, clock, settings, tmp_path)
    monkeypatch.setattr("app.operations.jobs.get_settings", lambda: pub.settings)
    item = pub.scheduled()
    session.close()

    threads = [
        threading.Thread(
            target=run_due_jobs, args=(clock,), kwargs={"session_factory": session_factory}
        )
        for _ in range(4)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert count(session_factory, SimPublishedMedia) == 1
    with session_factory() as check:
        assert check.get(ContentItem, item.id).status == "published"  # type: ignore[union-attr]
