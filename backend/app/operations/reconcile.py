"""Reconciling a send whose outcome is unknown (ADR-011, INV-05, workflows.md §C and §G).

Order of evidence: (a) an echo webhook carrying our message, matched by provider message id or
by recipient + SHA-256 of the text inside the window; (b) the provider's conversation lookup;
(c) the end of the reconciliation window, which reports ``OUTCOME_UNCONFIRMED``. A send is
**never repeated** to find out: the message may have been delivered, and a duplicate to a
customer is worse than a miss.
"""

import uuid
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.core.clock import Clock
from app.core.config import Settings, get_settings
from app.core.context import WorkspaceContext
from app.inbox import drafts, echoes
from app.inbox.echoes import Echo
from app.inbox.models import ReplyDraft
from app.inbox.system import system_context
from app.integrations.instagram import queries
from app.integrations.instagram.base import AccountRef, InstagramProvider, OutboundMessageInfo
from app.integrations.instagram.errors import ProviderError
from app.integrations.instagram.models import SocialAccount
from app.integrations.instagram.registry import get_provider
from app.jobs.queue import enqueue
from app.operations.models import Operation
from app.operations.payloads import ReconcileSendPayload
from app.operations.resolution import (
    record_late_delivery,
    resolve_unconfirmed,
    resolve_unknown_as_sent,
    text_sha256,
)

RECONCILE_INTERVAL = timedelta(minutes=2)
CLOCK_SKEW = timedelta(minutes=1)


# --- echoes ---------------------------------------------------------------------------------


def match_echo(session: Session, clock: Clock, ctx: WorkspaceContext, echo: Echo) -> bool:
    """Is this echo the one of a send of ours? (Registered with ``inbox.echoes`` below.)

    A match resolves an unknown send as delivered, or records the id for a send that is still in
    flight; either way the echo is **not** a reply typed in the Instagram app.
    """
    window = timedelta(minutes=get_settings().send_reconcile_window_minutes)
    candidates = session.scalars(
        select(Operation)
        .where(
            Operation.workspace_id == ctx.workspace_id,
            Operation.social_account_id == echo.social_account_id,
            Operation.operation_type == "send_reply",
            Operation.status.in_(("in_progress", "outcome_unknown", "succeeded", "failed")),
            Operation.provider_ref["recipient_id"].astext == echo.customer_id,
        )
        .order_by(Operation.created_at.desc())
        .limit(20)
        .with_for_update()
    ).all()
    digest = text_sha256(echo.text) if echo.text is not None else None
    for op in candidates:
        if op.status == "succeeded":
            if echo.mid and op.result.get("message_id") == echo.mid:
                return True
            continue
        if op.status == "failed" and op.last_error_code != "OUTCOME_UNCONFIRMED":
            continue  # a send that certainly failed has no echo to explain
        started = op.started_at
        by_text = (
            digest is not None
            and digest == op.provider_ref.get("text_sha256")
            and started is not None
            and started - CLOCK_SKEW <= echo.provider_timestamp <= started + window + CLOCK_SKEW
        )
        if not by_text:
            continue
        if op.status == "failed":  # we had given up (OUTCOME_UNCONFIRMED): it did arrive after all
            draft = drafts.get_draft(session, op.workspace_id, op.subject_id, lock=True)
            account = queries.get_account_in_workspace(
                session, op.workspace_id, op.social_account_id
            )
            if draft is None or account is None or echo.mid is None:
                return False
            record_late_delivery(
                session, clock, ctx, op, draft, account,
                message_id=echo.mid, sent_at=echo.provider_timestamp,
            )  # fmt: skip
        elif op.status == "outcome_unknown":
            draft = drafts.get_draft(session, op.workspace_id, op.subject_id, lock=True)
            account = queries.get_account_in_workspace(
                session, op.workspace_id, op.social_account_id
            )
            if draft is None or account is None or echo.mid is None:
                return False
            resolve_unknown_as_sent(
                session, clock, ctx, op, draft, account,
                message_id=echo.mid, sent_at=echo.provider_timestamp, via="echo",
            )  # fmt: skip
        else:  # in_progress: the send's own outcome (T5) is still to be recorded
            op.provider_ref = {**op.provider_ref, "echo_mid": echo.mid}
        return True
    return False


echoes.register_matcher(match_echo)


# --- the lookup and the deadline ------------------------------------------------------------


def reconcile_send(
    session_factory: sessionmaker[Session],
    clock: Clock,
    settings: Settings,
    workspace_id: uuid.UUID,
    operation_id: uuid.UUID,
    round_: int = 1,
    *,
    provider: InstagramProvider | None = None,
) -> str:
    """One reconciliation check. Returns ``resolved`` (nothing left to do), ``sent``,
    ``unconfirmed`` or ``rescheduled``."""
    with session_factory() as session:
        op = session.scalars(
            select(Operation).where(
                Operation.workspace_id == workspace_id, Operation.id == operation_id
            )
        ).one_or_none()
        if op is None or op.status != "outcome_unknown" or op.started_at is None:
            return "resolved"
        account = queries.get_account_in_workspace(session, workspace_id, op.social_account_id)
        if account is None:
            return "resolved"
        ref = AccountRef(account.id, workspace_id, account.external_account_id)
        kind, recipient = account.provider_kind, str(op.provider_ref.get("recipient_id", ""))
        digest, since = op.provider_ref.get("text_sha256"), op.started_at - CLOCK_SKEW

    found: OutboundMessageInfo | None = None
    reader = provider or get_provider(
        kind, settings=settings, session_factory=session_factory, clock=clock
    )
    try:  # no transaction is open here
        for info in reader.find_recent_outbound(ref, recipient, since):
            if info.text is not None and text_sha256(info.text) == digest:
                found = info
                break
    except ProviderError:
        pass  # a failed lookup and an empty one are treated alike: ask again later

    with session_factory() as session:
        op = session.scalars(
            select(Operation)
            .where(Operation.workspace_id == workspace_id, Operation.id == operation_id)
            .with_for_update()
        ).one()
        if op.status != "outcome_unknown":
            return "resolved"  # an echo got there first
        ctx = system_context(session, workspace_id, "operations.reconcile")
        draft = drafts.get_draft(session, workspace_id, op.subject_id, lock=True)
        stored = queries.get_account_in_workspace(session, workspace_id, op.social_account_id)
        if ctx is None or draft is None or stored is None:
            return "resolved"
        outcome = _conclude(session, clock, settings, ctx, op, draft, stored, found, round_)
        session.commit()
        return outcome


def _conclude(
    session: Session,
    clock: Clock,
    settings: Settings,
    ctx: WorkspaceContext,
    op: Operation,
    draft: ReplyDraft,
    account: SocialAccount,
    found: OutboundMessageInfo | None,
    round_: int,
) -> str:
    if found is not None:
        resolve_unknown_as_sent(
            session, clock, ctx, op, draft, account,
            message_id=found.message_id, sent_at=found.sent_at, via="lookup",
        )  # fmt: skip
        return "sent"
    now = clock.now()
    started = op.started_at or now
    if now >= started + timedelta(minutes=settings.send_reconcile_window_minutes):
        resolve_unconfirmed(session, clock, ctx, op, draft)
        return "unconfirmed"
    enqueue(
        session,
        "reconcile_send",
        ReconcileSendPayload(operation_id=op.id, round=round_ + 1),
        workspace_id=op.workspace_id,
        correlation_id=op.correlation_id,
        run_at=now + RECONCILE_INTERVAL,
        dedup_key=f"reconcile_send:{op.id}:{round_ + 1}",
        clock=clock,
    )
    return "rescheduled"
