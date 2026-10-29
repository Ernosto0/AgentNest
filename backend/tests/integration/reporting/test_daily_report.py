"""Daily report metrics (workflows.md section F.1): AC-E1, AC-E2, row-set equality, isolation."""

import uuid
from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.inbox.context import MESSAGING_WINDOW as INBOX_MESSAGING_WINDOW
from app.reporting import definitions
from app.reporting.definitions import BY_KEY, DEFINITIONS, DEFINITIONS_VERSION, KEYS
from app.reporting.metrics import compute_metrics
from app.reporting.models import DailyReport
from app.reporting.periods import day_bounds
from tests.factories import create_user, create_workspace, knowledge_ctx
from tests.helpers.reporting import (
    EXPECTED,
    EXPECTED_BREAKDOWN,
    EXPECTED_BURSTS,
    Builder,
    Scenario,
    at,
    build_day,
)


def _compute(session: Session, scenario: Scenario):  # type: ignore[no-untyped-def]
    return compute_metrics(session, scenario.ctx, scenario.start, scenario.end, scenario.now)


@pytest.fixture
def scenario(db_session: Session) -> Scenario:
    return build_day(db_session)


# --- registry -----------------------------------------------------------------------------------


def test_registry_preserves_twenty_legacy_metrics_and_adds_four_agent_metrics() -> None:
    assert DEFINITIONS_VERSION == "2"
    assert len(KEYS) == len(set(KEYS)) == 24
    assert set(KEYS) == set(EXPECTED)
    kinds = {d.key: d.kind for d in DEFINITIONS}
    assert {k for k, kind in kinds.items() if kind == "snapshot"} == {
        "attention_now",
        "unanswered_open_now",
        "pending_approvals_now",
        "content_scheduled_next_24h",
        "content_on_hold_now",
        "agent_unknown_now_v1",
    }
    assert {d.key for d in DEFINITIONS if d.value == "median"} == {"median_first_response_minutes"}
    assert {d.key for d in DEFINITIONS if d.grouped} == {"pending_approvals_now"}
    assert {d.section for d in DEFINITIONS} == set(definitions.SECTIONS)


def test_inbox_metrics_are_the_ones_staff_may_see() -> None:
    """H2: staff see the inbox-related metrics only."""
    assert set(definitions.INBOX_KEYS) == {
        "inbound_messages",
        "conversations_with_inbound",
        "new_conversations",
        "replies_sent",
        "replies_sent_auto",
        "replies_sent_approved",
        "replies_sent_by_owner",
        "native_replies",
        "escalations",
        "missed_conversations",
        "median_first_response_minutes",
        "attention_now",
        "unanswered_open_now",
    }


def test_messaging_window_matches_the_inbox() -> None:
    assert definitions.MESSAGING_WINDOW == INBOX_MESSAGING_WINDOW


def test_the_model_allows_generations_but_not_duplicate_revisions(db_session: Session) -> None:
    workspace = create_workspace(db_session)
    start, end = day_bounds(date(2026, 3, 10), workspace.timezone)
    values = {
        "workspace_id": workspace.id,
        "local_date": date(2026, 3, 10),
        "timezone": workspace.timezone,
        "period_start": start,
        "period_end": end,
        "metrics": {},
        "definitions_version": "1",
        "generated_at": end,
    }
    db_session.add(DailyReport(**values, revision=1))
    db_session.add(DailyReport(**values, revision=2))
    db_session.flush()
    db_session.add(DailyReport(**values, revision=2))
    with pytest.raises(Exception, match="uq_daily_reports_workspace_id_local_date_revision"):
        db_session.flush()
    db_session.rollback()


# --- AC-E1 ----------------------------------------------------------------------------------


def test_ac_e1_every_metric_has_its_exact_known_value(
    db_session: Session, scenario: Scenario
) -> None:
    metrics = _compute(db_session, scenario)

    assert [m.key for m in metrics.metrics] == list(KEYS)
    assert metrics.definitions_version == "2"
    for key, expected in EXPECTED.items():
        assert metrics.value(key) == expected, key
    # The fixture is built so that no two metrics share a value.
    legacy = {k: v for k, v in EXPECTED.items() if not k.startswith("agent_")}
    assert len(set(legacy.values())) == len(legacy)
    assert metrics.by_key["pending_approvals_now"].breakdown == EXPECTED_BREAKDOWN
    assert all(m.breakdown is None for m in metrics.metrics if m.key != "pending_approvals_now")
    assert metrics.has_simulated_data is True


def test_snapshot_metrics_follow_now_not_the_period(
    db_session: Session, scenario: Scenario
) -> None:
    """Snapshot metrics ignore the period; the 24 h look-ahead and the open window use ``now``."""
    ctx, start, end = scenario.ctx, scenario.start, scenario.end

    # 14 h after the end of the day (14:00 next day): the 13:00 customer window has closed, those
    # of 15:00 and 18:00 are open. Posts are scheduled at +0, 2, ..., 18 h and +24 h: from 14 h
    # on, the window [14 h, 38 h) holds those at 14, 16, 18 and 24 h.
    metrics = compute_metrics(db_session, ctx, start, end, scenario.now + timedelta(hours=14))
    assert metrics.value("unanswered_open_now") == 2
    assert metrics.value("content_scheduled_next_24h") == 4

    metrics = compute_metrics(db_session, ctx, start, end, scenario.now + timedelta(hours=19))
    assert metrics.value("unanswered_open_now") == 0
    assert metrics.value("content_scheduled_next_24h") == 1

    # Period metrics did not move.
    assert metrics.value("inbound_messages") == EXPECTED["inbound_messages"]


@pytest.mark.parametrize("key", KEYS)
def test_rows_count_equals_value(db_session: Session, scenario: Scenario, key: str) -> None:
    """The drill-down list is the metric's row set, so its length is the number shown."""
    definition = BY_KEY[key]
    rows = definition.rows(
        db_session, scenario.ctx, scenario.start, scenario.end, scenario.now
    ).subquery()
    count = db_session.scalar(select(func.count()).select_from(rows))
    metrics = _compute(db_session, scenario)
    if definition.value == "median":
        # The rows of the median are the answered bursts (the value is their median).
        assert count == len(EXPECTED_BURSTS)
    else:
        assert count == metrics.value(key) == EXPECTED[key]


def test_every_row_set_has_the_seven_documented_columns(
    db_session: Session, scenario: Scenario
) -> None:
    for definition in DEFINITIONS:
        stmt = definition.rows(db_session, scenario.ctx, scenario.start, scenario.end, scenario.now)
        assert list(stmt.selected_columns.keys()) == [
            "subject_type",
            "subject_id",
            "occurred_at",
            "is_simulated",
            "link_id",
            "measure",
            "group_key",
        ], definition.key


def test_median_is_taken_over_the_answered_bursts(db_session: Session, scenario: Scenario) -> None:
    stmt = BY_KEY["median_first_response_minutes"].rows(
        db_session, scenario.ctx, scenario.start, scenario.end, scenario.now
    )
    measures = sorted(float(row.measure) for row in db_session.execute(stmt))
    assert measures == [float(m) for m in EXPECTED_BURSTS]
    assert _compute(db_session, scenario).value("median_first_response_minutes") == 6.5


def test_median_is_null_without_an_answered_burst(db_session: Session) -> None:
    workspace = create_workspace(db_session)
    b = Builder(db_session, workspace, create_user(db_session))
    day = date(2026, 3, 10)
    c = b.conversation(at(day, 9))
    b.message(c, "inbound", at(day, 10))  # nobody answered
    start, end = day_bounds(day, workspace.timezone)
    metrics = compute_metrics(db_session, knowledge_ctx(workspace), start, end, end)
    assert metrics.value("inbound_messages") == 1
    assert metrics.value("median_first_response_minutes") is None


def test_a_reply_after_the_period_does_not_answer_a_burst_of_the_period(
    db_session: Session,
) -> None:
    """A report for a day is the same whenever it is generated: a late reply is not in it."""
    workspace = create_workspace(db_session)
    b = Builder(db_session, workspace, create_user(db_session))
    day = date(2026, 3, 10)
    c = b.conversation(at(day, 9))
    b.message(c, "inbound", at(day, 23, 50))
    b.message(c, "outbound", at(day + timedelta(days=1), 0, 10), kind="business_native")
    start, end = day_bounds(day, workspace.timezone)
    metrics = compute_metrics(db_session, knowledge_ctx(workspace), start, end, end)
    assert metrics.value("median_first_response_minutes") is None


def test_a_burst_that_started_before_the_period_is_not_counted_in_it(
    db_session: Session,
) -> None:
    workspace = create_workspace(db_session)
    b = Builder(db_session, workspace, create_user(db_session))
    day = date(2026, 3, 10)
    c = b.conversation(at(day - timedelta(days=1), 9))
    b.message(c, "inbound", at(day - timedelta(days=1), 23, 58))  # first of the burst
    b.message(c, "inbound", at(day, 0, 5))  # same burst, inside the period
    b.message(c, "outbound", at(day, 0, 20), kind="business_native")
    start, end = day_bounds(day, workspace.timezone)
    metrics = compute_metrics(db_session, knowledge_ctx(workspace), start, end, end)
    assert metrics.value("inbound_messages") == 1
    assert metrics.value("median_first_response_minutes") is None


# --- simulated data (INV-09) ----------------------------------------------------------------


def test_has_simulated_data_is_false_when_every_record_is_real(db_session: Session) -> None:
    real = build_day(db_session, simulated=False)
    metrics = _compute(db_session, real)
    assert metrics.has_simulated_data is False
    assert {k: metrics.value(k) for k in EXPECTED} == EXPECTED


def test_one_simulated_record_marks_the_report_simulated(db_session: Session) -> None:
    real = build_day(db_session, simulated=False)
    b = Builder(db_session, real.workspace, real.user, simulated=False, account=real.account)
    conversation = b.conversation(at(date(2026, 3, 10), 9))
    b.message(conversation, "inbound", at(date(2026, 3, 10), 21), simulated=True)
    metrics = _compute(db_session, real)
    assert metrics.has_simulated_data is True
    assert metrics.by_key["inbound_messages"].has_simulated_data is True
    assert metrics.by_key["replies_sent"].has_simulated_data is False


# --- isolation (INV-01) ------------------------------------------------------------------------


def test_records_of_another_workspace_change_no_metric(
    db_session: Session, scenario: Scenario
) -> None:
    before = _compute(db_session, scenario).as_list()

    other = build_day(db_session)  # the whole script again, in a second workspace
    assert other.workspace.id != scenario.workspace.id

    assert _compute(db_session, scenario).as_list() == before
    # ... and the second workspace sees exactly its own numbers.
    assert {k: _compute(db_session, other).value(k) for k in EXPECTED} == EXPECTED
    # No drill-down row set leaks a foreign record.
    for definition in DEFINITIONS:
        stmt = definition.rows(db_session, scenario.ctx, scenario.start, scenario.end, scenario.now)
        ids = {row.subject_id for row in db_session.execute(stmt)}
        foreign = {
            row.subject_id
            for row in db_session.execute(
                definition.rows(db_session, other.ctx, other.start, other.end, other.now)
            )
        }
        assert not ids & foreign, definition.key


def test_compute_metrics_leaves_the_session_writable(
    db_session: Session, scenario: Scenario
) -> None:
    """It runs in a read-only savepoint that is rolled back."""
    _compute(db_session, scenario)
    assert db_session.scalar(text("SHOW transaction_read_only")) == "off"
    Builder(db_session, scenario.workspace, scenario.user, account=scenario.account).conversation(
        scenario.now
    )
    db_session.flush()


def test_compute_metrics_cannot_write(db_session: Session, scenario: Scenario) -> None:
    from app.reporting import metrics as metrics_module

    original = metrics_module._compute_one

    def writing(*args, **kwargs):  # type: ignore[no-untyped-def]
        db_session.execute(text("UPDATE conversations SET attention = 'none'"))
        return original(*args, **kwargs)

    metrics_module._compute_one = writing  # type: ignore[assignment]
    try:
        with pytest.raises(Exception, match="read-only"):
            _compute(db_session, scenario)
    finally:
        metrics_module._compute_one = original  # type: ignore[assignment]


# --- AC-E2: day boundaries in the workspace timezone (INV-19) -----------------------------------

BOUNDARY_CASES = [
    pytest.param("Europe/Istanbul", date(2026, 3, 10), [], 24, id="istanbul"),
    pytest.param("Europe/Lisbon", date(2026, 1, 15), [], 24, id="lisbon-winter"),
    pytest.param("Europe/Lisbon", date(2026, 6, 15), [], 24, id="lisbon-summer"),
    # Clocks go forward at 01:00 UTC on 29 March 2026: the local day lasts 23 hours.
    pytest.param("Europe/Lisbon", date(2026, 3, 29), [], 23, id="lisbon-dst-spring-forward"),
    # Clocks go back at 01:00 UTC on 25 October 2026: 25 hours, and 01:30 happens twice.
    pytest.param(
        "Europe/Lisbon",
        date(2026, 10, 25),
        [datetime(2026, 10, 25, 0, 30, tzinfo=UTC), datetime(2026, 10, 25, 1, 30, tzinfo=UTC)],
        25,
        id="lisbon-dst-fall-back",
    ),
]


def _boundary_records(b: Builder, instants: list[datetime]) -> None:
    """At each instant: a new conversation with one inbound message, a published post and a
    fact change (one record per period-based source table)."""
    for instant in instants:
        conversation = b.conversation(instant)
        b.message(conversation, "inbound", instant)
        b.content("published", published_at=instant)
        b.audit("fact.updated", instant)


@pytest.mark.parametrize(("tz", "day", "extra", "hours"), BOUNDARY_CASES)
def test_ac_e2_records_on_the_local_day_boundaries(
    db_session: Session, tz: str, day: date, extra: list[datetime], hours: int
) -> None:
    workspace = create_workspace(db_session, timezone=tz)
    b = Builder(db_session, workspace, create_user(db_session))
    ctx = knowledge_ctx(workspace)
    previous, following = day - timedelta(days=1), day + timedelta(days=1)

    _boundary_records(
        b,
        [
            at(previous, 23, 59, 59, tz),  # last second of the day before
            at(day, 0, 0, 0, tz),  # first second of the day
            at(day, 12, 0, 0, tz),
            at(day, 23, 59, 59, tz),  # last second of the day
            at(following, 0, 0, 0, tz),  # first second of the day after
            *extra,
        ],
    )

    start, end = day_bounds(day, tz)
    assert end - start == timedelta(hours=hours)
    inside = 3 + len(extra)
    for which, expected in [(day, inside), (previous, 1), (following, 1)]:
        lo, hi = day_bounds(which, tz)
        metrics = compute_metrics(db_session, ctx, lo, hi, hi)
        for key in ("inbound_messages", "new_conversations", "content_published", "fact_changes"):
            assert metrics.value(key) == expected, (which, key)
        assert metrics.value("conversations_with_inbound") == expected


def test_a_period_computed_in_utc_would_get_lisbon_wrong(db_session: Session) -> None:
    """Guards the test above: on the DST day the UTC calendar day is not the local day."""
    start, end = day_bounds(date(2026, 3, 29), "Europe/Lisbon")
    assert (start, end) == (
        datetime(2026, 3, 29, 0, 0, tzinfo=UTC),
        datetime(2026, 3, 29, 23, 0, tzinfo=UTC),
    )
    assert uuid.uuid4()  # keep the import used when the module is edited
