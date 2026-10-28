"""Sending an approved reply (workflows.md §C step 4, ADR-011, INV-05/06/15).

The two-transaction pattern around the one external call:

* **T4** locks the draft, re-checks everything (status, approval and its payload hash, window,
  account), creates or finds the ledger row ``send_reply:{draft_id}``, marks it ``in_progress``
  and the draft ``sending``, and **commits before the provider is called** (INV-15).
* the provider call happens with **no transaction open**;
* **T5** records the outcome: delivered, retry, failed, or *unknown*.

An unknown outcome (a timeout after the request may have been accepted, or any unexpected
error after T4) is never retried by sending again: it becomes ``outcome_unknown`` and is
reconciled (``operations.reconcile``). One draft can therefore cause at most one message.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, sessionmaker

from app.agent.delegation import fence_action
from app.approvals import service as approvals
from app.audit import service as audit
from app.core.canonical import payload_hash
from app.core.clock import Clock
from app.core.config import Settings
from app.core.context import WorkspaceContext
from app.core.errors import AppError, RetryableError
from app.core.ids import new_id
from app.core.logging import get_logger
from app.inbox import attention, drafts
from app.inbox.approval_payload import approval_payload
from app.inbox.context import MESSAGING_WINDOW
from app.inbox.models import Conversation, ReplyDraft
from app.inbox.system import system_context
from app.integrations.instagram import queries
from app.integrations.instagram.base import AccountRef, InstagramProvider
from app.integrations.instagram.errors import (
    ProviderAuthError,
    ProviderError,
    ProviderInvalidRequest,
    ProviderOutcomeUnknown,
    ProviderPermissionError,
    ProviderRateLimited,
    ProviderTransientError,
    ProviderWindowClosed,
)
from app.integrations.instagram.models import SocialAccount
from app.integrations.instagram.registry import account_ref, get_provider
from app.jobs.queue import enqueue
from app.operations import health
from app.operations.models import Operation
from app.operations.payloads import EmitEchoPayload, ReconcileSendPayload
from app.operations.resolution import (
    lock_conversation,
    notify_reply_failed,
    record_delivered,
    set_operation,
    text_sha256,
)

log = get_logger(__name__)

SEND_MAX_ATTEMPTS = 6
SEND_MARGIN = timedelta(seconds=60)  # nothing is sent this close to the end of the window
FIRST_RECONCILE_DELAY = timedelta(minutes=2)
ECHO_DELAY = timedelta(seconds=1)
UNKNOWN_ECHO_DELAY = timedelta(seconds=5)

Kind = Literal["sent", "skipped", "retry", "waiting", "rescheduled", "failed", "unknown", "expired"]


@dataclass(frozen=True)
class SendOutcome:
    kind: Kind
    detail: str | None = None
    retry_after_seconds: float | None = None
    error_code: str | None = None
    run_at: datetime | None = None  # ``rescheduled``: when the circuit may be probed again


@dataclass(frozen=True)
class _Prepared:
    workspace_id: uuid.UUID
    operation_id: uuid.UUID
    draft_id: uuid.UUID
    account: AccountRef
    provider_kind: str
    recipient_id: str
    text: str


def execute_send_reply(
    session_factory: sessionmaker[Session],
    clock: Clock,
    settings: Settings,
    workspace_id: uuid.UUID,
    draft_id: uuid.UUID,
    *,
    correlation_id: uuid.UUID | None = None,
    provider: InstagramProvider | None = None,
) -> SendOutcome:
    """Send ``draft_id`` once. Safe to call again for the same draft (a retry, a re-run after a
    crash): the ledger and the draft state decide what, if anything, still has to happen."""
    with session_factory() as session:  # [T4]
        prepared = _prepare(session, clock, workspace_id, draft_id, correlation_id, settings)
        session.commit()
    if isinstance(prepared, SendOutcome):
        _wake_agent(session_factory, clock, workspace_id, draft_id)
        return prepared

    sender = provider or get_provider(
        prepared.provider_kind, settings=settings, session_factory=session_factory, clock=clock
    )
    error: Exception | None = None
    message_id: str | None = None
    try:  # no transaction is open here
        message_id = sender.send_text_message(
            prepared.account, prepared.recipient_id, prepared.text
        ).message_id
    except Exception as exc:
        error = exc

    with session_factory() as session:  # [T5]
        outcome = _record(session, clock, prepared, message_id, error)
        session.commit()
    _wake_agent(session_factory, clock, workspace_id, draft_id)
    return outcome


def _wake_agent(
    factory: sessionmaker[Session], clock: Clock, workspace_id: uuid.UUID, draft_id: uuid.UUID
) -> None:
    from app.agent.jobs import wake
    from app.agent.models import AgentAction

    with factory() as db:
        draft = db.get(ReplyDraft, draft_id)
        action = (
            db.get(AgentAction, draft.agent_action_id) if draft and draft.agent_action_id else None
        )
        if action is not None and draft is not None:
            wake(db, clock, workspace_id, action.thread_id, f"send:{draft_id}:{draft.status}")
            db.commit()


# --- T4 ------------------------------------------------------------------------------------------


def _skip(detail: str) -> SendOutcome:
    return SendOutcome("skipped", detail=detail)


def _prepare(
    session: Session,
    clock: Clock,
    workspace_id: uuid.UUID,
    draft_id: uuid.UUID,
    correlation_id: uuid.UUID | None,
    settings: Settings,
) -> _Prepared | SendOutcome:
    candidate = drafts.get_draft(session, workspace_id, draft_id)
    ctx = system_context(session, workspace_id, "operations.send")
    if candidate is None or ctx is None:
        return _skip("draft_missing")
    from app.agent.models import AccountAgent
    from app.approvals.models import Approval

    ref = session.get(Conversation, candidate.conversation_id)
    if ref is None:
        return _skip("conversation_missing")
    # Approval first matches human callbacks/cleanup. Account NOWAIT prevents a
    # domain-first disconnect/legacy transaction from creating a lock cycle.
    if candidate.approval_id:
        session.scalar(
            select(Approval).where(Approval.id == candidate.approval_id).with_for_update()
        )
    try:
        controller = session.scalar(
            select(AccountAgent)
            .where(
                AccountAgent.workspace_id == workspace_id,
                AccountAgent.social_account_id == ref.social_account_id,
            )
            .with_for_update(nowait=True)
        )
    except OperationalError as exc:
        if getattr(exc.orig, "sqlstate", None) == "55P03":
            raise RetryableError(
                "CONFLICT_STATE", "controller busy", retry_after_seconds=1
            ) from exc
        raise
    draft = drafts.get_draft(session, workspace_id, draft_id, lock=True)
    if draft is None:
        return _skip("draft_missing")
    session.refresh(draft)
    if draft.status == "sent":
        return SendOutcome("sent", detail="already_sent")
    if draft.status in ("sending", "outcome_unknown"):
        return _skip(f"in_flight:{draft.status}")
    if draft.status != "queued":
        return _skip(f"not_queued:{draft.status}")
    if (
        controller
        and draft.origin != "agent"
        and draft.source != "owner"
        and (
            controller.controller_mode == "agent"
            or draft.validation.get("controller_cutover_generation", 0)
            != controller.cutover_generation
        )
    ):
        return _cancel_queued(session, clock, ctx, draft, ref, "CONTROLLER_CHANGED")

    conversation = lock_conversation(session, draft)
    account = queries.get_account_in_workspace(
        session, workspace_id, conversation.social_account_id, lock=True
    )
    if account is None or draft.text is None or draft.approval_id is None:
        return _fail_queued(session, clock, ctx, draft, "SEND_PRECONDITION")
    now = clock.now()
    window_end = (
        conversation.last_inbound_at + MESSAGING_WINDOW if conversation.last_inbound_at else None
    )
    if window_end is None or now >= window_end - SEND_MARGIN:
        drafts.transition(session, clock, ctx, draft, "expire", reason="MESSAGING_WINDOW_CLOSED")
        attention.refresh(session, conversation)
        return SendOutcome("expired", error_code="MESSAGING_WINDOW_CLOSED")

    if draft.origin == "agent":
        try:
            if draft.agent_action_id is None:
                raise AppError("APPROVAL_STALE")
            from app.agent.dm import revalidate

            if not revalidate(session, clock, draft, conversation):
                raise AppError("APPROVAL_STALE")
            fence_action(
                session,
                clock,
                workspace_id,
                draft.agent_action_id,
                account_id=account.id,
                payload_hash_value=payload_hash(approval_payload(draft, conversation)),
                expected_action="dm.send",
            )
        except AppError as exc:
            return _cancel_queued(session, clock, ctx, draft, conversation, exc.code)

    # The approval: approved, for this version, not past its execution deadline, and for exactly
    # this text (INV-16). Anything else cancels the send.
    try:
        approval = approvals.assert_executable(
            session, clock, ctx, draft.approval_id, draft.version
        )
    except AppError as exc:
        return _cancel_queued(session, clock, ctx, draft, conversation, exc.code)
    if payload_hash(approval_payload(draft, conversation)) != approval.payload_hash:
        return _cancel_queued(session, clock, ctx, draft, conversation, "APPROVAL_STALE")

    if account.status not in ("connected", "degraded") or (
        account.capabilities.get("messaging") is not True
    ):
        # Stay queued: the window may outlast the problem (the expiry sweep ends it otherwise).
        return SendOutcome("waiting", error_code="ACCOUNT_NOT_CONNECTED")
    if (
        account.status == "degraded"
        and account.degraded_until is not None
        and now < account.degraded_until
    ):
        # The circuit is open (plan H11): no provider call and no attempt spent. The job comes
        # back when the cooldown ends, but never later than the end of the window or of the
        # approval, where the checks above end the send. (After the cooldown the send is the
        # half-open probe; its success closes the circuit.)
        run_at = min(account.degraded_until, window_end - SEND_MARGIN)
        if approval.execute_before is not None:
            run_at = min(run_at, approval.execute_before)
        return SendOutcome("rescheduled", error_code="ACCOUNT_DEGRADED", run_at=max(run_at, now))

    operation = _get_or_create_operation(session, clock, draft, account, window_end, correlation_id)
    if operation.status in ("in_progress", "outcome_unknown"):
        return _skip(f"operation_{operation.status}")
    if operation.status == "succeeded":
        # The effect happened but the draft was not closed (a crash after T5's call): repair it.
        message_id = str(operation.result.get("message_id") or "")
        drafts.transition(session, clock, ctx, draft, "start_send")
        record_delivered(
            session, clock, ctx, operation, draft, account,
            message_id=message_id, sent_at=operation.completed_at or now, via="repair",
        )  # fmt: skip
        return SendOutcome("sent", detail="repaired")
    if operation.status in ("failed", "cancelled"):
        return _skip(f"operation_{operation.status}")

    approvals.assert_executable(
        session, clock, ctx, draft.approval_id, draft.version, operation_id=operation.id
    )
    set_operation(clock, operation, "start")
    operation.attempts += 1
    operation.started_at = operation.started_at or now
    operation.next_attempt_at = None
    operation.provider_ref = {
        "recipient_id": conversation.customer_external_id,
        "text_sha256": text_sha256(draft.text),
    }
    drafts.transition(session, clock, ctx, draft, "start_send")
    attention.refresh(session, conversation)
    return _Prepared(
        workspace_id=workspace_id,
        operation_id=operation.id,
        draft_id=draft.id,
        account=account_ref(account, settings),
        provider_kind=account.provider_kind,
        recipient_id=conversation.customer_external_id,
        text=draft.text,
    )


def _get_or_create_operation(
    session: Session,
    clock: Clock,
    draft: ReplyDraft,
    account: SocialAccount,
    window_end: datetime,
    correlation_id: uuid.UUID | None,
) -> Operation:
    key = f"send_reply:{draft.id}"
    session.execute(
        pg_insert(Operation)
        .values(
            id=new_id(),
            workspace_id=draft.workspace_id,
            operation_type="send_reply",
            idempotency_key=key,
            subject_type="reply_draft",
            subject_id=draft.id,
            social_account_id=account.id,
            provider_kind=account.provider_kind,
            status="pending",
            attempts=0,
            max_attempts=SEND_MAX_ATTEMPTS,
            deadline_at=window_end - SEND_MARGIN,
            correlation_id=correlation_id,
            is_simulated=account.is_simulated,
            created_at=clock.now(),
        )
        .on_conflict_do_nothing(index_elements=["idempotency_key"])
    )
    operation = session.scalars(
        select(Operation).where(Operation.idempotency_key == key).with_for_update()
    ).one()
    draft.operation_id = operation.id
    return operation


def _fail_queued(
    session: Session, clock: Clock, ctx: WorkspaceContext, draft: ReplyDraft, code: str
) -> SendOutcome:
    drafts.transition(session, clock, ctx, draft, "cancel", reason=code)
    return SendOutcome("failed", error_code=code)


def _cancel_queued(
    session: Session,
    clock: Clock,
    ctx: WorkspaceContext,
    draft: ReplyDraft,
    conversation: Conversation,
    code: str,
) -> SendOutcome:
    """The approval no longer covers this send (stale, expired, consumed): nothing is sent."""
    reason = "MESSAGING_WINDOW_CLOSED" if code == "APPROVAL_EXPIRED" else code
    event = "expire" if code == "APPROVAL_EXPIRED" else "cancel"
    drafts.transition(session, clock, ctx, draft, event, reason=reason)
    attention.refresh(session, conversation)
    return SendOutcome("expired" if event == "expire" else "failed", error_code=reason)


# --- T5 ------------------------------------------------------------------------------------------


def _record(
    session: Session,
    clock: Clock,
    prepared: _Prepared,
    message_id: str | None,
    error: Exception | None,
) -> SendOutcome:
    ctx = system_context(session, prepared.workspace_id, "operations.send")
    draft = drafts.get_draft(session, prepared.workspace_id, prepared.draft_id, lock=True)
    operation = session.scalars(
        select(Operation)
        .where(
            Operation.workspace_id == prepared.workspace_id, Operation.id == prepared.operation_id
        )
        .with_for_update()
    ).one()
    account = queries.get_account_in_workspace(
        session, prepared.workspace_id, prepared.account.social_account_id, lock=True
    )
    if ctx is None or draft is None or account is None:
        raise RuntimeError("the records of a send vanished between T4 and T5")
    now = clock.now()

    if error is None and message_id is not None:
        set_operation(clock, operation, "succeed")
        operation.result = {"message_id": message_id}
        health.record_success(session, clock, ctx, account, correlation_id=operation.correlation_id)
        record_delivered(
            session, clock, ctx, operation, draft, account,
            message_id=message_id, sent_at=now, via="send",
        )  # fmt: skip
        _emit_echo_later(session, clock, operation, account, ECHO_DELAY)
        return SendOutcome("sent")

    if isinstance(error, ProviderWindowClosed):
        set_operation(clock, operation, "fail", code="MESSAGING_WINDOW_CLOSED")
        drafts.transition(session, clock, ctx, draft, "expire", reason="MESSAGING_WINDOW_CLOSED")
        attention.refresh(session, lock_conversation(session, draft))
        return SendOutcome("expired", error_code="MESSAGING_WINDOW_CLOSED")

    if isinstance(error, ProviderInvalidRequest):
        return _fail(session, clock, ctx, operation, draft, "PROVIDER_REJECTED", error.request_code)

    if isinstance(error, ProviderPermissionError):
        health.handle_permission_error(session, clock, ctx, account)
        return _fail(session, clock, ctx, operation, draft, "CAPABILITY_MISSING")

    if isinstance(error, ProviderAuthError):
        # Not sent, and not the customer's problem: the draft waits (queued) for a reconnection.
        set_operation(clock, operation, "retry", code="ACCOUNT_NEEDS_REAUTH")
        drafts.transition(session, clock, ctx, draft, "retry")
        health.handle_auth_error(session, clock, ctx, account)
        attention.refresh(session, lock_conversation(session, draft))
        return SendOutcome("waiting", error_code="ACCOUNT_NEEDS_REAUTH")

    if isinstance(error, ProviderRateLimited | ProviderTransientError):
        code = error.code
        if isinstance(error, ProviderTransientError):
            health.record_transient_failure(session, clock, ctx, account, code)
        out_of_time = operation.deadline_at is not None and now >= operation.deadline_at
        if operation.attempts >= operation.max_attempts or out_of_time:
            return _fail(session, clock, ctx, operation, draft, code)
        set_operation(clock, operation, "retry", code=code)
        drafts.transition(session, clock, ctx, draft, "retry")
        retry_after = error.retry_after_s if isinstance(error, ProviderRateLimited) else None
        return SendOutcome(
            "retry",
            error_code=code,
            retry_after_seconds=float(retry_after) if retry_after else None,
        )

    # ProviderOutcomeUnknown, or anything unexpected after the request may have been accepted:
    # never send again, find out what happened.
    if error is not None and not isinstance(error, ProviderOutcomeUnknown):
        log.error(
            "send_unexpected_error", error=type(error).__name__, operation_id=str(operation.id)
        )
    elif isinstance(error, ProviderError):
        log.warning("send_outcome_unknown", operation_id=str(operation.id))
    set_operation(clock, operation, "unknown", code="OUTCOME_UNKNOWN")
    drafts.transition(session, clock, ctx, draft, "unknown")
    conversation = lock_conversation(session, draft)
    attention.refresh(session, conversation)
    enqueue(
        session,
        "reconcile_send",
        ReconcileSendPayload(operation_id=operation.id, round=1),
        workspace_id=operation.workspace_id,
        correlation_id=operation.correlation_id,
        run_at=now + FIRST_RECONCILE_DELAY,
        dedup_key=f"reconcile_send:{operation.id}:1",
        clock=clock,
    )
    _emit_echo_later(session, clock, operation, account, UNKNOWN_ECHO_DELAY)
    audit.record(
        session,
        ctx,
        "reply.outcome_unknown",
        "reply_draft",
        draft.id,
        {"operation_id": operation.id, "conversation_id": conversation.id},
        is_simulated=draft.is_simulated,
        correlation_id=operation.correlation_id,
        clock=clock,
    )
    return SendOutcome("unknown", error_code="OUTCOME_UNKNOWN")


def _fail(
    session: Session,
    clock: Clock,
    ctx: WorkspaceContext,
    operation: Operation,
    draft: ReplyDraft,
    code: str,
    detail: str | None = None,
) -> SendOutcome:
    set_operation(clock, operation, "fail", code=code)
    operation.last_error_detail = detail
    drafts.transition(session, clock, ctx, draft, "fail", reason=code)
    attention.refresh(session, lock_conversation(session, draft))
    notify_reply_failed(session, clock, ctx, draft, code)
    audit.record(
        session,
        ctx,
        "reply.failed",
        "reply_draft",
        draft.id,
        {"operation_id": operation.id, "code": code, "conversation_id": draft.conversation_id},
        is_simulated=draft.is_simulated,
        correlation_id=operation.correlation_id,
        clock=clock,
    )
    return SendOutcome("failed", error_code=code)


def _emit_echo_later(
    session: Session, clock: Clock, operation: Operation, account: SocialAccount, delay: timedelta
) -> None:
    """Only the simulator: a real provider sends its own echo webhook."""
    if account.provider_kind != "mock":
        return
    enqueue(
        session,
        "demo_emit_echo",
        EmitEchoPayload(operation_id=operation.id),
        workspace_id=operation.workspace_id,
        correlation_id=operation.correlation_id,
        run_at=clock.now() + delay,
        dedup_key=f"demo_emit_echo:{operation.id}",
        clock=clock,
    )
