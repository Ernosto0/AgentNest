"""Inbox jobs (background-jobs.md). Imported by ``app.handlers.load_handlers``."""

import uuid
from datetime import timedelta

from sqlalchemy.orm import Session

from app.ai.runtime import runner_deps
from app.core.clock import Clock
from app.core.config import get_settings
from app.core.errors import RetryableError
from app.inbox import expiry, processing, reply_workflow, sandbox
from app.inbox.context import DraftContext, DraftSkip, prepare
from app.inbox.drafting import DraftPlan, failed_plan, make_plan
from app.inbox.models import InboundEvent
from app.inbox.payloads import (
    AssistantTestDraftPayload,
    DraftReplyPayload,
    ExpireReplyDraftsPayload,
    ProcessInboundEventPayload,
)
from app.jobs.queue import enqueue
from app.jobs.registry import JobContext, RescheduleJob, job_handler
from app.jobs.scheduler import register_periodic
from app.plans import service as usage

# Two model calls (the call and one regeneration), each with its own repair call, at 30 s.
DRAFT_TIMEOUT_SECONDS = 150
IN_FLIGHT_RETRY_SECONDS = 60


def _on_event_dead(job: JobContext, error_code: str) -> None:
    payload = job.payload
    if not isinstance(payload, ProcessInboundEventPayload):
        return
    with job.session_factory() as session:
        event = session.get(InboundEvent, payload.event_id)
        if event is not None and event.status == "received":
            event.status, event.error_code = "failed", error_code
            event.processed_at = job.clock.now()
            session.commit()


@job_handler(
    "process_inbound_event", ProcessInboundEventPayload, max_attempts=3, on_dead=_on_event_dead
)
def process_inbound_event(job: JobContext) -> None:
    payload = job.payload
    if not isinstance(payload, ProcessInboundEventPayload) or job.workspace_id is None:
        return
    with job.session_factory() as session:
        processing.process_inbound_event(
            session,
            job.clock,
            job.workspace_id,
            payload.event_id,
            debounce_seconds=get_settings().reply_debounce_seconds,
        )


def _on_draft_dead(job: JobContext, error_code: str) -> None:
    """The model stayed unavailable through every retry: a person answers (rule R10)."""
    payload = job.payload
    if not isinstance(payload, DraftReplyPayload) or job.workspace_id is None:
        return
    with job.session_factory() as session:
        prepared = prepare(
            session,
            job.clock,
            job.workspace_id,
            payload.conversation_id,
            message_id=payload.message_id,
            requested=payload.requested,
        )
        session.commit()
    if not isinstance(prepared, DraftContext):
        return
    with job.session_factory() as session:
        reply_workflow.persist_plan(
            session,
            job.clock,
            prepared,
            failed_plan(prepared, "LLM_UNAVAILABLE"),
            correlation_id=job.correlation_id,
        )
        session.commit()


@job_handler(
    "draft_reply",
    DraftReplyPayload,
    max_attempts=3,  # agent-runtime.md §2: 10 s / 60 s / 300 s backoff
    timeout=DRAFT_TIMEOUT_SECONDS,
    on_dead=_on_draft_dead,
    backoff=(10, 60, 300),
)
def draft_reply(job: JobContext) -> None:
    """Three phases; the model is called in the middle with **no transaction open**."""
    payload = job.payload
    if not isinstance(payload, DraftReplyPayload) or job.workspace_id is None:
        return
    with job.session_factory() as session:  # [T1] read-only
        prepared = prepare(
            session,
            job.clock,
            job.workspace_id,
            payload.conversation_id,
            message_id=payload.message_id,
            requested=payload.requested,
        )
        session.commit()
    if isinstance(prepared, DraftSkip):
        if prepared.retry:  # an earlier reply is still being sent
            raise RetryableError("REPLY_IN_FLIGHT", retry_after_seconds=IN_FLIGHT_RETRY_SECONDS)
        return
    # The monthly allowance (plans). A slot is reserved before the model is called; when
    # drafting is paused no model call is made and the message waits for a person, with the
    # reason on a needs-human draft: the inbound message itself is already stored and notified.
    with job.session_factory() as session:
        ticket = usage.reserve(
            session,
            job.clock,
            job.workspace_id,
            f"legacy:{job.job_id}:{prepared.covers_through_message_id}",
        )
        ticket_id = ticket.id if ticket is not None else None
        session.commit()
    if ticket_id is None:
        plan = failed_plan(prepared, usage.PAUSED_REASON)
    else:
        plan = make_plan(  # no transaction is open here
            runner_deps(job.session_factory, job.clock), prepared, job.correlation_id, job.job_id
        )
    newer = _store_draft(job, prepared, plan, ticket_id)
    if newer is None:  # the slot was taken by another draft while this model call ran
        newer = _store_draft(job, prepared, failed_plan(prepared, usage.PAUSED_REASON), None)
    if newer:
        # The customer wrote again while the model ran. This job's dedup key kept that
        # message's own enqueue from creating a second job, so this job must run again.
        raise RescheduleJob(
            job.clock.now() + timedelta(seconds=get_settings().reply_debounce_seconds)
        )


def _store_draft(
    job: JobContext, prepared: DraftContext, plan: DraftPlan, ticket_id: uuid.UUID | None
) -> bool | None:
    """[T3] Store the draft and count it in the same transaction. Returns whether a newer
    customer message made the plan obsolete, or ``None`` when the allowance ran out meanwhile
    (nothing was stored)."""
    with job.session_factory() as session:
        draft = reply_workflow.persist_plan(
            session, job.clock, prepared, plan, correlation_id=job.correlation_id
        )
        if ticket_id is not None and not usage.finish(
            session,
            job.clock,
            prepared.workspace_id,
            ticket_id,
            produced=draft is not None and bool(plan.text or plan.suggestion_text),
        ):
            session.rollback()
            return None
        # Checked while T3 still holds the conversation lock: a customer message cannot be
        # stored between this answer and the commit.
        newer = draft is None and reply_workflow.newer_inbound_arrived(session, prepared)
        session.commit()
        return newer


def _on_test_draft_dead(job: JobContext, error_code: str) -> None:
    """The model stayed unavailable through every retry: the test chat shows what a real
    customer would get, a person answers (rule R10)."""
    payload = job.payload
    if not isinstance(payload, AssistantTestDraftPayload) or job.workspace_id is None:
        return
    with job.session_factory() as session:
        prepared = sandbox.prepare(session, job.clock, job.workspace_id, payload.turn_id)
        session.commit()
    if prepared is None:
        return
    with job.session_factory() as session:
        sandbox.apply_plan(session, job.clock, prepared, failed_plan(prepared, "LLM_UNAVAILABLE"))
        session.commit()


@job_handler(
    "assistant_test_draft",
    AssistantTestDraftPayload,
    max_attempts=3,
    timeout=DRAFT_TIMEOUT_SECONDS,
    on_dead=_on_test_draft_dead,
    backoff=(10, 60, 300),
)
def assistant_test_draft(job: JobContext) -> None:
    """The owner's test chat (F-02): the real drafting pipeline, a sandbox result. Three phases
    like ``draft_reply``; the model is called in the middle with **no transaction open**. Nothing
    is approved, queued for sending, notified or remembered (see ``inbox.sandbox``)."""
    payload = job.payload
    if not isinstance(payload, AssistantTestDraftPayload) or job.workspace_id is None:
        return
    with job.session_factory() as session:  # [T1] read-only
        prepared = sandbox.prepare(session, job.clock, job.workspace_id, payload.turn_id)
        session.commit()
    if prepared is None:  # reset, answered or gone: nothing to do
        return
    plan = make_plan(  # no transaction is open here
        runner_deps(job.session_factory, job.clock), prepared, job.correlation_id, job.job_id
    )
    with job.session_factory() as session:  # [T3]
        sandbox.apply_plan(session, job.clock, prepared, plan)
        session.commit()


@job_handler("expire_reply_drafts", ExpireReplyDraftsPayload, max_attempts=1)
def expire_reply_drafts(job: JobContext) -> None:
    expiry.expire_closed_window_drafts(job.session_factory, job.clock)


@register_periodic
def enqueue_reply_draft_expiry(session: Session, clock: Clock) -> int:
    enqueue(
        session,
        "expire_reply_drafts",
        ExpireReplyDraftsPayload(),
        workspace_id=None,
        correlation_id=None,
        dedup_key=f"expire_reply_drafts:{clock.now():%Y-%m-%dT%H:%M}",
        clock=clock,
    )
    return 1
