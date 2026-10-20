"""Operations jobs (background-jobs.md). Imported by ``app.handlers.load_handlers``.

``send_reply`` retries only what certainly did not reach the provider; an unknown outcome is
never retried but handed to ``reconcile_send`` (INV-05).
"""

import uuid
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.content.models import ContentItem
from app.content.payload import PublishContentPayload
from app.core.clock import Clock
from app.core.config import get_settings
from app.core.errors import RetryableError
from app.inbox import drafts
from app.inbox.ingest import ingest_webhook
from app.inbox.payloads import SendReplyPayload
from app.inbox.system import system_context
from app.integrations.instagram import queries, webhook_format
from app.integrations.instagram.base import AccountRef
from app.integrations.instagram.mock import MockInstagramProvider
from app.integrations.instagram.models import SimSentMessage
from app.jobs.queue import enqueue
from app.jobs.registry import JobContext, RescheduleJob, job_handler
from app.jobs.scheduler import register_periodic
from app.operations import publish, reconcile, resume, send
from app.operations.models import Operation
from app.operations.payloads import (
    EmitEchoPayload,
    ReconcilePublishPayload,
    ReconcileSendPayload,
    ReconcileStuckPayload,
    ResumeAccountPayload,
)
from app.operations.resolution import set_operation, text_sha256

STUCK_AFTER = timedelta(minutes=15)
# 1 / 5 / 15 / 30 minutes (state-machines.md §6); a larger Retry-After overrides.
SEND_BACKOFF = (60, 300, 900, 1800, 1800)
WAIT_BACKOFF_SECONDS = 300


@job_handler(
    "send_reply",
    SendReplyPayload,
    max_attempts=send.SEND_MAX_ATTEMPTS,
    timeout=90,
    backoff=SEND_BACKOFF,
)
def send_reply(job: JobContext) -> None:
    payload = job.payload
    if not isinstance(payload, SendReplyPayload) or job.workspace_id is None:
        return
    outcome = send.execute_send_reply(
        job.session_factory,
        job.clock,
        get_settings(),
        job.workspace_id,
        payload.reply_draft_id,
        correlation_id=job.correlation_id,
    )
    if outcome.kind == "retry":
        raise RetryableError(
            outcome.error_code or "PROVIDER_UNAVAILABLE",
            retry_after_seconds=outcome.retry_after_seconds,
        )
    if outcome.kind == "waiting":  # the account is not usable right now; the window may outlast it
        raise RetryableError(
            outcome.error_code or "ACCOUNT_NOT_CONNECTED", retry_after_seconds=WAIT_BACKOFF_SECONDS
        )


def _publish_dead(job: JobContext, code: str) -> None:
    """The publish job is dead: the item must not stay ``scheduled`` for ever (G10)."""
    payload = job.payload
    if not isinstance(payload, PublishContentPayload) or job.workspace_id is None:
        return
    with job.session_factory() as session:
        publish.abandon_publish(
            session, job.clock, job.workspace_id, payload.content_id, payload.version, code
        )
        session.commit()


@job_handler(
    "publish_content",
    PublishContentPayload,
    max_attempts=publish.PUBLISH_MAX_ATTEMPTS,
    timeout=publish.PUBLISH_LEASE_SECONDS,
    on_dead=_publish_dead,
    backoff=publish.PUBLISH_BACKOFF,
)
def publish_content(job: JobContext) -> None:
    """Publish one version of a scheduled item (workflows.md section E step 6).

    A retryable provider error retries **this** job row with ``max(backoff, Retry-After)``
    (G10). A quota that is used up is not a failure: the job is rescheduled for when there is
    room, without spending an attempt (G8). An unknown outcome is handed to ``reconcile_publish``
    by the executor itself.
    """
    payload = job.payload
    if not isinstance(payload, PublishContentPayload) or job.workspace_id is None:
        return
    outcome = publish.execute_publish(
        job.session_factory,
        job.clock,
        get_settings(),
        job.workspace_id,
        payload.content_id,
        payload.version,
        heartbeat=job.heartbeat,
    )
    if outcome.kind == "retry":
        raise RetryableError(
            outcome.error_code or "PROVIDER_UNAVAILABLE",
            retry_after_seconds=outcome.retry_after_seconds,
        )
    if outcome.kind == "rescheduled" and outcome.run_at is not None:
        raise RescheduleJob(outcome.run_at)


def _reconcile_publish_dead(job: JobContext, code: str) -> None:
    payload = job.payload
    if not isinstance(payload, ReconcilePublishPayload) or job.workspace_id is None:
        return
    with job.session_factory() as session:
        publish.abandon_reconcile(session, job.clock, job.workspace_id, payload.operation_id)
        session.commit()


@job_handler(
    "reconcile_publish",
    ReconcilePublishPayload,
    max_attempts=10,
    timeout=publish.PUBLISH_LEASE_SECONDS,
    on_dead=_reconcile_publish_dead,
)
def reconcile_publish(job: JobContext) -> None:
    """Read the container of a publish whose outcome is unknown and conclude (never a blind
    retry). While the container is still processing, or an unknown outcome came up again, the
    same job row is looked at again later, until the operation's deadline ends it."""
    payload = job.payload
    if not isinstance(payload, ReconcilePublishPayload) or job.workspace_id is None:
        return
    outcome = publish.reconcile_publish(
        job.session_factory,
        job.clock,
        get_settings(),
        job.workspace_id,
        payload.operation_id,
        heartbeat=job.heartbeat,
    )
    if outcome.kind in ("rescheduled", "unknown") and outcome.run_at is not None:
        raise RescheduleJob(outcome.run_at)


@job_handler("resume_account", ResumeAccountPayload, max_attempts=3)
def resume_account(job: JobContext) -> None:
    """The account is connected again: make the queued replies that can still go out due now."""
    payload = job.payload
    if not isinstance(payload, ResumeAccountPayload) or job.workspace_id is None:
        return
    with job.session_factory() as session:
        resume.resume_queued_replies(
            session,
            job.clock,
            job.workspace_id,
            payload.social_account_id,
            correlation_id=job.correlation_id,
        )
        session.commit()


@job_handler("reconcile_send", ReconcileSendPayload, max_attempts=3, timeout=60)
def reconcile_send(job: JobContext) -> None:
    payload = job.payload
    if not isinstance(payload, ReconcileSendPayload) or job.workspace_id is None:
        return
    reconcile.reconcile_send(
        job.session_factory,
        job.clock,
        get_settings(),
        job.workspace_id,
        payload.operation_id,
        payload.round,
    )


@job_handler("demo_emit_echo", EmitEchoPayload, max_attempts=1)
def demo_emit_echo(job: JobContext) -> None:
    """Simulator only: the echo webhook Instagram would send for a message we sent, delivered
    through the real ingestion path (signed, deduplicated, processed by the worker)."""
    payload = job.payload
    if not isinstance(payload, EmitEchoPayload) or job.workspace_id is None:
        return
    settings = get_settings()
    with job.session_factory() as session:
        op = session.scalars(
            select(Operation).where(
                Operation.workspace_id == job.workspace_id, Operation.id == payload.operation_id
            )
        ).one_or_none()
        account = (
            queries.get_account_in_workspace(session, job.workspace_id, op.social_account_id)
            if op
            else None
        )
        if op is None or account is None or account.provider_kind != "mock":
            return
        recipient = str(op.provider_ref.get("recipient_id", ""))
        sent = _sent_message(session, op)
        ref = AccountRef(account.id, account.workspace_id, account.external_account_id)
        external_id = account.external_account_id
    if sent is None:  # the message never reached the simulator: nothing to echo
        return
    mock = MockInstagramProvider(
        job.session_factory, job.clock, settings.mock_instagram_app_secret.get_secret_value()
    )
    if not mock.should_emit_echo(ref):
        return
    body = webhook_format.serialize(
        webhook_format.build_echo_payload(
            external_id, recipient, sent.message_id, sent.text, sent.sent_at, app_id="mock-app"
        )
    )
    signature = webhook_format.sign(body, settings.mock_instagram_app_secret.get_secret_value())
    with job.session_factory() as session:
        ingest_webhook(
            session, job.clock, settings, "mock", body, {webhook_format.SIGNATURE_HEADER: signature}
        )


def _sent_message(session: Session, op: Operation) -> SimSentMessage | None:
    """The simulator's record of what this operation sent: by id, or (when the answer was lost)
    by recipient and text."""
    message_id = op.result.get("message_id")
    stmt = select(SimSentMessage).where(
        SimSentMessage.workspace_id == op.workspace_id,
        SimSentMessage.social_account_id == op.social_account_id,
    )
    if message_id:
        return session.scalars(stmt.where(SimSentMessage.message_id == message_id)).first()
    recipient = op.provider_ref.get("recipient_id")
    digest = op.provider_ref.get("text_sha256")
    candidates = session.scalars(
        stmt.where(SimSentMessage.recipient_id == recipient).order_by(SimSentMessage.sent_at.desc())
    ).all()
    return next((m for m in candidates if text_sha256(m.text) == digest), None)


@job_handler("reconcile_stuck_operations", ReconcileStuckPayload, max_attempts=1)
def reconcile_stuck_operations(job: JobContext) -> None:
    """An operation that stayed ``in_progress`` (the worker died mid-call) may or may not have
    had its effect: make it ``outcome_unknown`` and reconcile it, never repeat it blindly
    (INV-05). A reply goes to ``reconcile_send``; a publish (G11) to ``reconcile_publish``."""
    cutoff = job.clock.now() - STUCK_AFTER
    with job.session_factory() as session:
        stuck = session.execute(
            select(Operation.id, Operation.workspace_id, Operation.operation_type).where(
                Operation.status == "in_progress",
                Operation.operation_type.in_(("send_reply", "publish_content")),
                Operation.started_at < cutoff,
            )
        ).all()
    for operation_id, workspace_id, operation_type in stuck:
        with job.session_factory() as session:
            if operation_type == "publish_content":
                _unstick_publish(session, job.clock, workspace_id, operation_id)
            else:
                _unstick_send(session, job.clock, workspace_id, operation_id)
            session.commit()


def _unstick_send(
    session: Session, clock: Clock, workspace_id: uuid.UUID, operation_id: uuid.UUID
) -> None:
    op = session.scalars(
        select(Operation)
        .where(Operation.workspace_id == workspace_id, Operation.id == operation_id)
        .with_for_update()
    ).one()
    ctx = system_context(session, workspace_id, "operations.reconcile")
    draft = drafts.get_draft(session, workspace_id, op.subject_id, lock=True)
    if op.status != "in_progress" or ctx is None or draft is None:
        return
    set_operation(clock, op, "unknown", code="OUTCOME_UNKNOWN")
    if draft.status == "sending":
        drafts.transition(session, clock, ctx, draft, "unknown")
    enqueue(
        session,
        "reconcile_send",
        ReconcileSendPayload(operation_id=op.id, round=1),
        workspace_id=workspace_id,
        correlation_id=op.correlation_id,
        dedup_key=f"reconcile_send:{op.id}:1",
        clock=clock,
    )


def _unstick_publish(
    session: Session, clock: Clock, workspace_id: uuid.UUID, operation_id: uuid.UUID
) -> None:
    subject_id = session.scalar(
        select(Operation.subject_id).where(
            Operation.workspace_id == workspace_id, Operation.id == operation_id
        )
    )
    # The executor's lock order: the item first, then the operation.
    item = session.scalars(
        select(ContentItem)
        .where(ContentItem.workspace_id == workspace_id, ContentItem.id == subject_id)
        .with_for_update()
    ).one_or_none()
    op = session.scalars(
        select(Operation)
        .where(Operation.workspace_id == workspace_id, Operation.id == operation_id)
        .with_for_update()
    ).one()
    ctx = system_context(session, workspace_id, "operations.reconcile")
    if op.status != "in_progress" or ctx is None or item is None:
        return
    publish.mark_unknown(session, clock, ctx, item, op)


@register_periodic
def enqueue_stuck_check(session: Session, clock: Clock) -> int:
    now = clock.now()
    enqueue(
        session,
        "reconcile_stuck_operations",
        ReconcileStuckPayload(),
        workspace_id=None,
        correlation_id=None,
        dedup_key=f"reconcile_stuck_operations:{now:%Y-%m-%dT%H}:{now.minute // 5}",
        clock=clock,
    )
    return 1
