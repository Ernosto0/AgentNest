"""User-bound OAuth orchestration with short committed transactions around network work."""

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.audit import service as audit
from app.core.clock import Clock
from app.core.config import Settings
from app.core.context import ActorRef, WorkspaceContext
from app.core.errors import AppError
from app.core.ids import new_id
from app.core.security import TokenKeyRing, account_token_aad, generate_token, hash_token
from app.identity import repository as identity_repo
from app.identity import service as identity_service
from app.identity.models import User, WorkspaceMember
from app.identity.permissions import has_permission
from app.integrations.instagram import oauth, queries, registry
from app.integrations.instagram.base import AccountRef
from app.integrations.instagram.errors import ProviderAuthError, ProviderError
from app.integrations.instagram.models import OAuthState, SocialAccount
from app.jobs.queue import enqueue
from app.operations import conversation_deletion
from app.operations.accounts import lock_workspace, transition_account
from app.operations.payloads import ResumeAccountPayload


@dataclass(frozen=True)
class CallbackOutcome:
    workspace_id: uuid.UUID
    error_code: str | None = None


def _context(session: Session, workspace_id: uuid.UUID, user_id: uuid.UUID) -> WorkspaceContext:
    session.scalar(
        select(WorkspaceMember)
        .where(WorkspaceMember.workspace_id == workspace_id, WorkspaceMember.user_id == user_id)
        .with_for_update()
    )
    found = identity_repo.get_membership(session, workspace_id, user_id)
    user = session.get(User, user_id)
    if found is None or found[1].status != "active" or user is None or not user.is_active:
        raise AppError("FORBIDDEN")
    member, workspace = found
    if not has_permission(member.role, "integrations.manage"):
        raise AppError("FORBIDDEN")
    return identity_service.workspace_context(workspace, ActorRef.user(user_id), member.role)


def start_connect(
    session: Session,
    clock: Clock,
    ctx: WorkspaceContext,
    settings: Settings,
    *,
    purpose: str = "connect",
    social_account_id: uuid.UUID | None = None,
) -> str:
    if "meta" not in settings.instagram_providers:
        raise AppError("FORBIDDEN")
    if ctx.actor.id is None or purpose not in ("connect", "reconnect"):
        raise AppError("VALIDATION_FAILED")
    user_id = uuid.UUID(ctx.actor.id)
    _context(session, ctx.workspace_id, user_id)
    if conversation_deletion.pending(session, ctx.workspace_id):
        raise AppError("CONFLICT_STATE")
    if purpose == "reconnect":
        account = (
            queries.get_account(session, ctx, social_account_id, lock=True)
            if social_account_id
            else None
        )
        if account is None:
            raise AppError("NOT_FOUND")
        if account.provider_kind != "meta" or account.status == "disconnected":
            raise AppError("CONFLICT_STATE")
    elif social_account_id is not None:
        raise AppError("VALIDATION_FAILED")
    elif queries.get_active_for_workspace(session, ctx.workspace_id) is not None:
        raise AppError("CONFLICT_STATE")
    raw = generate_token()
    session.add(
        OAuthState(
            workspace_id=ctx.workspace_id,
            user_id=user_id,
            state_hash=hash_token(raw),
            purpose=purpose,
            social_account_id=social_account_id,
            expires_at=clock.now() + timedelta(minutes=10),
            created_at=clock.now(),
        )
    )
    session.commit()
    return oauth.build_authorize_url(settings, raw)


def complete_callback(
    session_factory: Callable[[], Session],
    clock: Clock,
    settings: Settings,
    user_id: uuid.UUID,
    *,
    code: str | None,
    state: str | None,
    error: str | None,
) -> CallbackOutcome:
    if not state or len(state) > 512:
        raise AppError("OAUTH_STATE_INVALID")
    with session_factory() as session:
        row = session.scalars(
            select(OAuthState).where(OAuthState.state_hash == hash_token(state)).with_for_update()
        ).one_or_none()
        if (
            row is None
            or row.user_id != user_id
            or row.used_at is not None
            or row.invalidated_at is not None
            or row.expires_at <= clock.now()
        ):
            raise AppError("OAUTH_STATE_INVALID")
        row.used_at = clock.now()
        workspace_id, state_id, account_id = row.workspace_id, row.id, row.social_account_id
        purpose = row.purpose
        account = (
            queries.get_account_in_workspace(session, workspace_id, account_id)
            if account_id
            else None
        )
        snapshot = (account.token_ciphertext, account.token_refreshed_at) if account else None
        session.commit()  # single use, even permission revocation, denial or downstream failure
        try:
            _context(session, workspace_id, user_id)
            if "meta" not in settings.instagram_providers:
                raise AppError("FORBIDDEN")
        except AppError as exc:
            return CallbackOutcome(workspace_id, exc.code)
    try:
        if error is not None or not code or len(code) > 4096:
            raise AppError("OAUTH_STATE_INVALID")
        exchanged = oauth.exchange_code_for_long_lived_token(settings, code)
        provider = registry.get_provider(
            "meta", settings=settings, session_factory=session_factory, clock=clock
        )
        profile = provider.get_account_profile(
            AccountRef(
                account_id or new_id(),
                workspace_id,
                exchanged.ig_user_id,
                lambda: exchanged.access_token,
            )
        )
        if profile.external_account_id != exchanged.ig_user_id:
            raise AppError("ACCOUNT_MISMATCH")
        with session_factory() as session:
            # Serialize workspace changes; indexes arbitrate cross-workspace races.
            lock_workspace(session, workspace_id)
            ctx = _context(session, workspace_id, user_id)
            if conversation_deletion.pending(session, workspace_id):
                raise AppError("CONFLICT_STATE")
            current_state = session.get(OAuthState, state_id)
            if current_state is None or current_state.invalidated_at is not None:
                raise AppError("OAUTH_STATE_INVALID")
            active = queries.get_active_for_workspace(session, workspace_id)
            if purpose == "reconnect":
                account = (
                    queries.get_account_in_workspace(session, workspace_id, account_id, lock=True)
                    if account_id
                    else None
                )
                if (
                    account is None
                    or account.status == "disconnected"
                    or account.provider_kind != "meta"
                ):
                    raise AppError("CONFLICT_STATE")
                if snapshot != (account.token_ciphertext, account.token_refreshed_at):
                    raise AppError("CONFLICT_STATE")
                if account.external_account_id != profile.external_account_id:
                    raise AppError("ACCOUNT_MISMATCH")
            else:
                if active is not None:
                    raise AppError("CONFLICT_STATE")
                account = session.scalars(
                    select(SocialAccount)
                    .where(
                        SocialAccount.workspace_id == workspace_id,
                        SocialAccount.provider_kind == "meta",
                        SocialAccount.external_account_id == profile.external_account_id,
                        SocialAccount.status == "disconnected",
                    )
                    .order_by(SocialAccount.created_at.desc(), SocialAccount.id)
                    .limit(1)
                    .with_for_update()
                ).first()
                if account is None:
                    account = SocialAccount(
                        id=new_id(),
                        workspace_id=workspace_id,
                        provider_kind="meta",
                        external_account_id=profile.external_account_id,
                        status="connected",
                    )
                    session.add(account)
            if account is None:
                raise AppError("CONFLICT_STATE")
            account.username = profile.username
            account.capabilities = oauth.compute_capabilities(
                exchanged.granted_scopes, settings.meta_stories_enabled
            )
            account.granted_scopes = exchanged.granted_scopes
            ring = TokenKeyRing(
                settings.token_encryption_keys.get_secret_value(),
                settings.token_encryption_active_key_id,
            )
            account.token_ciphertext, account.token_key_id = ring.encrypt(
                exchanged.access_token, aad=account_token_aad(workspace_id, account.id)
            )
            account.token_expires_at = clock.now() + timedelta(seconds=exchanged.expires_in_seconds)
            account.token_refreshed_at = clock.now()
            if purpose == "reconnect" or account.status == "disconnected":
                transition_account(
                    session,
                    clock,
                    ctx,
                    account,
                    "connected",
                    reauthorized=True,
                    audit_action="account.reconnected"
                    if purpose == "reconnect"
                    else "social_account.connected",
                )
            else:
                account.connected_at = clock.now()
                account.disconnected_at = None
                account.last_error_code = None
                session.flush()
                audit.record(
                    session,
                    ctx,
                    "account.reconnected" if purpose == "reconnect" else "social_account.connected",
                    "social_account",
                    account.id,
                    {"provider_kind": "meta"},
                    is_simulated=False,
                    clock=clock,
                )
            if purpose == "reconnect":
                enqueue(
                    session,
                    "resume_account",
                    ResumeAccountPayload(social_account_id=account.id),
                    workspace_id=workspace_id,
                    correlation_id=None,
                    dedup_key=f"resume_account:{account.id}",
                    clock=clock,
                )
            session.commit()
        return CallbackOutcome(workspace_id)
    except IntegrityError:
        return CallbackOutcome(workspace_id, "CONFLICT_STATE")
    except AppError as exc:
        return CallbackOutcome(workspace_id, exc.code)
    except ProviderAuthError:
        return CallbackOutcome(workspace_id, "ACCOUNT_NEEDS_REAUTH")
    except ProviderError:
        return CallbackOutcome(workspace_id, "PROVIDER_UNAVAILABLE")
