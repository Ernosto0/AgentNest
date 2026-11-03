"""The retention rules (plan H17). Pure data work: no job, no audit, no external call.

Every rule runs in batches of ``BATCH_SIZE`` rows, each batch in its own short transaction,
until a batch comes back short. Failed inbound-event deletion also records source gaps in that
transaction. A crash rolls back the current batch; the next run continues idempotently.

``audit_logs`` is **never** touched here: INV-12 allows no delete path, and the two-year purge
needs an ADR with the Phase 8 database privileges (plan H17). The text columns of messages and
drafts are written only by this module after their creation (INV-17 exception, H17): the row and
its metadata stay, only the words go, so reports built from the rows are unchanged.
"""

from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import (
    ColumnElement,
    Executable,
    Select,
    and_,
    delete,
    func,
    null,
    or_,
    select,
    update,
)
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session, sessionmaker

from app.agent.models import AgentAction, AgentStep, OwnerTask
from app.ai.models import AgentRun
from app.core.clock import FrozenClock
from app.core.config import Settings
from app.core.db import set_tenant_context
from app.identity.models import Workspace
from app.inbox.models import InboundEvent, Message, ReplyDraft
from app.jobs.models import Job
from app.notifications.models import Notification
from app.owner_requests.models import OwnerAnswer, OwnerQuestion
from app.reporting.models import ReportSourceGap

BATCH_SIZE = 1000


@dataclass(frozen=True)
class RetentionCounts:
    """How many rows each rule changed in one run (the audit entry carries exactly these)."""

    webhook_payloads_nulled: int = 0
    webhook_rows_deleted: int = 0
    agent_inputs_nulled: int = 0
    messages_nulled: int = 0
    drafts_nulled: int = 0
    notifications_deleted: int = 0
    jobs_finished_deleted: int = 0
    jobs_dead_deleted: int = 0
    memories_nulled: int = 0
    public_sources_nulled: int = 0
    # Phase 7.5 extensions (Session 12)
    owner_questions_redacted: int = 0
    owner_tasks_redacted: int = 0
    agent_steps_scrubbed: int = 0
    agent_actions_scrubbed: int = 0

    def as_dict(self) -> dict[str, int]:
        return asdict(self)


def _ids_of(model: Any, where: ColumnElement[bool], batch: int) -> Select[Any]:
    # ``model`` is any mapped class with an ``id`` column: every table cleaned here has one.
    return select(model.id).where(where).limit(batch)


def _run_batches(
    session_factory: sessionmaker[Session],
    statement_for: Callable[[int], Executable],
    batch_size: int,
) -> int:
    """Run ``statement_for(batch_size)`` until a batch changes fewer rows than ``batch_size``."""
    total = 0
    while True:
        with session_factory() as session:
            changed = int(session.execute(statement_for(batch_size)).rowcount)  # type: ignore[attr-defined]
            session.commit()
        total += changed
        if changed < batch_size:
            return total


def _null_columns(
    model: Any, columns: list[str], where: ColumnElement[bool]
) -> Callable[[int], Executable]:
    def statement(batch: int) -> Executable:
        return (
            update(model)
            .where(model.id.in_(_ids_of(model, where, batch)))
            .values({column: null() for column in columns})
            .execution_options(synchronize_session=False)
        )

    return statement


def _delete_rows(model: Any, where: ColumnElement[bool]) -> Callable[[int], Executable]:
    def statement(batch: int) -> Executable:
        return (
            delete(model)
            .where(model.id.in_(_ids_of(model, where, batch)))
            .execution_options(synchronize_session=False)
        )

    return statement


def _delete_inbound_events(
    session_factory: sessionmaker[Session], cutoff: datetime, batch_size: int
) -> int:
    """Source removal and its completeness markers commit together, including crash recovery."""
    total = 0
    while True:
        with session_factory() as session:
            removed = session.execute(
                delete(InboundEvent)
                .where(
                    InboundEvent.id.in_(
                        _ids_of(InboundEvent, InboundEvent.received_at < cutoff, batch_size)
                    )
                )
                .returning(
                    InboundEvent.workspace_id,
                    InboundEvent.status,
                    func.coalesce(InboundEvent.processed_at, InboundEvent.received_at).label(
                        "failed_at"
                    ),
                )
            ).all()
            lost = {(row.workspace_id, row.failed_at) for row in removed if row.status == "failed"}
            if lost:
                session.execute(
                    pg_insert(ReportSourceGap)
                    .values(
                        [
                            {
                                "workspace_id": ws,
                                "metric_key": "integration_errors",
                                "start_at": at,
                                "end_at": at,
                            }
                            for ws, at in lost
                        ]
                    )
                    .on_conflict_do_nothing(
                        index_elements=["workspace_id", "metric_key", "start_at", "end_at"]
                    )
                )
            session.commit()
        total += len(removed)
        if len(removed) < batch_size:
            return total


def run_retention(
    session_factory: sessionmaker[Session],
    settings: Settings,
    now: datetime,
    *,
    batch_size: int = BATCH_SIZE,
) -> RetentionCounts:
    """Apply every retention rule as of ``now`` (the injected clock) and count the changes."""

    def cutoff(days: int) -> datetime:
        return now - timedelta(days=days)

    with session_factory() as session:
        try:
            workspace_ids = list(session.scalars(select(Workspace.id)).all())
        except Exception:
            workspace_ids = []

    def run(statement_for: Callable[[int], Executable]) -> int:
        return _run_batches(session_factory, statement_for, batch_size)

    def run_tenant(statement_for: Callable[[int], Executable]) -> int:
        if not workspace_ids:
            return _run_batches(session_factory, statement_for, batch_size)
        total = 0
        for ws_id in workspace_ids:
            while True:
                with session_factory() as session:
                    set_tenant_context(session, ws_id)
                    changed = int(session.execute(statement_for(batch_size)).rowcount)  # type: ignore[attr-defined]
                    session.commit()
                total += changed
                if changed < batch_size:
                    break
        return total

    # Raw webhook payload: the whole row is gone at 90 days; a younger row loses its payload
    # at 30.
    rows_deleted = _delete_inbound_events(
        session_factory, cutoff(settings.retention_inbound_event_row_days), batch_size
    )
    payloads_nulled = run(
        _null_columns(
            InboundEvent,
            ["payload"],
            and_(
                InboundEvent.received_at < cutoff(settings.retention_webhook_payload_days),
                InboundEvent.payload.is_not(None),
            ),
        )
    )

    # The redacted model input is only for reproducing a run; a run still in progress keeps it.
    agent_inputs = run_tenant(
        _null_columns(
            AgentRun,
            ["input_snapshot"],
            and_(
                AgentRun.created_at < cutoff(settings.retention_agent_input_days),
                AgentRun.input_snapshot.is_not(None),
                AgentRun.status.not_in(("queued", "running")),
            ),
        )
    )

    # Message and draft text: nulled at 365 days. The message age is its provider time, the
    # clock every report uses, so the day it belongs to never changes (INV-17, H17).
    text_cutoff = cutoff(settings.retention_message_text_days)
    from app.comments.privacy import retention_batch as public_retention
    from app.memory.service import erase_source, retention_batch
    from app.owner_requests.service import recover_questions

    privacy_clock = FrozenClock(now)

    public_count = 0
    while True:
        with session_factory() as session:
            changed, examined = public_retention(session, privacy_clock, text_cutoff, batch_size)
            session.commit()
        public_count += changed
        if examined < batch_size:
            break
    recover_questions(session_factory, privacy_clock, batch_size)
    memory_count = 0
    while True:
        with session_factory() as session:
            changed = retention_batch(
                session, privacy_clock, cutoff(settings.retention_customer_memory_days), batch_size
            )
            session.commit()
        memory_count += changed
        if changed < batch_size:
            break
    # Source expiry invalidates memory before its authoritative message loses its body.
    while True:
        with session_factory() as session:
            from app.memory.models import MemorySource

            sources = list(
                session.scalars(
                    select(Message)
                    .where(
                        Message.provider_timestamp < text_cutoff,
                        Message.id.in_(
                            select(MemorySource.message_id)
                            .where(MemorySource.message_id.is_not(None))
                            .union(
                                select(OwnerQuestion.source_message_id).where(
                                    OwnerQuestion.source_message_id.is_not(None)
                                )
                            )
                        ),
                    )
                    .limit(batch_size)
                )
            )
            for source in sources:
                erase_source(session, privacy_clock, source)
            session.commit()
        if len(sources) < batch_size:
            break
    messages = run_tenant(
        _null_columns(
            Message,
            ["text"],
            and_(Message.provider_timestamp < text_cutoff, Message.text.is_not(None)),
        )
    )
    drafts = run_tenant(
        _null_columns(
            ReplyDraft,
            ["text", "template", "suggestion_text"],
            and_(
                ReplyDraft.created_at < text_cutoff,
                or_(
                    ReplyDraft.text.is_not(None),
                    ReplyDraft.template.is_not(None),
                    ReplyDraft.suggestion_text.is_not(None),
                ),
            ),
        )
    )
    run_tenant(
        lambda batch: (
            update(ReplyDraft)
            .where(
                ReplyDraft.id.in_(
                    _ids_of(
                        ReplyDraft,
                        and_(ReplyDraft.created_at < text_cutoff, ReplyDraft.validation != {}),
                        batch,
                    )
                )
            )
            .values(validation={})
            .execution_options(synchronize_session=False)
        )
    )

    # Phase 7.5: Owner questions and answers text redaction at text_cutoff
    owner_questions_nulled = run_tenant(
        lambda batch: (
            update(OwnerQuestion)
            .where(
                OwnerQuestion.id.in_(
                    _ids_of(
                        OwnerQuestion,
                        and_(
                            OwnerQuestion.created_at < text_cutoff,
                            OwnerQuestion.body.is_not(None),
                        ),
                        batch,
                    )
                )
            )
            .values(body=None, source_message_id=None, source_hash="")
            .execution_options(synchronize_session=False)
        )
    )
    owner_answers_nulled = run_tenant(
        _null_columns(
            OwnerAnswer,
            ["body"],
            and_(OwnerAnswer.created_at < text_cutoff, OwnerAnswer.body.is_not(None)),
        )
    )
    owner_questions_redacted = owner_questions_nulled + owner_answers_nulled

    # Phase 7.5: Agent owner tasks text redaction at text_cutoff
    owner_tasks_redacted = run_tenant(
        lambda batch: (
            update(OwnerTask)
            .where(
                OwnerTask.id.in_(
                    _ids_of(
                        OwnerTask,
                        and_(
                            OwnerTask.created_at < text_cutoff,
                            OwnerTask.request_text != "[REDACTED]",
                        ),
                        batch,
                    )
                )
            )
            .values(request_text="[REDACTED]", clarification=None, answers=[])
            .execution_options(synchronize_session=False)
        )
    )

    # Phase 7.5: Agent steps raw checkpoint / input / output ref scrubbing at agent_input_cutoff
    agent_steps_scrubbed = run_tenant(
        _null_columns(
            AgentStep,
            ["read_checkpoint", "input_ref", "output_ref"],
            and_(
                AgentStep.created_at < cutoff(settings.retention_agent_input_days),
                or_(
                    AgentStep.read_checkpoint.is_not(None),
                    AgentStep.input_ref.is_not(None),
                    AgentStep.output_ref.is_not(None),
                ),
            ),
        )
    )

    # Phase 7.5: Agent actions content_intent / policy_grant scrubbing at agent_input_cutoff
    # (only for non-active states: proposed, authorized, pending_execution, executing keep payloads)
    agent_actions_scrubbed = run_tenant(
        _null_columns(
            AgentAction,
            ["content_intent", "policy_grant"],
            and_(
                AgentAction.created_at < cutoff(settings.retention_agent_input_days),
                AgentAction.status.not_in(
                    ("proposed", "authorized", "pending_execution", "executing")
                ),
                or_(
                    AgentAction.content_intent.is_not(None),
                    AgentAction.policy_grant.is_not(None),
                ),
            ),
        )
    )

    # Notifications: 90 days after they were read. An unread one is never deleted.
    notifications = run_tenant(
        _delete_rows(
            Notification,
            and_(
                Notification.read_at.is_not(None),
                Notification.read_at < cutoff(settings.retention_notifications_read_days),
            ),
        )
    )

    # Jobs by status. ``finished_at`` is set for every finished job; the fallback is a safety net.
    finished = func.coalesce(Job.finished_at, Job.updated_at)
    jobs_done = run(
        _delete_rows(
            Job,
            and_(
                Job.status.in_(("succeeded", "cancelled")),
                finished < cutoff(settings.retention_jobs_succeeded_days),
            ),
        )
    )
    jobs_dead = run(
        _delete_rows(
            Job,
            and_(Job.status == "dead", finished < cutoff(settings.retention_jobs_dead_days)),
        )
    )

    return RetentionCounts(
        webhook_payloads_nulled=payloads_nulled,
        webhook_rows_deleted=rows_deleted,
        agent_inputs_nulled=agent_inputs,
        messages_nulled=messages,
        drafts_nulled=drafts,
        notifications_deleted=notifications,
        jobs_finished_deleted=jobs_done,
        jobs_dead_deleted=jobs_dead,
        memories_nulled=memory_count,
        public_sources_nulled=public_count,
        owner_questions_redacted=owner_questions_redacted,
        owner_tasks_redacted=owner_tasks_redacted,
        agent_steps_scrubbed=agent_steps_scrubbed,
        agent_actions_scrubbed=agent_actions_scrubbed,
    )
