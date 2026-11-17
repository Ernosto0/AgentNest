"""The weekly missed-customer report (D-03): after-hours DMs in the workspace timezone, reply time,
unanswered conversations, answered price questions, and a lira estimate that comes only from
verified prices and always shows its basis. Simulated data is never counted (INV-09)."""

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.clock import FrozenClock
from app.identity.models import User, Workspace
from app.inbox.models import Conversation, Message
from app.integrations.instagram.models import SocialAccount
from app.jobs.models import Job
from app.jobs.testing import run_due_jobs
from app.notifications.models import Notification
from app.reporting import jobs as report_jobs
from app.reporting import missed_customers
from app.reporting.weekly_sources import WEEKLY_DEFINITIONS
from tests.factories import (
    add_member,
    create_fact,
    create_user,
    create_workspace,
    knowledge_ctx,
    login,
    money,
)
from tests.helpers.gym import HOURS, MONTHLY, QUARTER, STUDENT, WEEK
from tests.helpers.reporting import Builder

TZ = "Europe/Istanbul"
MONDAY = date(2026, 3, 9)
PREVIOUS_MONDAY = date(2026, 3, 2)
# The report is read on Monday 2026-03-16 at 10:00 local, so the week of MONDAY has ended.
NOW = datetime(2026, 3, 16, 7, 0, tzinfo=UTC)


def at(day: date, hour: int, minute: int = 0, tz: str = TZ) -> datetime:
    """The instant (UTC) at the local wall-clock time of ``day``."""
    return datetime.combine(day, time(hour, minute), tzinfo=ZoneInfo(tz)).astimezone(UTC)


def d(offset: int, base: date = MONDAY) -> date:
    return date.fromordinal(base.toordinal() + offset)


MON, TUE, WED, THU, FRI, SAT, SUN = (d(i) for i in range(7))


@dataclass
class World:
    workspace: Workspace
    owner: User
    session: Session
    clock: FrozenClock
    real: Builder

    def ctx(self) -> Any:
        return knowledge_ctx(self.workspace, self.owner, "owner")

    def report(self, week: date = MONDAY) -> missed_customers.MissedCustomerReport:
        return missed_customers.build_report(self.session, self.clock, self.ctx(), week)

    def inbound(self, when: datetime, *, builder: Builder | None = None) -> Conversation:
        b = builder or self.real
        conversation = b.conversation(when)
        b.message(conversation, "inbound", when)
        return conversation

    def answer(
        self,
        conversation: Conversation,
        inbound: Message,
        when: datetime,
        *,
        intent: str | None,
        source: str = "ai",
        status: str = "sent",
        builder: Builder | None = None,
    ) -> None:
        b = builder or self.real
        draft = b.draft(
            conversation,
            inbound,
            source=source,
            decision="auto",
            status=status,
            created_at=when,
        )
        draft.intent = intent
        if status == "sent":
            b.message(conversation, "outbound", when, draft=draft)
        self.session.flush()


def _world(
    session: Session,
    *,
    hours: bool = True,
    prices: bool = True,
    timezone: str = TZ,
    clock: FrozenClock | None = None,
) -> World:
    workspace = create_workspace(session, timezone=timezone)
    owner = create_user(session)
    add_member(session, workspace, owner, "owner")
    clock = clock or FrozenClock(NOW)
    if hours:
        create_fact(session, workspace, HOURS, WEEK, clock=clock)
    if prices:
        create_fact(session, workspace, MONTHLY, money("6000"), clock=clock)
        create_fact(session, workspace, QUARTER, money("16500", unit="package"), clock=clock)
        create_fact(session, workspace, STUDENT, money("4500"), verified=False, clock=clock)
    session.flush()
    real = Builder(session, workspace, owner, simulated=False)
    return World(workspace, owner, session, clock, real)


def _first_message(session: Session, conversation: Conversation) -> Message:
    return session.scalars(
        select(Message)
        .where(Message.conversation_id == conversation.id, Message.direction == "inbound")
        .order_by(Message.provider_timestamp)
    ).first()  # type: ignore[return-value]


def _extra_account(world: World, *, simulated: bool) -> Builder:
    """A second (mock) account of the workspace; only one account may be active at a time, so
    it is disconnected, which does not make its history any more real."""
    account = SocialAccount(
        workspace_id=world.workspace.id,
        platform="instagram",
        provider_kind="mock",
        external_account_id=f"ext-{uuid.uuid4().hex[:12]}",
        username="mock",
        status="disconnected",
        capabilities={},
        granted_scopes=[],
    )
    world.session.add(account)
    world.session.flush()
    return Builder(
        world.session, world.workspace, world.owner, simulated=simulated, account=account
    )


def _script(world: World) -> dict[str, Conversation]:
    """A week with known answers. The gym is open Mon-Fri 07:00-23:00, Sat 09:00-21:00,
    Sun 10:00-18:00 (Istanbul, UTC+3)."""
    session = world.session
    c: dict[str, Conversation] = {}
    # A: asks the price at 06:59 (a minute before opening); the assistant answers at 08:00.
    c["A"] = world.inbound(at(MON, 6, 59))
    world.answer(c["A"], _first_message(session, c["A"]), at(MON, 8, 0), intent="pricing")
    # B: writes exactly at opening (07:00, inside); the owner answers from the Instagram app.
    c["B"] = world.inbound(at(MON, 7, 0))
    world.real.message(c["B"], "outbound", at(MON, 7, 10), kind="business_native")
    # C: writes exactly at closing (23:00, outside); nobody answers.
    c["C"] = world.inbound(at(TUE, 23, 0))
    # D: a booking question at 08:59 on Saturday (before 09:00); the assistant answers.
    c["D"] = world.inbound(at(SAT, 8, 59))
    world.answer(c["D"], _first_message(session, c["D"]), at(SAT, 9, 30), intent="booking")
    # E: a price question on Sunday 18:00 (closing); only a draft waiting for approval exists.
    c["E"] = world.inbound(at(SUN, 18, 0))
    world.answer(
        c["E"],
        _first_message(session, c["E"]),
        at(SUN, 18, 5),
        intent="pricing",
        status="pending_approval",
    )
    # Noise that must never count: a deleted message, a simulated conversation, a mock account
    # with malformed "real" flags, and last week's after-hours message.
    gone = world.real.conversation(at(WED, 2, 0))
    world.real.message(gone, "inbound", at(WED, 2, 0), deleted=True)
    simulated = _extra_account(world, simulated=True)
    sim = world.inbound(at(THU, 3, 0), builder=simulated)
    world.answer(
        sim, _first_message(session, sim), at(THU, 3, 5), intent="pricing", builder=simulated
    )
    mock = _extra_account(world, simulated=True)
    mock_conversation = mock.conversation(at(FRI, 3, 0), simulated=False)
    mock_message = mock.message(mock_conversation, "inbound", at(FRI, 3, 0), simulated=False)
    world.answer(mock_conversation, mock_message, at(FRI, 3, 5), intent="pricing", builder=mock)
    c["H"] = world.inbound(at(d(-2), 22, 0))  # Saturday of the previous week, after hours
    session.flush()
    return c


# --- the numbers -----------------------------------------------------------------------------


def test_the_week_counts_only_real_records_and_follows_the_hours(db_session: Session) -> None:
    world = _world(db_session)
    _script(world)
    report = world.report()

    assert report.hours_available and not report.is_partial
    assert (report.week_start, report.week_end) == (MONDAY, d(6))
    assert report.value("after_hours_dms") == 4  # A, C, D, E; B opens at 07:00 sharp
    assert report.value("unanswered_conversations") == 2  # C and E
    assert report.value("answered_questions") == 2  # A (price) and D (booking)
    assert report.value("after_hours_price_answers") == 1  # only A: D is a booking question
    # First replies: A 61 min, B 10 min, D 31 min.
    assert report.value("first_reply_median_minutes") == 31.0
    previous = {m.key: m.previous_value for m in report.metrics}
    assert previous["after_hours_dms"] == 1  # the Saturday message of the week before
    assert previous["answered_questions"] == 0
    assert previous["first_reply_median_minutes"] is None


def test_the_estimate_shows_every_input_and_uses_only_verified_prices(db_session: Session) -> None:
    world = _world(db_session)
    _script(world)
    estimate = world.report().estimate

    assert estimate.status == "ok" and estimate.currency == "TRY"
    assert estimate.price_questions == 1
    assert estimate.conversion_rate == missed_customers.CONVERSION_RATE == Decimal("0.05")
    # The unverified student price (4500) is not an input: the median of 6000 and 16500.
    assert [p.key for p in estimate.price_inputs] == [MONTHLY, QUARTER]
    assert estimate.median_price == Decimal("11250.00")
    assert estimate.amount == Decimal("562.50")  # 1 x 0.05 x 11250


def test_without_a_verified_price_only_counts_are_shown(db_session: Session) -> None:
    world = _world(db_session, prices=False)
    create_fact(
        db_session, world.workspace, STUDENT, money("4500"), verified=False, clock=world.clock
    )
    _script(world)
    report = world.report()
    assert report.estimate.status == "no_verified_price"
    assert report.estimate.amount is None and report.estimate.median_price is None
    assert report.estimate.price_inputs == []
    assert report.value("after_hours_price_answers") == 1  # the count itself is still shown


def test_with_more_prices_than_are_listed_the_count_of_prices_used_is_still_shown(
    db_session: Session,
) -> None:
    world = _world(db_session, prices=False)
    for n in range(1, 26):  # 25 prices: 100, 200, ..., 2500
        create_fact(
            db_session,
            world.workspace,
            f"pricing.item_{n:02d}",
            money(str(n * 100)),
            clock=world.clock,
        )
    _script(world)
    estimate = world.report().estimate
    assert estimate.status == "ok"
    assert estimate.median_price == Decimal("1300.00")  # over all 25, not only the 20 listed
    assert estimate.amount == Decimal("65.00")  # 1 x 0.05 x 1300
    assert estimate.price_count == 25
    assert len(estimate.price_inputs) == missed_customers.MAX_PRICE_INPUTS == 20


def test_a_price_in_another_currency_is_not_a_lira_input(db_session: Session) -> None:
    world = _world(db_session, prices=False)
    create_fact(
        db_session, world.workspace, MONTHLY, money("100", currency="EUR"), clock=world.clock
    )
    _script(world)
    assert world.report().estimate.status == "no_verified_price"


def test_without_verified_hours_after_hours_numbers_are_unknown_not_zero(
    db_session: Session,
) -> None:
    world = _world(db_session, hours=False)
    create_fact(db_session, world.workspace, HOURS, WEEK, verified=False, clock=world.clock)
    _script(world)
    report = world.report()
    assert not report.hours_available
    assert report.value("after_hours_dms") is None
    assert report.value("after_hours_price_answers") is None
    assert report.estimate.status == "hours_missing" and report.estimate.amount is None
    # Numbers that need no hours are still there.
    assert report.value("unanswered_conversations") == 2
    assert report.value("answered_questions") == 2
    with pytest.raises(Exception) as caught:
        missed_customers.metric_items(
            db_session, world.clock, world.ctx(), MONDAY, "after_hours_dms", locale="tr"
        )
    assert getattr(caught.value, "code", None) == "NOT_FOUND"


def test_a_week_with_no_data_is_empty_and_zero(db_session: Session) -> None:
    world = _world(db_session)
    report = world.report()
    assert report.empty
    assert report.value("after_hours_dms") == 0
    assert report.value("first_reply_median_minutes") is None  # no reply, no median
    assert report.estimate.status == "ok" and report.estimate.amount == Decimal("0.00")


def test_a_message_counts_in_the_workspace_timezone_not_utc(db_session: Session) -> None:
    """The same UTC instant is 08:00 in Istanbul (open) and 05:00 in Lisbon (closed)."""
    instant = datetime(2026, 3, 10, 5, 0, tzinfo=UTC)
    istanbul = _world(db_session)
    istanbul.inbound(instant)
    lisbon = _world(db_session, timezone="Europe/Lisbon")
    lisbon.inbound(instant)
    assert istanbul.report().value("after_hours_dms") == 0
    assert lisbon.report().value("after_hours_dms") == 1


def test_a_closed_exception_day_makes_the_whole_day_after_hours(db_session: Session) -> None:
    world = _world(db_session, hours=False)
    hours = WEEK | {"exceptions": [{"date": WED.isoformat(), "closed": True, "ranges": []}]}
    create_fact(db_session, world.workspace, HOURS, hours, clock=world.clock)
    world.inbound(at(WED, 12, 0))  # midday on a normal Wednesday would be open
    world.inbound(at(THU, 12, 0))
    assert world.report().value("after_hours_dms") == 1


def test_the_current_week_is_partial_and_a_future_week_is_refused(db_session: Session) -> None:
    clock = FrozenClock(at(WED, 12, 0))
    world = _world(db_session, clock=clock)
    world.inbound(at(TUE, 23, 30))
    world.inbound(at(THU, 3, 0))  # after "now": not part of the week so far
    report = world.report()
    assert report.is_partial and report.period_end == clock.now()
    assert report.value("after_hours_dms") == 1
    with pytest.raises(Exception) as caught:
        world.report(d(7))
    assert getattr(caught.value, "code", None) == "VALIDATION_FAILED"
    # Any date of a week selects that week's Monday.
    assert world.report(WED).week_start == MONDAY


# --- the drill-down --------------------------------------------------------------------------


def test_every_number_equals_the_records_behind_it(db_session: Session) -> None:
    world = _world(db_session)
    _script(world)
    report = world.report()
    for metric in report.metrics:
        collected: list[Any] = []
        cursor = None
        while True:
            page = missed_customers.metric_items(
                db_session,
                world.clock,
                world.ctx(),
                MONDAY,
                metric.key,
                locale="tr",
                cursor=cursor,
                limit=1,
            )
            collected.extend(page.items)
            cursor = page.next_cursor
            if cursor is None:
                break
        assert page.value == metric.value, metric.key
        if metric.key == "first_reply_median_minutes":
            assert sorted(i.measure for i in collected) == [10.0, 31.0, 61.0]
        else:
            assert len(collected) == metric.value, metric.key
        assert all(not i.is_simulated for i in collected)
        assert all(i.link and i.link["route"] for i in collected)


def test_an_unknown_metric_is_not_found(db_session: Session) -> None:
    world = _world(db_session)
    with pytest.raises(Exception) as caught:
        missed_customers.metric_items(
            db_session, world.clock, world.ctx(), MONDAY, "inbound_messages", locale="tr"
        )
    assert getattr(caught.value, "code", None) == "NOT_FOUND"


def test_one_workspace_never_counts_the_rows_of_another(db_session: Session) -> None:
    first = _world(db_session)
    second = _world(db_session)
    second.inbound(at(TUE, 23, 30))
    assert first.report().value("after_hours_dms") == 0
    assert second.report().value("after_hours_dms") == 1


def test_the_weekly_metrics_are_not_in_the_daily_registry() -> None:
    from app.reporting.definitions import BY_KEY

    assert {d.key for d in WEEKLY_DEFINITIONS}.isdisjoint(BY_KEY)


# --- the routes ------------------------------------------------------------------------------


@dataclass
class Api:
    world: World
    client: TestClient
    headers: dict[str, str]
    base: str


def _api(db_session: Session, make_client: Callable[[], TestClient], role: str = "owner") -> Api:
    clock = FrozenClock(NOW)
    world = _world(db_session, clock=clock)
    user = world.owner
    if role != "owner":
        user = create_user(db_session)
        add_member(db_session, world.workspace, user, role)
    db_session.flush()
    client = make_client()
    headers = login(client, user)
    return Api(world, client, headers, f"/api/v1/workspaces/{world.workspace.id}")


@pytest.fixture
def frozen_app_clock(clock: FrozenClock) -> FrozenClock:
    clock.advance(NOW - clock.now())
    return clock


def test_the_report_route_returns_the_formula_and_its_inputs(
    db_session: Session, make_client: Callable[[], TestClient], frozen_app_clock: FrozenClock
) -> None:
    api = _api(db_session, make_client)
    _script(api.world)
    response = api.client.get(
        f"{api.base}/reports/missed-customers",
        params={"week_start": "2026-03-11"},
        headers=api.headers,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["week_start"] == "2026-03-09" and body["week_end"] == "2026-03-15"
    assert body["has_simulated_data"] is False and body["hours_available"] is True
    metrics = {m["key"]: m for m in body["metrics"]}
    assert metrics["after_hours_dms"]["value"] == 4
    assert metrics["after_hours_dms"]["previous_value"] == 1
    assert metrics["after_hours_dms"]["link"]["api"].endswith(
        "/reports/missed-customers/2026-03-09/metrics/after_hours_dms"
    )
    estimate = body["estimate"]
    assert estimate["status"] == "ok" and estimate["currency"] == "TRY"
    assert estimate["amount"] == "562.50" and estimate["median_price"] == "11250.00"
    assert estimate["conversion_rate"] == "0.05" and estimate["price_questions"] == 1
    assert estimate["price_count"] == 2
    assert [p["key"] for p in estimate["price_inputs"]] == [MONTHLY, QUARTER]

    drill = api.client.get(
        f"{api.base}/reports/missed-customers/2026-03-09/metrics/unanswered_conversations",
        headers=api.headers,
    )
    assert drill.status_code == 200
    assert drill.json()["value"] == 2 and len(drill.json()["items"]) == 2
    assert "text" not in drill.json()["items"][0]


def test_staff_cannot_read_the_lira_report(
    db_session: Session, make_client: Callable[[], TestClient], frozen_app_clock: FrozenClock
) -> None:
    api = _api(db_session, make_client, role="staff")
    for path in (
        "/reports/missed-customers",
        "/reports/missed-customers/2026-03-09/metrics/after_hours_dms",
    ):
        response = api.client.get(f"{api.base}{path}", headers=api.headers)
        assert response.status_code == 403, path


def test_a_future_week_is_a_validation_error_over_http(
    db_session: Session, make_client: Callable[[], TestClient], frozen_app_clock: FrozenClock
) -> None:
    api = _api(db_session, make_client)
    response = api.client.get(
        f"{api.base}/reports/missed-customers",
        params={"week_start": "2026-03-23"},
        headers=api.headers,
    )
    assert response.status_code == 422


def test_one_workspace_never_sees_anothers_weekly_numbers_or_records(
    db_session: Session, make_client: Callable[[], TestClient], frozen_app_clock: FrozenClock
) -> None:
    api = _api(db_session, make_client)
    other = _world(db_session, clock=api.world.clock)
    _script(other)  # busy week in the other workspace; ours is empty
    body = api.client.get(f"{api.base}/reports/missed-customers", headers=api.headers).json()
    assert {m["key"]: m["value"] for m in body["metrics"]}["after_hours_dms"] == 0
    drill = api.client.get(
        f"{api.base}/reports/missed-customers/2026-03-09/metrics/unanswered_conversations",
        headers=api.headers,
    )
    assert drill.json()["items"] == []
    foreign = f"/api/v1/workspaces/{other.workspace.id}/reports/missed-customers"
    response = api.client.get(foreign, headers=api.headers)
    assert response.status_code == 404
    assert response.json()["code"] == "NOT_FOUND"


# --- the weekly job --------------------------------------------------------------------------


def _jobs(session: Session) -> list[Job]:
    return list(
        session.scalars(select(Job).where(Job.job_type == "generate_missed_customer_report"))
    )


def _tick(session: Session, moment: datetime) -> int:
    count = report_jobs.enqueue_missed_customer_reports(session, FrozenClock(moment))
    session.commit()
    return count


def test_the_job_is_enqueued_once_per_finished_week_from_monday_nine_local(
    db_session: Session,
) -> None:
    workspace = create_workspace(db_session)
    add_member(db_session, workspace, create_user(db_session), "owner")
    db_session.commit()
    assert _tick(db_session, at(MON, 8, 59)) == 0  # before 09:00 on Monday
    assert _tick(db_session, at(MON, 9, 0)) == 1
    [job] = _jobs(db_session)
    assert job.dedup_key == f"missed_customer_report:{workspace.id}:{PREVIOUS_MONDAY}"
    assert job.payload == {
        "workspace_id": str(workspace.id),
        "week_start": PREVIOUS_MONDAY.isoformat(),
    }
    assert _tick(db_session, at(MON, 9, 1)) == 0
    assert _tick(db_session, at(SUN, 23, 59)) == 0  # the same finished week, caught up or done
    assert _tick(db_session, at(d(7), 8, 59)) == 0
    assert _tick(db_session, at(d(7), 9, 0)) == 1  # the next Monday: the next week
    assert [j.payload["week_start"] for j in _jobs(db_session)] == [
        PREVIOUS_MONDAY.isoformat(),
        MONDAY.isoformat(),
    ]


def test_a_workspace_that_is_not_active_gets_no_weekly_job(db_session: Session) -> None:
    workspace = create_workspace(db_session)
    workspace.status = "deleting"
    db_session.commit()
    assert _tick(db_session, at(MON, 10, 0)) == 0


def test_the_job_announces_a_busy_week_once_and_stays_silent_for_an_empty_one(
    db_session: Session, shared_session_factory: sessionmaker[Session]
) -> None:
    clock = FrozenClock(at(d(7), 10, 0))  # Monday 2026-03-16, 10:00 local
    busy = _world(db_session, clock=clock)
    manager = create_user(db_session)
    add_member(db_session, busy.workspace, manager, "manager")
    staff = create_user(db_session)
    add_member(db_session, busy.workspace, staff, "staff")
    quiet = _world(db_session, clock=clock)
    _script(busy)
    db_session.commit()

    assert _tick(db_session, clock.now()) == 2
    assert run_due_jobs(clock, session_factory=shared_session_factory) == 2
    db_session.expire_all()
    notices = list(
        db_session.scalars(
            select(Notification).where(Notification.type == "report.missed_customers_ready")
        )
    )
    # The owner and the manager of the busy workspace; not staff, not the quiet workspace.
    assert {n.workspace_id for n in notices} == {busy.workspace.id}
    assert len(notices) == 2
    [first, *_] = notices
    assert first.params == {
        "week_start": "2026-03-09",
        "after_hours_dms": 4,
        "unanswered_conversations": 2,
    }
    assert first.is_simulated is False
    assert first.dedup_key == "missed-customers:2026-03-09"
    assert quiet.workspace.id not in {n.workspace_id for n in notices}

    # Running the same week again does not announce it a second time while it is unread.
    [job, *_] = [j for j in _jobs(db_session) if j.workspace_id == busy.workspace.id]
    job.status, job.finished_at = "queued", None
    db_session.commit()
    run_due_jobs(FrozenClock(clock.now()), session_factory=shared_session_factory)
    assert (
        db_session.scalar(
            select(func.count())
            .select_from(Notification)
            .where(Notification.type == "report.missed_customers_ready")
        )
        == 2
    )


def test_the_job_ignores_a_workspace_that_disappeared(
    db_session: Session, shared_session_factory: sessionmaker[Session]
) -> None:
    clock = FrozenClock(at(d(7), 10, 0))
    world = _world(db_session, clock=clock)
    db_session.commit()
    _tick(db_session, clock.now())
    world.workspace.status = "deleting"
    db_session.commit()
    run_due_jobs(clock, session_factory=shared_session_factory)
    assert db_session.scalar(select(func.count()).select_from(Notification)) == 0
