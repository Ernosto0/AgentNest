"""Social-account service: connect (mock), disconnect, state changes (state-machines.md §7).

``transition_account`` is the only function that changes ``social_accounts.status``; every
change is audited. It does not commit (the caller owns the transaction); ``connect_mock`` and
``disconnect`` are API entry points and do.
"""

import uuid

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.approvals import service as approvals
from app.audit import service as audit
from app.content import hooks
from app.content import notifications as content_notifications
from app.content import transitions as content_transitions
from app.content.models import ContentItem
from app.content.payload import publish_job_key
from app.core.clock import Clock
from app.core.config import Settings
from app.core.context import WorkspaceContext
from app.core.errors import AppError
from app.identity import repository as identity_repo
from app.identity.models import Workspace
from app.inbox import attention, drafts
from app.inbox.models import Conversation, InboundEvent, ReplyDraft
from app.integrations.instagram import queries
from app.integrations.instagram.mock import MockInstagramProvider
from app.integrations.instagram.models import OAuthState, SocialAccount
from app.integrations.instagram.transitions import apply_account_transition
from app.jobs.queue import cancel_queued, enqueue
from app.operations import conversation_deletion
from app.operations.models import Operation
from app.operations.payloads import ResumeAccountPayload
from app.operations.resolution import set_operation

MOCK_CAPABILITIES = {
    "messaging": True,
    "comment_reply": True,
    "comment_moderate": True,
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


def lock_workspace(session: Session, workspace_id: uuid.UUID) -> None:
    """Serialize account changes while allowing tenant inserts' FK KEY SHARE locks."""
    # PostgreSQL: key_share=True without read=True renders FOR NO KEY UPDATE.
    session.scalar(
        select(Workspace).where(Workspace.id == workspace_id).with_for_update(key_share=True)
    )


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
    reauthorized: bool = False,
    metadata: dict[str, object] | None = None,
) -> SocialAccount:
    """Move ``account`` to ``target`` (row locked by the caller) and audit it. No commit.

    The audit action defaults to ``social_account.<target>``; a caller whose change has a name of
    its own in the audit catalog (``account.reconnected``) passes it instead.
    """
    previous = account.status
    account.status = apply_account_transition(previous, target, reauthorized=reauthorized)
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
            **(metadata or {}),
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
    MockInstagramProvider.reauthorize(session, account)
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
    session: Session,
    clock: Clock,
    ctx: WorkspaceContext,
    account_id: uuid.UUID,
    *,
    delete_conversation_data: bool = False,
) -> SocialAccount:
    lock_workspace(session, ctx.workspace_id)
    # Match executor lock order: drafts/conversations and content before the account/ledger.
    from app.agent.control import adopt_threads
    from app.agent.jobs import enqueue_cleanup
    from app.agent.repository import AgentScopeError, scoped_account

    try:
        agent = scoped_account(session, ctx.workspace_id, account_id, lock=True)
    except AgentScopeError as exc:
        raise AppError("NOT_FOUND") from exc
    if agent.controller_mode == "agent":
        agent.state = "paused"
        agent.controller_epoch += 1
        adopt_threads(session, clock, agent)
        enqueue_cleanup(session, clock, ctx.workspace_id, account_id, agent.controller_epoch)
    conversation_ids = select(Conversation.id).where(
        Conversation.workspace_id == ctx.workspace_id, Conversation.social_account_id == account_id
    )
    account_drafts = session.scalars(
        select(ReplyDraft)
        .where(
            ReplyDraft.workspace_id == ctx.workspace_id,
            ReplyDraft.conversation_id.in_(conversation_ids),
        )
        .order_by(ReplyDraft.id)
        .with_for_update()
    ).all()
    conversations = session.scalars(
        select(Conversation)
        .where(
            Conversation.workspace_id == ctx.workspace_id,
            Conversation.social_account_id == account_id,
        )
        .order_by(Conversation.id)
        .with_for_update()
    ).all()
    items = session.scalars(
        select(ContentItem)
        .where(
            ContentItem.workspace_id == ctx.workspace_id,
            ContentItem.social_account_id == account_id,
            ContentItem.status.in_(("scheduled", "retry_scheduled")),
        )
        .order_by(ContentItem.id)
        .with_for_update()
    ).all()
    account = queries.get_account(session, ctx, account_id, lock=True)
    if account is None:
        raise AppError("NOT_FOUND")
    account.token_ciphertext = None
    account.token_key_id = None
    account.token_expires_at = None
    account.token_refreshed_at = None
    if account.status != "disconnected":
        transition_account(
            session,
            clock,
            ctx,
            account,
            "disconnected",
            metadata={"delete_conversation_data": delete_conversation_data},
        )
    elif not delete_conversation_data:
        # Preserve the existing terminal-state API contract; do not emit another audit.
        raise AppError("CONFLICT_STATE")
    elif (
        conversations
        or session.scalar(
            select(InboundEvent.id)
            .where(
                InboundEvent.workspace_id == ctx.workspace_id,
                InboundEvent.social_account_id == account_id,
                InboundEvent.payload.is_not(None),
            )
            .limit(1)
        )
        is not None
    ) and not conversation_deletion.pending(session, ctx.workspace_id, account_id=account_id):
        audit.record(
            session,
            ctx,
            "social_account.disconnected",
            "social_account",
            account_id,
            {"delete_conversation_data": True, "from": "disconnected"},
            is_simulated=account.is_simulated,
            clock=clock,
        )
    session.execute(
        update(OAuthState)
        .where(OAuthState.workspace_id == ctx.workspace_id, OAuthState.invalidated_at.is_(None))
        .values(invalidated_at=clock.now())
    )
    for draft in account_drafts:
        if draft.status not in ("queued", "pending_approval"):
            continue
        approvals.cancel_for_subject(
            session, clock, ctx, "reply_draft", draft.id, "ACCOUNT_DISCONNECTED"
        )
        drafts.transition(session, clock, ctx, draft, "cancel", reason="ACCOUNT_DISCONNECTED")
        cancel_queued(session, f"send_reply:{draft.id}", clock)
    for conversation in conversations:
        cancel_queued(session, f"draft_reply:{conversation.id}", clock)
        cancel_queued(session, f"draft_reply:{conversation.id}:requested", clock)
        attention.refresh(session, conversation)
    for item in items:
        cancel_queued(session, publish_job_key(item.id, item.version), clock)
        hooks.get().cancel_operation(session, clock, ctx, item, "ACCOUNT_DISCONNECTED")
        approvals.cancel_for_subject(
            session, clock, ctx, "content_item", item.id, "ACCOUNT_DISCONNECTED"
        )
        content_transitions.apply(session, clock, ctx, item, "hold", reason="ACCOUNT_UNAVAILABLE")
        content_notifications.notify(
            session, clock, ctx, item, content_notifications.ON_HOLD, reason="ACCOUNT_UNAVAILABLE"
        )
    # Only waiting effects are cancelled; in-flight/unknown effects retain their reconcilers.
    for op in session.scalars(
        select(Operation)
        .where(
            Operation.workspace_id == ctx.workspace_id,
            Operation.social_account_id == account_id,
            Operation.status.in_(("pending", "retry_wait")),
        )
        .with_for_update()
    ):
        set_operation(clock, op, "cancel", code="ACCOUNT_DISCONNECTED")
    if delete_conversation_data:
        conversation_deletion.request(session, clock, ctx.workspace_id, account_id)
    session.commit()
    return account
