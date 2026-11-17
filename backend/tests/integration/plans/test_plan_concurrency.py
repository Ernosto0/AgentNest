"""Two workers drafting at once must not both slip past the limit or double-count."""

import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.clock import FrozenClock
from app.plans import service
from app.plans.models import ReplyUsage
from tests.factories import workspace_with_members

pytestmark = pytest.mark.commits


def make(factory: sessionmaker[Session], clock: FrozenClock, quota: int) -> uuid.UUID:
    with factory() as session:
        workspace, _ = workspace_with_members(session, roles=("owner", "manager"))
        row = service.get_plan(session, clock, workspace.id)
        row.period_start = clock.now()
        row.anchor_day = row.period_start.day
        row.period_end = service.next_month(row.period_start, row.anchor_day)
        row.quota_override = quota
        session.commit()
        return workspace.id


def used(factory: sessionmaker[Session], clock: FrozenClock, workspace_id: uuid.UUID) -> int:
    with factory() as session:
        value = service.get_plan(session, clock, workspace_id).used
        session.commit()
        return value


def test_parallel_consumers_stop_exactly_at_the_limit(
    session_factory: sessionmaker[Session], clock: FrozenClock
) -> None:
    workspace_id = make(session_factory, clock, quota=20)  # limit 22

    def one(i: int) -> bool:
        with session_factory() as session:
            admitted = service.consume(session, clock, workspace_id, f"draft-{i}")
            session.commit()
            return admitted

    with ThreadPoolExecutor(max_workers=12) as pool:
        results = list(pool.map(one, range(60)))
    assert sum(results) == 22
    assert used(session_factory, clock, workspace_id) == 22
    with session_factory() as session:
        consumed = session.scalar(
            select(func.count()).select_from(ReplyUsage).where(ReplyUsage.state == "consumed")
        )
    assert consumed == 22


def test_the_same_draft_from_many_workers_counts_once(
    session_factory: sessionmaker[Session], clock: FrozenClock
) -> None:
    workspace_id = make(session_factory, clock, quota=100)

    def one(_: int) -> bool:
        with session_factory() as session:
            admitted = service.consume(session, clock, workspace_id, "the-same-draft")
            session.commit()
            return admitted

    with ThreadPoolExecutor(max_workers=8) as pool:
        assert all(pool.map(one, range(24)))
    assert used(session_factory, clock, workspace_id) == 1


def test_reservations_made_in_parallel_cannot_exceed_the_limit(
    session_factory: sessionmaker[Session], clock: FrozenClock
) -> None:
    """The legacy job reserves, calls the model with no lock held, then finishes."""
    workspace_id = make(session_factory, clock, quota=10)  # limit 11

    def one(i: int) -> bool:
        with session_factory() as session:
            ticket = service.reserve(session, clock, workspace_id, f"job-{i}")
            ticket_id = ticket.id if ticket is not None else None
            session.commit()
        if ticket_id is None:
            return False
        with session_factory() as session:  # (the model call happens here, with nothing open)
            done = service.finish(session, clock, workspace_id, ticket_id, produced=True)
            session.commit()
            return done

    with ThreadPoolExecutor(max_workers=10) as pool:
        results = list(pool.map(one, range(40)))
    assert sum(results) == 11
    assert used(session_factory, clock, workspace_id) == 11


def test_warnings_are_sent_once_when_workers_cross_a_threshold_together(
    session_factory: sessionmaker[Session], clock: FrozenClock
) -> None:
    from app.notifications.models import Notification

    workspace_id = make(session_factory, clock, quota=10)

    def one(i: int) -> None:
        with session_factory() as session:
            service.consume(session, clock, workspace_id, f"draft-{i}")
            session.commit()

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(one, range(30)))
    with session_factory() as session:
        types = [n.type for n in session.scalars(select(Notification))]
    # two recipients (owner, manager) each get exactly one of each kind
    assert sorted(types) == ["quota.grace"] * 2 + ["quota.paused"] * 2 + ["quota.warning"] * 2
