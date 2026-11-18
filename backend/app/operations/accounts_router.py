"""Social-account routes (api-design.md §2.9)."""

import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, StrictBool
from sqlalchemy.orm import Session

from app.api.deps import get_app_settings, get_clock, require_membership
from app.audit import service as audit
from app.core.clock import Clock
from app.core.config import Settings
from app.core.context import WorkspaceContext
from app.core.db import get_db
from app.core.errors import AppError
from app.core.pagination import Page
from app.integrations.instagram import queries
from app.integrations.instagram.models import SocialAccount
from app.integrations.instagram.oauth import COMMENTS_SCOPE, compute_capabilities
from app.operations import accounts, oauth_service
from app.operations.schemas import (
    DisconnectRequest,
    InstagramConnectOut,
    InstagramConnectRequest,
    MockAccountCreate,
    SocialAccountOut,
)

router = APIRouter(prefix="/workspaces/{workspace_id}/social-accounts", tags=["integrations"])


@router.post("/instagram/connect", response_model=InstagramConnectOut)
def connect_instagram(
    body: InstagramConnectRequest | None = None,
    ctx: WorkspaceContext = Depends(require_membership("integrations.manage")),
    db: Session = Depends(get_db),
    clock: Clock = Depends(get_clock),
    settings: Settings = Depends(get_app_settings),
) -> InstagramConnectOut:
    body = body or InstagramConnectRequest()
    return InstagramConnectOut(
        authorize_url=oauth_service.start_connect(
            db, clock, ctx, settings, purpose=body.purpose, social_account_id=body.social_account_id
        )
    )


def account_out(account: SocialAccount) -> SocialAccountOut:
    return SocialAccountOut(
        id=account.id,
        platform=account.platform,
        provider_kind=account.provider_kind,
        username=account.username,
        status=account.status,
        capabilities=account.capabilities,
        comment_automation_enabled=account.comment_automation_enabled,
        connection_expires_at=account.token_expires_at,
        last_error_code=account.last_error_code,
        degraded_until=account.degraded_until,
        is_simulated=account.is_simulated,
    )


@router.get("", response_model=Page[SocialAccountOut])
def list_accounts(
    ctx: WorkspaceContext = Depends(require_membership()),
    db: Session = Depends(get_db),
) -> Page[SocialAccountOut]:
    return Page(items=[account_out(a) for a in queries.list_accounts(db, ctx)])


@router.post("/mock", response_model=SocialAccountOut, status_code=201)
def connect_mock_account(
    body: MockAccountCreate | None = None,
    ctx: WorkspaceContext = Depends(require_membership("integrations.manage")),
    db: Session = Depends(get_db),
    clock: Clock = Depends(get_clock),
    settings: Settings = Depends(get_app_settings),
) -> SocialAccountOut:
    username = body.username if body else None
    return account_out(accounts.connect_mock(db, clock, ctx, settings, username=username))


@router.post("/{account_id}/reconnect", response_model=SocialAccountOut)
def reconnect_account(
    account_id: uuid.UUID,
    ctx: WorkspaceContext = Depends(require_membership("integrations.manage")),
    db: Session = Depends(get_db),
    clock: Clock = Depends(get_clock),
    settings: Settings = Depends(get_app_settings),
) -> SocialAccountOut:
    return account_out(accounts.reconnect_mock(db, clock, ctx, settings, account_id))


@router.post("/{account_id}/disconnect", response_model=SocialAccountOut)
def disconnect_account(
    account_id: uuid.UUID,
    body: DisconnectRequest | None = None,
    ctx: WorkspaceContext = Depends(require_membership("integrations.manage")),
    db: Session = Depends(get_db),
    clock: Clock = Depends(get_clock),
) -> SocialAccountOut:
    return account_out(
        accounts.disconnect(
            db,
            clock,
            ctx,
            account_id,
            delete_conversation_data=body.delete_conversation_data if body else False,
        )
    )


comment_automation_router = APIRouter(
    prefix="/workspaces/{workspace_id}/accounts", tags=["integrations"]
)


class CommentAutomationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: StrictBool


@comment_automation_router.put("/{account_id}/comment-automation", response_model=SocialAccountOut)
def set_comment_automation(
    account_id: uuid.UUID,
    body: CommentAutomationRequest,
    ctx: WorkspaceContext = Depends(require_membership("integrations.manage")),
    db: Session = Depends(get_db),
    clock: Clock = Depends(get_clock),
    settings: Settings = Depends(get_app_settings),
) -> SocialAccountOut:
    account = queries.get_account_in_workspace(db, ctx.workspace_id, account_id, lock=True)
    if account is None:
        raise AppError("NOT_FOUND")
    if ctx.role != "owner":
        raise AppError("FORBIDDEN", permission="integrations.manage")
    if account.provider_kind != "meta":
        raise AppError("CONFLICT_STATE", reason="real_account_required")
    if body.enabled and (
        account.status not in {"connected", "degraded"}
        or COMMENTS_SCOPE not in account.granted_scopes
        or account.capabilities.get("comments_permission") is not True
    ):
        raise AppError("CONFLICT_STATE", reason="comments_permission_missing")
    before = account.comment_automation_enabled
    account.comment_automation_enabled = body.enabled
    account.capabilities = compute_capabilities(
        account.granted_scopes,
        settings.meta_stories_enabled,
        body.enabled,
        settings.meta_human_agent_enabled,
    )
    if before != body.enabled:
        audit.record(
            db,
            ctx,
            "account.comment_automation_changed",
            "social_account",
            account.id,
            {"from": before, "to": body.enabled},
            clock=clock,
        )
    db.commit()
    return account_out(account)
