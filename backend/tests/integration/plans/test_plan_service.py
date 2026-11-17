"""The monthly AI reply allowance (P-11): the counter, the thresholds, the warnings, the periods."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.clock import FrozenClock
from app.identity.models import User, Workspace
from app.notifications.models import Notification
from app.plans import service
from app.plans.models import ReplyUsage, WorkspacePlan
from app.plans.tiers import TIERS
from tests.factories import workspace_with_members


def make_workspace(
    db: Session, clock: FrozenClock, *, quota: int | None = None
) -> tuple[Workspace, dict[str, User]]:
    """A workspace with an owner, a manager and a staff member; its period starts at the
    frozen clock's now, so the tests do not depend on the real date."""
    workspace, users = workspace_with_members(db, roles=("owner", "manager", "staff"))
    row = service.get_plan(db, clock, workspace.id)
    row.period_start = clock.now()
    row.anchor_day = row.period_start.day
    row.period_end = service.next_month(row.period_start, row.anchor_day)
    row.quota_override = quota
    db.flush()
    return workspace, users


def quota_notifications(db: Session, kind: str | None = None) -> list[Notification]:
    db.expire_all()
    statement = select(Notification).where(Notification.type.like("quota.%"))
    if kind is not None:
        statement = statement.where(Notification.type == kind)
    return list(db.scalars(statement))


def spend(
    db: Session, clock: FrozenClock, workspace_id: uuid.UUID, n: int, prefix: str = "k"
) -> int:
    """Consume ``n`` distinct drafts; how many were admitted."""
    return sum(
        service.consume(db, clock, workspace_id, f"{prefix}-{i}-{uuid.uuid4().hex[:6]}")
        for i in range(n)
    )


# --- the tier table and the default ------------------------------------------------------------


def test_the_tier_table_is_the_pricing_documents() -> None:
    assert TIERS == {"starter": 500, "growth": 2500, "pro": 7500}


def test_a_workspace_starts_on_growth_trial_at_its_creation(
    db_session: Session, clock: FrozenClock
) -> None:
    workspace, _ = workspace_with_members(db_session)
    row = service.get_plan(db_session, clock, workspace.id)
    assert (row.plan, row.monthly_quota, row.status, row.quota_override, row.used) == (
        "growth",
        2500,
        "trial",
        None,
        0,
    )
    assert row.period_start == workspace.created_at
    assert row.period_end == service.next_month(workspace.created_at, workspace.created_at.day)
    # asking again changes nothing (one row, one period)
    assert service.get_plan(db_session, clock, workspace.id).period_id == row.period_id
    assert db_session.scalar(select(func.count()).select_from(WorkspacePlan)) == 1


@pytest.mark.parametrize(
    ("quota", "warning_at", "grace_at", "paused_at"),
    [(500, 400, 500, 550), (2500, 2000, 2500, 2750), (7500, 6000, 7500, 8250), (5, 4, 5, 6)],
)
def test_the_thresholds(quota: int, warning_at: int, grace_at: int, paused_at: int) -> None:
    row = WorkspacePlan(plan="growth", monthly_quota=quota, quota_override=None, used=0)
    assert service.limit(row) == paused_at  # the quota plus 10%, and at least one more
    for used, expected in (
        (0, "normal"),
        (warning_at - 1, "normal"),
        (warning_at, "warning"),
        (grace_at - 1, "warning"),
        (grace_at, "grace"),
        (paused_at - 1, "grace"),
        (paused_at, "paused"),
        (paused_at + 40, "paused"),
    ):
        row.used = used
        assert service.state(row) == expected, (quota, used)


def test_an_override_replaces_the_plan_quota() -> None:
    row = WorkspacePlan(plan="starter", monthly_quota=500, quota_override=1000, used=999)
    assert (service.quota(row), service.limit(row), service.state(row)) == (1000, 1100, "warning")


# --- counting ----------------------------------------------------------------------------------


def test_each_draft_counts_once_whatever_happens_to_it_afterwards(
    db_session: Session, clock: FrozenClock
) -> None:
    workspace, _ = make_workspace(db_session, clock, quota=100)
    assert service.consume(db_session, clock, workspace.id, "draft-a")
    assert service.consume(db_session, clock, workspace.id, "draft-b")
    # a replayed job or action is the same draft
    assert service.consume(db_session, clock, workspace.id, "draft-a")
    assert service.get_plan(db_session, clock, workspace.id).used == 2
    assert db_session.scalar(select(func.count()).select_from(ReplyUsage)) == 2


def test_a_run_without_a_draft_costs_nothing(db_session: Session, clock: FrozenClock) -> None:
    workspace, _ = make_workspace(db_session, clock, quota=100)
    ticket = service.reserve(db_session, clock, workspace.id, "no-text")
    assert ticket is not None
    assert service.finish(db_session, clock, workspace.id, ticket.id, produced=False)
    row = service.get_plan(db_session, clock, workspace.id)
    assert row.used == 0 and ticket.state == "released"
    # and the same key can be tried again later
    again = service.reserve(db_session, clock, workspace.id, "no-text")
    assert again is not None
    assert service.finish(db_session, clock, workspace.id, again.id, produced=True)
    assert service.get_plan(db_session, clock, workspace.id).used == 1


def test_a_reservation_holds_a_slot_until_it_is_finished_or_lapses(
    db_session: Session, clock: FrozenClock
) -> None:
    workspace, _ = make_workspace(db_session, clock, quota=10)  # limit 11
    spend(db_session, clock, workspace.id, 10)
    held = service.reserve(db_session, clock, workspace.id, "held")
    assert held is not None  # the 11th slot
    assert service.reserve(db_session, clock, workspace.id, "other") is None  # nothing is left
    # the same job asking again keeps its slot
    assert service.reserve(db_session, clock, workspace.id, "held") is held
    clock.advance(minutes=6)  # the worker died: the slot lapses
    assert service.reserve(db_session, clock, workspace.id, "other") is not None
    # a late worker cannot consume a lapsed slot
    assert service.finish(db_session, clock, workspace.id, held.id, produced=True) is False
    assert service.get_plan(db_session, clock, workspace.id).used == 10


def test_nothing_is_admitted_after_the_grace_is_used(
    db_session: Session, clock: FrozenClock
) -> None:
    workspace, _ = make_workspace(db_session, clock, quota=100)  # limit 110
    assert spend(db_session, clock, workspace.id, 120) == 110
    row = service.get_plan(db_session, clock, workspace.id)
    assert row.used == 110 and service.state(row) == "paused"
    assert service.is_paused(db_session, clock, workspace.id)


def test_a_larger_quota_or_a_new_period_resumes_drafting(
    db_session: Session, clock: FrozenClock
) -> None:
    workspace, _ = make_workspace(db_session, clock, quota=100)
    spend(db_session, clock, workspace.id, 110)
    assert service.is_paused(db_session, clock, workspace.id)
    row = service.get_plan(db_session, clock, workspace.id)
    row.quota_override = 200  # the operator changed the plan
    assert not service.is_paused(db_session, clock, workspace.id)
    assert service.consume(db_session, clock, workspace.id, "after-upgrade")
    row.quota_override = 100
    assert service.is_paused(db_session, clock, workspace.id)
    clock.advance(days=32)  # the next period
    assert not service.is_paused(db_session, clock, workspace.id)
    assert service.get_plan(db_session, clock, workspace.id).used == 0


# --- warnings ----------------------------------------------------------------------------------


def test_the_warnings_fire_once_per_period_to_owner_and_manager(
    db_session: Session, clock: FrozenClock
) -> None:
    workspace, users = make_workspace(db_session, clock, quota=100)
    owner_manager = {users["owner"].id, users["manager"].id}

    spend(db_session, clock, workspace.id, 79)
    assert quota_notifications(db_session) == []
    spend(db_session, clock, workspace.id, 1)  # 80
    warning = quota_notifications(db_session, "quota.warning")
    assert {n.recipient_user_id for n in warning} == owner_manager  # not staff
    spend(db_session, clock, workspace.id, 19)  # 99: still only the first
    assert len(quota_notifications(db_session)) == 2
    spend(db_session, clock, workspace.id, 1)  # 100
    assert len(quota_notifications(db_session, "quota.grace")) == 2
    spend(db_session, clock, workspace.id, 9)  # 109
    assert quota_notifications(db_session, "quota.paused") == []
    spend(db_session, clock, workspace.id, 1)  # 110
    assert len(quota_notifications(db_session, "quota.paused")) == 2
    # more attempts and more reads send nothing new, even once the owner has read them all
    for notification in quota_notifications(db_session):
        notification.read_at = clock.now()
    db_session.flush()
    spend(db_session, clock, workspace.id, 5)
    service.get_plan(db_session, clock, workspace.id)
    service.reserve(db_session, clock, workspace.id, "refused")
    assert len(quota_notifications(db_session)) == 6


def test_the_warnings_come_back_in_the_next_period(db_session: Session, clock: FrozenClock) -> None:
    workspace, _ = make_workspace(db_session, clock, quota=10)
    spend(db_session, clock, workspace.id, 8)
    assert len(quota_notifications(db_session, "quota.warning")) == 2
    clock.advance(days=31)
    spend(db_session, clock, workspace.id, 8)
    assert len(quota_notifications(db_session, "quota.warning")) == 4


def test_a_warning_carries_numbers_but_no_customer_text(
    db_session: Session, clock: FrozenClock
) -> None:
    workspace, _ = make_workspace(db_session, clock, quota=10)
    spend(db_session, clock, workspace.id, 8)
    params = quota_notifications(db_session, "quota.warning")[0].params
    assert set(params) == {"used", "quota", "period_end"}
    assert (params["used"], params["quota"]) == (8, 10)


# --- periods -----------------------------------------------------------------------------------


def test_the_period_rolls_over_when_next_touched(db_session: Session, clock: FrozenClock) -> None:
    workspace, _ = make_workspace(db_session, clock, quota=100)
    spend(db_session, clock, workspace.id, 30)
    first = service.get_plan(db_session, clock, workspace.id)
    first_id, first_end = first.period_id, first.period_end
    clock.advance(days=30)  # still inside the period (15 Jan to 15 Feb)
    assert service.get_plan(db_session, clock, workspace.id).used == 30
    clock.advance(days=1, hours=1)
    row = service.get_plan(db_session, clock, workspace.id)
    assert row.used == 0 and row.period_id != first_id
    assert row.period_start == first_end
    assert row.period_end == datetime(2026, 3, 15, 12, 0, tzinfo=UTC)


def test_an_idle_workspace_skips_the_periods_nobody_used(
    db_session: Session, clock: FrozenClock
) -> None:
    workspace, _ = make_workspace(db_session, clock, quota=100)
    spend(db_session, clock, workspace.id, 30)
    clock.advance(days=100)  # 25 April
    row = service.get_plan(db_session, clock, workspace.id)
    assert row.used == 0
    assert row.period_start == datetime(2026, 4, 15, 12, 0, tzinfo=UTC)
    assert row.period_end == datetime(2026, 5, 15, 12, 0, tzinfo=UTC)


def test_periods_keep_the_original_day_across_short_months() -> None:
    jan_31 = datetime(2026, 1, 31, 8, 0, tzinfo=UTC)
    assert service.next_month(jan_31, 31) == datetime(2026, 2, 28, 8, 0, tzinfo=UTC)
    feb_28 = datetime(2026, 2, 28, 8, 0, tzinfo=UTC)
    assert service.next_month(feb_28, 31) == datetime(2026, 3, 31, 8, 0, tzinfo=UTC)
    dec_15 = datetime(2026, 12, 15, 8, 0, tzinfo=UTC)
    assert service.next_month(dec_15, 15) == datetime(2027, 1, 15, 8, 0, tzinfo=UTC)


def test_a_ledger_key_is_not_charged_again_in_a_later_period(
    db_session: Session, clock: FrozenClock
) -> None:
    workspace, _ = make_workspace(db_session, clock, quota=100)
    assert service.consume(db_session, clock, workspace.id, "replayed")
    clock.advance(days=32)
    assert service.consume(db_session, clock, workspace.id, "replayed")  # a replay, not a draft
    assert service.get_plan(db_session, clock, workspace.id).used == 0


def test_a_period_lasts_about_a_month(db_session: Session, clock: FrozenClock) -> None:
    workspace, _ = make_workspace(db_session, clock)
    row = service.get_plan(db_session, clock, workspace.id)
    assert timedelta(days=27) <= row.period_end - row.period_start <= timedelta(days=31)
