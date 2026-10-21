"""Retention (plan H17, security-and-privacy.md section 8): every rule just before and just after
its limit, with the injected clock; batching; the audit table is never touched.

``NOW`` is the run instant. A row of age ``d`` days (``ago(d)``) is older than a ``d``-day limit by
the extra second ``ago(d, 1)`` and younger by ``ago(d, -1)``.
"""

import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import func, insert, inspect, select
from sqlalchemy.orm import Session, sessionmaker

from app.ai.models import AgentRun
from app.audit import service as audit
from app.audit.models import AuditLog
from app.core.clock import FrozenClock
from app.core.config import Settings
from app.identity.models import User, Workspace
from app.inbox.models import InboundEvent, Message, ReplyDraft
from app.jobs.models import Job
from app.jobs.testing import run_due_jobs
from app.notifications.models import Notification
from app.reporting import service as reporting
from app.retention import cleanup
from app.retention import jobs as retention_jobs
from tests.factories import add_member, create_user, create_workspace, knowledge_ctx
from tests.helpers.reporting import DAY, TIMEZONE, Builder, at, build_day

NOW = datetime(2026, 10, 21, 2, 0, tzinfo=UTC)
SessionFactory = sessionmaker[Session]


def ago(days: int, seconds: int = 0) -> datetime:
    """The instant ``days`` days (plus ``seconds``) before ``NOW``."""
    return NOW - timedelta(days=days, seconds=seconds)


class World:
    """A workspace with one user and a simulated account, plus row helpers."""

    def __init__(self, session: Session) -> None:
        self.session = session
        self.workspace: Workspace = create_workspace(session, timezone=TIMEZONE)
        self.user: User = create_user(session)
        add_member(session, self.workspace, self.user, "owner")
        self.builder = Builder(session, self.workspace, self.user)

    def event(
        self, received_at: datetime, *, payload: dict[str, Any] | None = None
    ) -> InboundEvent:
        event = self.builder.inbound_event("processed", received_at)
        event.payload = payload if payload is not None else {"entry": "secret words"}
        self.session.flush()
        return event

    def run(self, created_at: datetime, status: str = "succeeded") -> AgentRun:
        run = AgentRun(
            workspace_id=self.workspace.id,
            task="interpret_command",
            status=status,
            input_snapshot={"redacted": "input"},
            created_at=created_at,
        )
        self.session.add(run)
        self.session.flush()
        return run

    def message_and_draft(self, when: datetime) -> tuple[Message, ReplyDraft]:
        conversation = self.builder.conversation(when)
        inbound = self.builder.message(conversation, "inbound", when)
        inbound.text = "Aylık üyelik ne kadar?"
        draft = self.builder.draft(
            conversation,
            inbound,
            source="ai",
            decision="auto",
            created_at=when,
        )
        draft.text, draft.template, draft.suggestion_text = "yanıt", "şablon {{fact:x}}", "öneri"
        outbound = self.builder.message(conversation, "outbound", when, draft=draft)
        outbound.text = "yanıt"
        self.session.flush()
        return inbound, draft

    def notification(self, read_at: datetime | None, n: int = 0) -> Notification:
        notification = Notification(
            workspace_id=self.workspace.id,
            recipient_user_id=self.user.id,
            type="report.daily_ready",
            severity="info",
            params={},
            dedup_key=f"n{n}-{uuid.uuid4()}",
            read_at=read_at,
            created_at=ago(500),
        )
        self.session.add(notification)
        self.session.flush()
        return notification

    def job(self, status: str, finished_at: datetime | None) -> Job:
        job = Job(
            job_type="test.old",
            payload={},
            status=status,
            run_at=ago(400),
            max_attempts=1,
            finished_at=finished_at,
        )
        self.session.add(job)
        self.session.flush()
        return job


@pytest.fixture
def world(db_session: Session) -> World:
    return World(db_session)


def go(
    db_session: Session,
    factory: SessionFactory,
    settings: Settings,
    batch_size: int = cleanup.BATCH_SIZE,
) -> cleanup.RetentionCounts:
    db_session.commit()
    counts = cleanup.run_retention(factory, settings, NOW, batch_size=batch_size)
    db_session.expire_all()
    return counts


def exists(session: Session, model: type, row: Any) -> bool:
    """Whether the row is still stored (its key is read without refreshing a deleted row)."""
    identity = inspect(row).identity
    assert identity is not None
    return session.get(model, identity[0]) is not None


# --- webhook rows ---------------------------------------------------------------------------


def test_webhook_payload_is_nulled_at_30_days_and_the_row_deleted_at_90(
    db_session: Session, shared_session_factory: SessionFactory, settings: Settings, world: World
) -> None:
    young = world.event(ago(30, -1))  # 29 d 23:59:59
    old = world.event(ago(30, 1))  # just past 30 d
    older = world.event(ago(89, 3600))  # 89 d 1 h: the row is younger than 90 d
    gone_just_before = world.event(ago(90, -1))
    gone = world.event(ago(90, 1))
    counts = go(db_session, shared_session_factory, settings)

    assert young.payload == {"entry": "secret words"}
    assert old.payload is None and exists(db_session, InboundEvent, old)
    assert older.payload is None and exists(db_session, InboundEvent, older)
    assert exists(db_session, InboundEvent, gone_just_before)  # 89 d 23:59:59: row kept
    assert gone_just_before.payload is None  # ... but its payload went at 30 d
    assert not exists(db_session, InboundEvent, gone)
    assert counts.webhook_rows_deleted == 1
    assert counts.webhook_payloads_nulled == 3  # old, older, gone_just_before


# --- agent run input ------------------------------------------------------------------------


def test_agent_input_is_nulled_at_30_days_but_a_running_run_keeps_it(
    db_session: Session, shared_session_factory: SessionFactory, settings: Settings, world: World
) -> None:
    young = world.run(ago(30, -1))
    old = world.run(ago(30, 1))
    running = world.run(ago(40), status="running")
    queued = world.run(ago(40), status="queued")
    counts = go(db_session, shared_session_factory, settings)

    assert young.input_snapshot == {"redacted": "input"}
    assert old.input_snapshot is None
    assert running.input_snapshot is not None and queued.input_snapshot is not None
    assert counts.agent_inputs_nulled == 1
    assert exists(db_session, AgentRun, old)  # the run itself stays; only the input goes


# --- message and draft text -----------------------------------------------------------------


def test_message_and_draft_text_is_nulled_at_365_days_and_the_metadata_kept(
    db_session: Session, shared_session_factory: SessionFactory, settings: Settings, world: World
) -> None:
    young_in, young_draft = world.message_and_draft(ago(365, -1))
    old_in, old_draft = world.message_and_draft(ago(365, 1))
    near_miss_in, _ = world.message_and_draft(ago(364, 3600))  # 364 d 1 h: must survive
    stamp = old_in.provider_timestamp
    counts = go(db_session, shared_session_factory, settings)

    assert young_in.text == "Aylık üyelik ne kadar?" and young_draft.text == "yanıt"
    assert near_miss_in.text == "Aylık üyelik ne kadar?"
    assert old_in.text is None
    assert (old_draft.text, old_draft.template, old_draft.suggestion_text) == (None, None, None)
    # Everything but the words is kept: the row, its direction, time, flags and links.
    assert old_in.direction == "inbound" and old_in.provider_timestamp == stamp
    assert old_in.is_simulated is True and old_in.is_deleted is False
    assert old_draft.status == "sent" and old_draft.decision == "auto"
    assert counts.messages_nulled == 2  # the old inbound and the old outbound message
    assert counts.drafts_nulled == 1


def test_the_report_for_a_day_is_unchanged_when_its_message_text_is_nulled(
    db_session: Session, shared_session_factory: SessionFactory, settings: Settings
) -> None:
    scenario = build_day(db_session)
    for message in db_session.scalars(select(Message)):
        message.text = "customer words"
    db_session.commit()
    ctx = knowledge_ctx(scenario.workspace, scenario.user, "owner")
    before = reporting.generate_daily_report(
        db_session, FrozenClock(scenario.now), ctx, DAY, scheduled=False
    )
    db_session.commit()

    year_later = at(DAY, 12) + timedelta(days=366)
    counts = cleanup.run_retention(shared_session_factory, settings, year_later)
    db_session.expire_all()
    assert counts.messages_nulled > 0
    assert db_session.scalar(
        select(func.count()).select_from(Message).where(Message.text.is_(None))
    )

    # The stored report of that day is a row of its own: nothing here touches it.
    stored = reporting.get_report(db_session, FrozenClock(year_later), ctx, DAY)
    assert stored.generated_at == before.generated_at
    assert stored.metrics == before.metrics

    # A regeneration counts the same messages. The one number that reads webhook rows
    # (``integration_errors``: failed inbound events) loses them at 90 days, by design.
    after = reporting.generate_daily_report(
        db_session, FrozenClock(scenario.now), ctx, DAY, scheduled=False
    )
    assert after.metrics.keys() == before.metrics.keys()
    for key in before.metrics:
        if key != "integration_errors":
            assert after.value(key) == before.value(key), key
    assert before.value("inbound_messages") == after.value("inbound_messages") > 0
    assert (before.value("integration_errors"), after.value("integration_errors")) == (18, 11)


# --- notifications and jobs -----------------------------------------------------------------


def test_notifications_go_90_days_after_being_read_and_unread_ones_never(
    db_session: Session, shared_session_factory: SessionFactory, settings: Settings, world: World
) -> None:
    just_read = world.notification(ago(90, -1), 1)
    long_read = world.notification(ago(90, 1), 2)
    unread = world.notification(None, 3)  # created 500 days ago, never read
    counts = go(db_session, shared_session_factory, settings)

    assert exists(db_session, Notification, just_read)
    assert not exists(db_session, Notification, long_read)
    assert exists(db_session, Notification, unread)
    assert counts.notifications_deleted == 1


def test_jobs_are_deleted_by_status(
    db_session: Session, shared_session_factory: SessionFactory, settings: Settings, world: World
) -> None:
    keep = [
        world.job("succeeded", ago(7, -1)),
        world.job("cancelled", ago(7, -1)),
        world.job("dead", ago(7, 1)),  # a dead job lives 90 d
        world.job("dead", ago(90, -1)),
        world.job("queued", None),  # old but still to be run
        world.job("running", None),
    ]
    drop = [
        world.job("succeeded", ago(7, 1)),
        world.job("cancelled", ago(7, 1)),
        world.job("dead", ago(90, 1)),
    ]
    counts = go(db_session, shared_session_factory, settings)

    assert all(exists(db_session, Job, j) for j in keep)
    assert not any(exists(db_session, Job, j) for j in drop)
    assert counts.jobs_finished_deleted == 2 and counts.jobs_dead_deleted == 1


# --- batching -------------------------------------------------------------------------------


def test_more_than_1000_rows_are_removed_in_batches_of_1000(
    db_session: Session, shared_session_factory: SessionFactory, settings: Settings, world: World
) -> None:
    rows = 2_500
    db_session.execute(
        insert(InboundEvent),
        [
            {
                "workspace_id": world.workspace.id,
                "social_account_id": world.builder.account.id,
                "provider_kind": "mock",
                "dedup_key": f"bulk-{i}",
                "event_type": "message",
                "status": "processed",
                "correlation_id": uuid.uuid4(),
                "is_simulated": True,
                "received_at": ago(120),
                "payload": {"i": i},
            }
            for i in range(rows)
        ],
    )
    keep = world.event(ago(1))
    db_session.commit()

    sessions_opened: list[int] = []

    def counting() -> Session:
        sessions_opened.append(1)
        return shared_session_factory()

    counts = cleanup.run_retention(counting, settings, NOW)  # type: ignore[arg-type]
    db_session.expire_all()

    assert cleanup.BATCH_SIZE == 1000
    assert counts.webhook_rows_deleted == rows
    assert db_session.scalar(select(func.count()).select_from(InboundEvent)) == 1
    assert exists(db_session, InboundEvent, keep)
    # 2 500 rows = batches of 1 000, 1 000 and 500 for the first rule, one empty pass per other.
    assert len(sessions_opened) == 3 + 7


def test_a_small_batch_size_gives_the_same_result(
    db_session: Session, shared_session_factory: SessionFactory, settings: Settings, world: World
) -> None:
    for _ in range(7):
        world.event(ago(100))
    counts = go(db_session, shared_session_factory, settings, batch_size=3)
    assert counts.webhook_rows_deleted == 7
    assert db_session.scalar(select(func.count()).select_from(InboundEvent)) == 0


def test_a_second_run_changes_nothing(
    db_session: Session, shared_session_factory: SessionFactory, settings: Settings, world: World
) -> None:
    world.message_and_draft(ago(400))
    world.event(ago(100))
    first = go(db_session, shared_session_factory, settings)
    second = go(db_session, shared_session_factory, settings)
    assert first.messages_nulled > 0 and first.webhook_rows_deleted == 1
    assert second == cleanup.RetentionCounts()


# --- the job: audit and scheduling ----------------------------------------------------------


def audit_count(session: Session) -> int:
    return session.scalar(select(func.count()).select_from(AuditLog)) or 0


@pytest.mark.invariant("INV-12")
def test_audit_rows_are_never_touched_and_cleanup_ran_is_written(
    db_session: Session, shared_session_factory: SessionFactory, world: World
) -> None:
    # An ancient audit row, a workspace one and a system one: all must survive every rule.
    old = audit.record(
        db_session,
        knowledge_ctx(world.workspace, world.user, "owner"),
        "fact.created",
        "fact",
        uuid.uuid4(),
        clock=FrozenClock(ago(2000)),
    )
    old_system = audit.record(
        db_session, None, "webhook.signature_invalid", None, None, clock=FrozenClock(ago(2000))
    )
    world.message_and_draft(ago(400))
    world.event(ago(100))
    world.job("succeeded", ago(10))
    db_session.commit()
    rows_before = audit_count(db_session)
    assert rows_before == 2

    clock = FrozenClock(NOW)
    retention_jobs.enqueue_retention_cleanup(db_session, clock)
    db_session.commit()
    assert run_due_jobs(clock, session_factory=shared_session_factory) == 1
    db_session.expire_all()

    assert audit_count(db_session) == rows_before + 1  # only the new entry
    assert db_session.get(AuditLog, old.id) is not None
    assert db_session.get(AuditLog, old_system.id) is not None
    (entry,) = audit.list_entries(db_session, system_level=True, action="retention.cleanup_ran")
    assert entry.workspace_id is None and entry.actor_type == "system"
    assert entry.occurred_at == NOW
    assert entry.metadata_["messages_nulled"] == 2
    assert entry.metadata_["drafts_nulled"] == 1
    assert entry.metadata_["webhook_rows_deleted"] == 1
    assert entry.metadata_["jobs_finished_deleted"] == 1
    assert all(isinstance(v, int) for v in entry.metadata_.values())


def test_the_cleanup_never_deletes_the_job_that_is_running_it(
    db_session: Session, shared_session_factory: SessionFactory
) -> None:
    clock = FrozenClock(NOW)
    retention_jobs.enqueue_retention_cleanup(db_session, clock)
    db_session.commit()
    run_due_jobs(clock, session_factory=shared_session_factory)
    job = db_session.scalar(select(Job).where(Job.job_type == "retention_cleanup"))
    assert job is not None and job.status == "succeeded"


@pytest.fixture
def tick(db_session: Session) -> Callable[[datetime], int]:
    def _tick(at_: datetime) -> int:
        count = retention_jobs.enqueue_retention_cleanup(db_session, FrozenClock(at_))
        db_session.commit()
        return count

    return _tick


def retention_job_rows(session: Session) -> list[Job]:
    return list(session.scalars(select(Job).where(Job.job_type == "retention_cleanup")))


def test_one_job_per_utc_day_from_02_00(
    db_session: Session,
    shared_session_factory: SessionFactory,
    tick: Callable[[datetime], int],
) -> None:
    assert tick(datetime(2026, 10, 21, 1, 59, tzinfo=UTC)) == 0
    assert retention_job_rows(db_session) == []
    assert tick(datetime(2026, 10, 21, 2, 0, tzinfo=UTC)) == 1
    [job] = retention_job_rows(db_session)
    assert job.dedup_key == "retention:2026-10-21" and job.workspace_id is None
    assert job.max_attempts == 1
    assert tick(datetime(2026, 10, 21, 2, 1, tzinfo=UTC)) == 0  # queued

    assert run_due_jobs(FrozenClock(NOW), session_factory=shared_session_factory) == 1
    for hour, minute in ((2, 2), (9, 30), (23, 59)):  # done: not again every minute
        assert tick(datetime(2026, 10, 21, hour, minute, tzinfo=UTC)) == 0
    assert tick(datetime(2026, 10, 22, 2, 0, tzinfo=UTC)) == 1
    assert len(retention_job_rows(db_session)) == 2


def test_a_dead_job_is_not_replaced_the_same_day(
    db_session: Session, tick: Callable[[datetime], int]
) -> None:
    tick(datetime(2026, 10, 21, 2, 0, tzinfo=UTC))
    [job] = retention_job_rows(db_session)
    job.status = "dead"
    db_session.commit()
    assert tick(datetime(2026, 10, 21, 2, 5, tzinfo=UTC)) == 0
    assert len(retention_job_rows(db_session)) == 1
