"""``promotion_expiry_notices`` (plan H18): every expiry is announced once, per workspace at its
own 09:00, to the ``knowledge.verify`` holders; nothing in the data changes.

A promotion whose ``valid_until`` is the day ``D`` is usable through all of ``D`` and unusable
from the first local second of ``D + 1``; the run of local day ``D + 1`` announces it.
"""

from datetime import UTC, date, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.core.clock import FrozenClock
from app.core.context import ActorRef
from app.identity import service as identity_service
from app.identity.models import User, Workspace
from app.jobs.models import Job
from app.jobs.testing import run_due_jobs
from app.knowledge import promotion_notices
from app.knowledge.models import BusinessFact
from app.notifications import catalog
from app.notifications.models import Notification
from tests.factories import add_member, create_fact, create_user, create_workspace, money

SessionFactory = sessionmaker[Session]
TYPE = "knowledge.promotion_expired"


def utc(year: int, month: int, day: int, hour: int = 0, minute: int = 0) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=UTC)


class Studio:
    def __init__(self, session: Session) -> None:
        self.session = session

    def workspace(self, timezone: str, name: str) -> tuple[Workspace, dict[str, User]]:
        workspace = create_workspace(self.session, timezone=timezone, name=name)
        users: dict[str, User] = {}
        for role in ("owner", "manager", "staff"):
            users[role] = create_user(self.session, display_name=f"{name} {role}")
            add_member(self.session, workspace, users[role], role)
        self.session.commit()
        return workspace, users

    def promo(
        self,
        workspace: Workspace,
        slug: str,
        valid_until: date | None,
        *,
        verified: bool = True,
    ) -> BusinessFact:
        fact = create_fact(
            self.session,
            workspace,
            f"promotion.{slug}",
            {"tr": f"{slug} kampanyası", "en": f"{slug} offer"},
            verified=verified,
            value_type="localized_text",
            label={"tr": slug, "en": slug},
            valid_until=valid_until,
        )
        self.session.commit()
        return fact

    def notifications(self, workspace: Workspace | None = None) -> list[Notification]:
        self.session.expire_all()
        statement = select(Notification).where(Notification.type == TYPE)
        if workspace is not None:
            statement = statement.where(Notification.workspace_id == workspace.id)
        return list(self.session.scalars(statement.order_by(Notification.created_at)))


@pytest.fixture
def studio(db_session: Session) -> Studio:
    return Studio(db_session)


def tick(session: Session, at: datetime) -> int:
    count = promotion_notices.enqueue_promotion_expiry_notices(session, FrozenClock(at))
    session.commit()
    return count


def jobs(session: Session) -> list[Job]:
    return list(session.scalars(select(Job).where(Job.job_type == "promotion_expiry_notices")))


def test_the_expiry_is_announced_to_the_verifiers_once(
    studio: Studio, db_session: Session, shared_session_factory: SessionFactory
) -> None:
    workspace, users = studio.workspace("Europe/Istanbul", "Istanbul")
    ended = studio.promo(workspace, "spring", date(2026, 10, 20))
    studio.promo(workspace, "still_on", date(2026, 10, 21))  # valid through today
    studio.promo(workspace, "long_ago", date(2026, 10, 1))  # announced by an earlier run
    studio.promo(workspace, "open_ended", None)
    studio.promo(workspace, "draft_offer", date(2026, 10, 20), verified=False)
    create_fact(  # not a promotion: an ended validity window is not announced
        db_session,
        workspace,
        "pricing.single_session",
        money("300"),
        valid_until=date(2026, 10, 20),
    )
    db_session.commit()
    before_values = {
        f.key: (f.status, f.valid_until, f.current_version) for f in _facts(db_session)
    }

    # 2026-10-21 09:00 in Istanbul (UTC+3) is 06:00 UTC.
    assert tick(db_session, utc(2026, 10, 21, 5, 59)) == 0
    assert tick(db_session, utc(2026, 10, 21, 6, 0)) == 1
    [job] = jobs(db_session)
    assert job.dedup_key == f"promo_expiry:{workspace.id}:2026-10-21"
    assert job.workspace_id == workspace.id
    assert job.payload == {"workspace_id": str(workspace.id), "local_date": "2026-10-21"}
    assert job.max_attempts == 1

    assert (
        run_due_jobs(FrozenClock(utc(2026, 10, 21, 6, 0)), session_factory=shared_session_factory)
        == 1
    )
    notes = studio.notifications()
    assert {n.recipient_user_id for n in notes} == {users["owner"].id, users["manager"].id}
    for note in notes:  # staff cannot verify facts: not told
        assert note.severity == "attention" and note.workspace_id == workspace.id
        assert note.subject_type == "business_fact" and note.subject_id == ended.id
        assert note.params["fact_key"] == "promotion.spring"
        assert note.params["valid_until"] == "2026-10-20"
        assert note.is_simulated is False
        assert note.dedup_key == f"promotion-expired:{ended.id}:2026-10-20"
        assert "kampanyası" not in str(note.params)  # the value is not copied, only the label

    # The rest of the day, and a repeated run, announce nothing more.
    for hour, minute in ((6, 1), (12, 0), (20, 59)):
        assert tick(db_session, utc(2026, 10, 21, hour, minute)) == 0
    run_due_jobs(FrozenClock(utc(2026, 10, 21, 7, 0)), session_factory=shared_session_factory)
    assert len(studio.notifications()) == 2

    # No data change (business-knowledge.md section 4).
    after_values = {f.key: (f.status, f.valid_until, f.current_version) for f in _facts(db_session)}
    assert after_values == before_values


def _facts(session: Session) -> list[BusinessFact]:
    session.expire_all()
    return list(session.scalars(select(BusinessFact)))


def test_the_next_day_announces_the_next_expiry_and_not_the_old_one_again(
    studio: Studio, db_session: Session, shared_session_factory: SessionFactory
) -> None:
    workspace, _ = studio.workspace("Europe/Istanbul", "Istanbul")
    studio.promo(workspace, "monday", date(2026, 10, 19))
    studio.promo(workspace, "tuesday", date(2026, 10, 20))
    for day in (20, 21, 22):
        at = utc(2026, 10, day, 6, 0)
        assert tick(db_session, at) == 1
        run_due_jobs(FrozenClock(at), session_factory=shared_session_factory)
    # Once each (to the owner and the manager), and always on the day after the last valid day.
    announced = [(n.params["fact_key"], n.created_at) for n in studio.notifications()]
    assert sorted(announced) == [
        ("promotion.monday", utc(2026, 10, 20, 6, 0)),
        ("promotion.monday", utc(2026, 10, 20, 6, 0)),
        ("promotion.tuesday", utc(2026, 10, 21, 6, 0)),
        ("promotion.tuesday", utc(2026, 10, 21, 6, 0)),
    ]


def test_each_workspace_is_served_at_its_own_9_in_the_morning(
    studio: Studio, db_session: Session, shared_session_factory: SessionFactory
) -> None:
    """Istanbul is UTC+3, Lisbon UTC+1 on 2026-10-21 (summer time ends on the 25th)."""
    istanbul, ist_users = studio.workspace("Europe/Istanbul", "Istanbul")
    lisbon, lis_users = studio.workspace("Europe/Lisbon", "Lisbon")
    ist_promo = studio.promo(istanbul, "ist", date(2026, 10, 20))
    lis_promo = studio.promo(lisbon, "lis", date(2026, 10, 20))

    assert tick(db_session, utc(2026, 10, 21, 5, 59)) == 0
    assert tick(db_session, utc(2026, 10, 21, 6, 0)) == 1  # 09:00 in Istanbul, 07:00 in Lisbon
    assert {j.workspace_id for j in jobs(db_session)} == {istanbul.id}
    run_due_jobs(FrozenClock(utc(2026, 10, 21, 6, 0)), session_factory=shared_session_factory)
    assert studio.notifications(lisbon) == []

    assert tick(db_session, utc(2026, 10, 21, 7, 59)) == 0
    assert tick(db_session, utc(2026, 10, 21, 8, 0)) == 1  # 09:00 in Lisbon
    run_due_jobs(FrozenClock(utc(2026, 10, 21, 8, 0)), session_factory=shared_session_factory)

    # Isolation: each workspace's members hear about their own promotion only.
    ist_notes, lis_notes = studio.notifications(istanbul), studio.notifications(lisbon)
    assert {n.subject_id for n in ist_notes} == {ist_promo.id}
    assert {n.subject_id for n in lis_notes} == {lis_promo.id}
    assert {n.recipient_user_id for n in ist_notes} == {
        ist_users["owner"].id,
        ist_users["manager"].id,
    }
    assert {n.recipient_user_id for n in lis_notes} == {
        lis_users["owner"].id,
        lis_users["manager"].id,
    }


def test_the_lisbon_day_boundary_follows_summer_time(
    studio: Studio, db_session: Session, shared_session_factory: SessionFactory
) -> None:
    """On 2026-10-25 Lisbon moves back to UTC+0, so 09:00 local is 09:00 UTC from then on."""
    lisbon, _ = studio.workspace("Europe/Lisbon", "Lisbon")
    studio.promo(lisbon, "weekend", date(2026, 10, 25))
    assert tick(db_session, utc(2026, 10, 26, 8, 59)) == 0  # 08:59 local (UTC+0)
    assert tick(db_session, utc(2026, 10, 26, 9, 0)) == 1
    run_due_jobs(FrozenClock(utc(2026, 10, 26, 9, 0)), session_factory=shared_session_factory)
    assert len(studio.notifications(lisbon)) == 2  # the owner and the manager


def test_a_workspace_that_is_not_active_gets_no_job_and_no_notice(
    studio: Studio, db_session: Session, shared_session_factory: SessionFactory
) -> None:
    workspace, _ = studio.workspace("Europe/Istanbul", "Istanbul")
    studio.promo(workspace, "spring", date(2026, 10, 20))
    workspace.status = "deleting"
    db_session.commit()
    assert tick(db_session, utc(2026, 10, 21, 6, 0)) == 0

    # A job that was queued before the suspension does nothing either.
    workspace.status = "active"
    db_session.commit()
    tick(db_session, utc(2026, 10, 21, 6, 0))
    workspace.status = "deleting"
    db_session.commit()
    run_due_jobs(FrozenClock(utc(2026, 10, 21, 6, 0)), session_factory=shared_session_factory)
    assert studio.notifications() == []


def test_a_dead_job_is_not_replaced_the_same_day(studio: Studio, db_session: Session) -> None:
    studio.workspace("Europe/Istanbul", "Istanbul")
    tick(db_session, utc(2026, 10, 21, 6, 0))
    [job] = jobs(db_session)
    job.status = "dead"
    db_session.commit()
    assert tick(db_session, utc(2026, 10, 21, 6, 5)) == 0
    assert len(jobs(db_session)) == 1


def test_an_unread_notice_for_the_same_expiry_is_never_doubled(
    studio: Studio, db_session: Session
) -> None:
    workspace, _ = studio.workspace("Europe/Istanbul", "Istanbul")
    studio.promo(workspace, "spring", date(2026, 10, 20))
    ctx = identity_service.workspace_context(workspace, ActorRef.system("test"), None)
    clock = FrozenClock(utc(2026, 10, 21, 6, 0))
    first = promotion_notices.announce_expired(db_session, clock, ctx, date(2026, 10, 21))
    again = promotion_notices.announce_expired(db_session, clock, ctx, date(2026, 10, 21))
    db_session.commit()
    assert len(first) == len(again) == 1  # the facts are found again ...
    assert len(studio.notifications()) == 2  # ... but the unread notices are not repeated


def test_the_type_is_in_the_catalog_with_its_severity() -> None:
    spec = catalog.CATALOG[TYPE]
    assert spec.severity == "attention" and spec.recipients == "knowledge.verify"
