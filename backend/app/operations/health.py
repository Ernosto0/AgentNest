"""Account health after provider results (workflows.md section G, state-machines.md section 7).

* A success resets the failure counter and its window, and closes a ``degraded`` account (a
  half-open probe that worked).
* ``CIRCUIT_FAILURE_THRESHOLD`` transient failures within ``CIRCUIT_WINDOW_MINUTES`` open the
  circuit: the account becomes ``degraded`` until ``degraded_until``; the executors leave the
  provider alone meanwhile (plan H10, H11). Rate limits do not count (G.1).
* An invalid token needs the owner (``needs_reauth``); a missing permission switches one
  capability off.

Nothing here commits and nothing here calls a provider.
"""

import uuid
from datetime import timedelta

from sqlalchemy.orm import Session

from app.core.clock import Clock
from app.core.config import get_settings
from app.core.context import WorkspaceContext
from app.integrations.instagram.models import SocialAccount
from app.jobs.queue import enqueue
from app.notifications import service as notifications
from app.operations.accounts import transition_account
from app.operations.payloads import ResumeAccountPayload


def record_success(
    session: Session,
    clock: Clock,
    ctx: WorkspaceContext,
    account: SocialAccount,
    *,
    correlation_id: uuid.UUID | None = None,
) -> None:
    """Any success resets the failure counter and its window. A success on a ``degraded``
    account (the half-open probe after the cooldown) closes the circuit."""
    account.consecutive_failures = 0
    account.failure_window_started_at = None
    if account.status == "degraded":
        recover(session, clock, ctx, account, correlation_id=correlation_id)


def recover(
    session: Session,
    clock: Clock,
    ctx: WorkspaceContext,
    account: SocialAccount,
    *,
    correlation_id: uuid.UUID | None = None,
) -> None:
    """``degraded`` -> ``connected``: tell the managers and make the queued replies due."""
    transition_account(session, clock, ctx, account, "connected", recovered=True)
    account.failure_window_started_at = None
    notifications.notify_permission_holders(
        session,
        clock,
        ctx,
        permission="integrations.manage",
        type="account.recovered",
        severity="info",
        params={"social_account_id": str(account.id), "username": account.username},
        subject_type="social_account",
        subject_id=account.id,
        dedup_key=f"account:{account.id}:connected",
        is_simulated=account.is_simulated,
    )
    enqueue(
        session,
        "resume_account",
        ResumeAccountPayload(social_account_id=account.id),
        workspace_id=ctx.workspace_id,
        correlation_id=correlation_id,
        dedup_key=f"resume_account:{account.id}",
        clock=clock,
    )


def extend_cooldown(clock: Clock, account: SocialAccount, code: str) -> None:
    """The account is still failing: leave it alone for another cooldown."""
    account.degraded_until = clock.now() + timedelta(
        minutes=get_settings().circuit_cooldown_minutes
    )
    account.last_error_code = code


def record_transient_failure(
    session: Session, clock: Clock, ctx: WorkspaceContext, account: SocialAccount, code: str
) -> None:
    """Count one transient failure (plan H10); open the circuit at the threshold."""
    settings = get_settings()
    now = clock.now()
    account.last_error_code = code
    if account.status == "degraded":  # a failed half-open probe: another cooldown
        extend_cooldown(clock, account, code)
        return
    window = timedelta(minutes=settings.circuit_window_minutes)
    started = account.failure_window_started_at
    if started is None or now - started > window:
        account.failure_window_started_at = now
        account.consecutive_failures = 1
    else:
        account.consecutive_failures += 1
    if account.status != "connected" or account.consecutive_failures < (
        settings.circuit_failure_threshold
    ):
        return
    transition_account(session, clock, ctx, account, "degraded", error_code=code)
    account.degraded_until = now + timedelta(minutes=settings.circuit_cooldown_minutes)
    notifications.notify_permission_holders(
        session,
        clock,
        ctx,
        permission="integrations.manage",
        type="account.degraded",
        severity="attention",
        params={"social_account_id": str(account.id), "username": account.username},
        subject_type="social_account",
        subject_id=account.id,
        dedup_key=f"account:{account.id}:degraded",
        is_simulated=account.is_simulated,
    )


def handle_auth_error(
    session: Session, clock: Clock, ctx: WorkspaceContext, account: SocialAccount
) -> None:
    """The token is no longer valid: the account needs the owner to connect it again."""
    if account.status in ("connected", "degraded"):
        transition_account(
            session, clock, ctx, account, "needs_reauth", error_code="ACCOUNT_NEEDS_REAUTH"
        )
    notifications.notify_permission_holders(
        session,
        clock,
        ctx,
        permission="integrations.manage",
        type="account.needs_reauth",
        severity="critical",
        params={"social_account_id": str(account.id), "username": account.username},
        subject_type="social_account",
        subject_id=account.id,
        dedup_key=f"account:{account.id}:needs_reauth",
        is_simulated=account.is_simulated,
    )


def handle_permission_error(
    session: Session,
    clock: Clock,
    ctx: WorkspaceContext,
    account: SocialAccount,
    capability: str = "messaging",
) -> None:
    """A required permission is missing: ``capability`` (messaging, or the publishing capability
    of a content type) is unavailable until it is granted. Tells the connection managers."""
    account.capabilities = {**account.capabilities, capability: False}
    account.last_error_code = "CAPABILITY_MISSING"
    notifications.notify_permission_holders(
        session,
        clock,
        ctx,
        permission="integrations.manage",
        type="account.permission_missing",
        severity="attention",
        params={
            "social_account_id": str(account.id),
            "username": account.username,
            "capability": capability,
        },
        subject_type="social_account",
        subject_id=account.id,
        dedup_key=f"account:{account.id}:permission_missing:{capability}",
        is_simulated=account.is_simulated,
    )
