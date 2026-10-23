"""Token refresh through the committed ledger, with credential and attempt fencing."""

import hashlib
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit import service as audit
from app.core.clock import Clock
from app.core.config import Settings
from app.core.security import TokenKeyRing, account_token_aad
from app.identity.models import Workspace
from app.inbox.system import system_context
from app.integrations.instagram import queries, registry
from app.integrations.instagram.errors import (
    ProviderAuthError,
    ProviderError,
    ProviderRateLimited,
    ProviderTransientError,
)
from app.integrations.instagram.models import SocialAccount
from app.jobs.models import Job
from app.jobs.queue import enqueue
from app.operations import health
from app.operations.models import Operation
from app.operations.payloads import RefreshTokenPayload
from app.operations.resolution import set_operation

REFRESH_LEASE = timedelta(minutes=2)


@dataclass(frozen=True)
class RefreshOutcome:
    kind: str = "done"
    error_code: str | None = None
    retry_after_seconds: float | None = None
    run_at: datetime | None = None


def eligible(account: SocialAccount, clock: Clock, settings: Settings) -> bool:
    now = clock.now()
    return (
        account.provider_kind == "meta"
        and account.status in ("connected", "degraded")
        and account.token_expires_at is not None
        and account.token_expires_at > now
        and account.token_expires_at
        <= now + timedelta(days=settings.token_refresh_days_before_expiry)
        and (
            account.token_refreshed_at is None
            or account.token_refreshed_at <= now - timedelta(hours=24)
        )
    )


def scan(session: Session, clock: Clock, settings: Settings) -> int:
    """Fan out once per account/UTC day, including completed/dead jobs in dedup."""
    if "meta" not in settings.instagram_providers:
        return 0
    accounts = session.scalars(
        select(SocialAccount)
        .join(Workspace, Workspace.id == SocialAccount.workspace_id)
        .where(
            Workspace.status == "active",
            SocialAccount.provider_kind == "meta",
            SocialAccount.status.in_(("connected", "degraded")),
        )
        .with_for_update(of=SocialAccount)
    ).all()
    count = 0
    for account in accounts:
        ctx = system_context(session, account.workspace_id, "operations.refresh")
        if ctx is None:
            continue
        if account.token_expires_at is not None and account.token_expires_at <= clock.now():
            health.handle_auth_error(session, clock, ctx, account)
        elif eligible(account, clock, settings):
            key = f"refresh_token:{account.id}:{clock.now().astimezone(UTC):%Y-%m-%d}"
            if session.scalar(select(Job.id).where(Job.dedup_key == key).limit(1)) is None:
                enqueue(
                    session,
                    "refresh_token",
                    RefreshTokenPayload(social_account_id=account.id),
                    workspace_id=account.workspace_id,
                    correlation_id=None,
                    dedup_key=key,
                    clock=clock,
                )
                count += 1
    session.commit()
    return count


def _fingerprint(account: SocialAccount) -> str:
    return hashlib.sha256(account.token_ciphertext or b"").hexdigest()


def execute_refresh(
    session_factory: Callable[[], Session],
    clock: Clock,
    settings: Settings,
    workspace_id: uuid.UUID,
    account_id: uuid.UUID,
    *,
    job_id: uuid.UUID | None = None,
) -> RefreshOutcome:
    with session_factory() as session:

        def no_refresh(code: str = "CONFLICT_STATE") -> RefreshOutcome:
            abandon(session, clock, workspace_id, job_id, code, account_id=account_id)
            return RefreshOutcome()

        if "meta" not in settings.instagram_providers:
            return no_refresh()
        workspace = session.get(Workspace, workspace_id)
        if workspace is None or workspace.status != "active":
            return no_refresh()
        account = queries.get_account_in_workspace(session, workspace_id, account_id, lock=True)
        ctx = system_context(session, workspace_id, "operations.refresh")
        if (
            account is None
            or ctx is None
            or account.provider_kind != "meta"
            or account.status not in ("connected", "degraded")
        ):
            return no_refresh()
        if account.token_expires_at is not None and account.token_expires_at <= clock.now():
            health.handle_auth_error(session, clock, ctx, account)
            return no_refresh("ACCOUNT_NEEDS_REAUTH")
        if not eligible(account, clock, settings):
            return no_refresh()
        key = f"refresh_token:{account.id}:{clock.now().astimezone(UTC):%Y-%m-%d}"
        stmt = select(Operation).where(
            Operation.workspace_id == workspace_id, Operation.idempotency_key == key
        )
        if job_id is not None:
            prior = session.scalar(
                select(Operation)
                .where(
                    Operation.workspace_id == workspace_id,
                    Operation.social_account_id == account_id,
                    Operation.operation_type == "refresh_token",
                    Operation.provider_ref["job_id"].astext == str(job_id),
                )
                .order_by(Operation.created_at)
                .limit(1)
            )
            if prior is not None:
                stmt = select(Operation).where(
                    Operation.workspace_id == workspace_id, Operation.id == prior.id
                )
        op = session.scalars(stmt.with_for_update()).one_or_none()
        if op is None:
            op = Operation(
                workspace_id=workspace_id,
                social_account_id=account.id,
                operation_type="refresh_token",
                idempotency_key=key,
                subject_type="social_account",
                subject_id=account.id,
                provider_kind="meta",
                status="pending",
                attempts=0,
                max_attempts=3,
                provider_ref={
                    "credential_fingerprint": _fingerprint(account),
                    **({"job_id": str(job_id)} if job_id else {}),
                },
                is_simulated=False,
            )
            session.add(op)
            session.flush()
        if op.status in ("succeeded", "failed", "cancelled"):
            return RefreshOutcome()
        if op.status == "in_progress":
            until = (op.started_at or clock.now()) + REFRESH_LEASE
            if until > clock.now():
                return RefreshOutcome("waiting", run_at=until)
            # Refresh is not visible; a lost worker may repeat the same credential.
            set_operation(clock, op, "retry", code="PROVIDER_UNAVAILABLE")
        if (
            op.provider_ref.get("credential_fingerprint") != _fingerprint(account)
            or op.attempts >= 3
        ):
            set_operation(
                clock,
                op,
                "fail",
                code="CONFLICT_STATE" if op.attempts < 3 else "PROVIDER_UNAVAILABLE",
            )
            audit.record(
                session,
                ctx,
                "operation.failed",
                "operation",
                op.id,
                {"error_code": op.last_error_code},
                is_simulated=False,
                clock=clock,
            )
            session.commit()
            return RefreshOutcome()
        set_operation(clock, op, "start")
        op.attempts += 1
        op.started_at = clock.now()
        op.next_attempt_at = None
        op_id, attempt, snapshot = op.id, op.attempts, account.token_ciphertext
        ref = registry.account_ref(account, settings)
        audit.record(
            session,
            ctx,
            "operation.started",
            "operation",
            op.id,
            {"operation_type": "refresh_token"},
            is_simulated=False,
            clock=clock,
        )
        session.commit()
    provider = registry.get_provider(
        "meta", settings=settings, session_factory=session_factory, clock=clock
    )
    failure: ProviderError | None = None
    ciphertext: bytes | None = None
    key_id: str | None = None
    expires_at: datetime | None = None
    try:
        result = provider.refresh_token(ref)
        if not result.access_token or result.expires_at is None or result.expires_at <= clock.now():
            raise ProviderTransientError("PROVIDER_UNAVAILABLE")
        ring = TokenKeyRing(
            settings.token_encryption_keys.get_secret_value(),
            settings.token_encryption_active_key_id,
        )
        ciphertext, key_id = ring.encrypt(
            result.access_token, aad=account_token_aad(workspace_id, account_id)
        )
        expires_at = result.expires_at
    except ProviderError as exc:
        failure = exc
    with session_factory() as session:
        account = queries.get_account_in_workspace(session, workspace_id, account_id, lock=True)
        op = session.scalars(
            select(Operation)
            .where(Operation.workspace_id == workspace_id, Operation.id == op_id)
            .with_for_update()
        ).one()
        ctx = system_context(session, workspace_id, "operations.refresh")
        if op.status != "in_progress" or op.attempts != attempt or ctx is None:
            return RefreshOutcome()
        if (
            account is None
            or account.status not in ("connected", "degraded")
            or account.token_ciphertext != snapshot
        ):
            set_operation(clock, op, "fail", code="CONFLICT_STATE")
            audit.record(
                session,
                ctx,
                "operation.failed",
                "operation",
                op.id,
                {"error_code": "CONFLICT_STATE"},
                is_simulated=False,
                clock=clock,
            )
            session.commit()
            return RefreshOutcome()
        if failure is None:
            account.token_ciphertext, account.token_key_id = ciphertext, key_id
            account.token_expires_at, account.token_refreshed_at = expires_at, clock.now()
            set_operation(clock, op, "succeed")
            op.result = {"expires_at": expires_at.isoformat() if expires_at else None}
            health.record_success(session, clock, ctx, account)
            for action, kind, subject in (
                ("operation.succeeded", "operation", op.id),
                ("social_account.token_refreshed", "social_account", account.id),
            ):
                audit.record(
                    session, ctx, action, kind, subject, {}, is_simulated=False, clock=clock
                )
            session.commit()
            return RefreshOutcome()
        code = (
            "ACCOUNT_NEEDS_REAUTH"
            if isinstance(failure, ProviderAuthError)
            else "PROVIDER_UNAVAILABLE"
        )
        retryable = isinstance(failure, (ProviderTransientError, ProviderRateLimited))
        delay = failure.retry_after_s if isinstance(failure, ProviderRateLimited) else None
        if isinstance(failure, ProviderRateLimited):
            code = "PROVIDER_RATE_LIMITED"
        set_operation(clock, op, "retry" if retryable and attempt < 3 else "fail", code=code)
        if isinstance(failure, ProviderAuthError):
            health.handle_auth_error(session, clock, ctx, account)
        elif retryable and not isinstance(failure, ProviderRateLimited):
            health.record_transient_failure(session, clock, ctx, account, code)
        audit.record(
            session,
            ctx,
            "operation.failed",
            "operation",
            op.id,
            {"error_code": code, "retryable": retryable},
            is_simulated=False,
            clock=clock,
        )
        session.commit()
        return RefreshOutcome("retry", code, delay) if retryable else RefreshOutcome()


def abandon(
    session: Session,
    clock: Clock,
    workspace_id: uuid.UUID,
    job_id: uuid.UUID | None,
    code: str,
    *,
    account_id: uuid.UUID | None = None,
) -> None:
    """A dead refresh job must not strand its non-visible operation in progress."""
    statement = select(Operation).where(
        Operation.workspace_id == workspace_id,
        Operation.operation_type == "refresh_token",
        Operation.status.in_(("in_progress", "retry_wait")),
    )
    if job_id is not None:
        statement = statement.where(Operation.provider_ref["job_id"].astext == str(job_id))
    elif account_id is not None:
        statement = statement.where(Operation.social_account_id == account_id)
    else:
        return
    for op in session.scalars(statement.with_for_update()):
        set_operation(clock, op, "fail", code=code)
        ctx = system_context(session, workspace_id, "operations.refresh")
        if ctx is not None:
            audit.record(
                session,
                ctx,
                "operation.failed",
                "operation",
                op.id,
                {"error_code": code},
                is_simulated=False,
                clock=clock,
            )
    session.commit()
