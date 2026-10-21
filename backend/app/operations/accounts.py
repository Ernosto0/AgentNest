"""Social-account service: connect (mock), disconnect, state changes (state-machines.md §7).

``transition_account`` is the only function that changes ``social_accounts.status``; every
change is audited. It does not commit (the caller owns the transaction); ``connect_mock`` and
``disconnect`` are API entry points and do.
"""

import uuid

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.audit import service as audit
from app.core.clock import Clock
from app.core.config import Settings
from app.core.context import WorkspaceContext
from app.core.errors import AppError
from app.identity import repository as identity_repo
from app.integrations.instagram import queries
from app.integrations.instagram.models import SocialAccount
from app.integrations.instagram.transitions import apply_account_transition
from app.jobs.queue import enqueue
from app.operations.payloads import ResumeAccountPayload

MOCK_CAPABILITIES = {
    "messaging": True,
    "publish_feed_image": True,
    "publish_story_image": True,
}


def mock_connect_allowed(settings: Settings, ctx: WorkspaceContext) -> bool:
    """The mock provider is enabled, and either this is not production or the workspace is a
    demo workspace on a deployment that allows simulated workspaces."""
    if "mock" not in settings.instagram_providers:
        return False
    if settings.app_env != "production":
        return True
    return ctx.is_demo and settings.allow_simulated_workspaces


def transition_account(
    session: Session,
    clock: Clock,
    ctx: WorkspaceContext,
    account: SocialAccount,
    target: str,
    *,
    error_code: str | None = None,
    audit_action: str | None = None,
    recovered: bool = False,
) -> SocialAccount:
    """Move ``account`` to ``target`` (row locked by the caller) and audit it. No commit.

    The audit action defaults to ``social_account.<target>``; a caller whose change has a name of
    its own in the audit catalog (``account.reconnected``) passes it instead.
    """
    previous = account.status
    account.status = apply_account_transition(previous, target)
    now = clock.now()
    if target == "connected":
        account.connected_at = account.connected_at or now
        account.disconnected_at = None
        account.degraded_until = None
        account.last_error_code = None
        account.consecutive_failures = 0
        account.failure_window_started_at = None
    elif target == "disconnected":
        account.disconnected_at = now
    if error_code is not None:
        account.last_error_code = error_code
    session.flush()
    audit.record(
        session,
        ctx,
        audit_action or f"social_account.{target}",
        "social_account",
        account.id,
        {
            "from": previous,
            "provider_kind": account.provider_kind,
            "error_code": error_code,
            **({"recovered": True} if recovered else {}),
        },
        is_simulated=account.is_simulated,
        clock=clock,
    )
    return account


def connect_mock(
    session: Session,
    clock: Clock,
    ctx: WorkspaceContext,
    settings: Settings,
    *,
    username: str | None = None,
) -> SocialAccount:
    """Connect the workspace's simulated Instagram account and commit."""
    if not mock_connect_allowed(settings, ctx):
        raise AppError("FORBIDDEN", permission="integrations.mock")
    workspace = identity_repo.get_workspace(session, ctx)
    if workspace is None:
        raise AppError("NOT_FOUND")
    if queries.get_active_for_workspace(session, ctx.workspace_id) is not None:
        raise AppError("CONFLICT_STATE", entity="social_account", reason="account_exists")
    account = SocialAccount(
        workspace_id=ctx.workspace_id,
        platform="instagram",
        provider_kind="mock",
        external_account_id=f"mock-{uuid.uuid4().hex[:12]}",
        username=username or f"{workspace.slug}.demo",
        status="connected",
        capabilities=dict(MOCK_CAPABILITIES),
        granted_scopes=[],
        connected_at=clock.now(),
    )
    try:
        with session.begin_nested():
            session.add(account)
    except IntegrityError as exc:  # raced with another connect
        raise AppError("CONFLICT_STATE", entity="social_account", reason="account_exists") from exc
    audit.record(
        session,
        ctx,
        "social_account.connected",
        "social_account",
        account.id,
        {"from": None, "provider_kind": "mock"},
        is_simulated=True,
        clock=clock,
    )
    session.commit()
    return account


def reconnect_mock(
    session: Session,
    clock: Clock,
    ctx: WorkspaceContext,
    settings: Settings,
    account_id: uuid.UUID,
) -> SocialAccount:
    """Connect a simulated account again after its token was revoked, and commit.

    ``needs_reauth`` becomes ``connected`` for the **same** external account. The replies that
    waited for the connection are resumed by the ``resume_account`` job enqueued here, in the same
    transaction (a transactional outbox). A real (Meta) account is reconnected through OAuth in
    Phase 7, never here. The simulator is told too (``reauthorize``): the revoked-token rules
    that made the account need re-authorisation are removed, as the owner's new token would
    end them.
    """
    if not mock_connect_allowed(settings, ctx):
        raise AppError("FORBIDDEN", permission="integrations.mock")
    account = queries.get_account(session, ctx, account_id, lock=True)
    if account is None:
        raise AppError("NOT_FOUND")
    if account.provider_kind != "mock":
        raise AppError("CONFLICT_STATE", entity="social_account", reason="not_a_mock_account")
    if account.status != "needs_reauth":  # connected, degraded or disconnected: nothing to resume
        raise AppError(
            "CONFLICT_STATE", entity="social_account", status=account.status, target="connected"
        )
    transition_account(
        session, clock, ctx, account, "connected", audit_action="account.reconnected"
    )
    enqueue(
        session,
        "resume_account",
        ResumeAccountPayload(social_account_id=account.id),
        workspace_id=ctx.workspace_id,
        correlation_id=None,
        dedup_key=f"resume_account:{account.id}",
        clock=clock,
    )
    session.commit()
    return account


def disconnect(
    session: Session, clock: Clock, ctx: WorkspaceContext, account_id: uuid.UUID
) -> SocialAccount:
    account = queries.get_account(session, ctx, account_id, lock=True)
    if account is None:
        raise AppError("NOT_FOUND")
    transition_account(session, clock, ctx, account, "disconnected")
    session.commit()
    return account
