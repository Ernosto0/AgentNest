"""Social-account routes (api-design.md §2.9)."""

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_app_settings, get_clock, require_membership
from app.core.clock import Clock
from app.core.config import Settings
from app.core.context import WorkspaceContext
from app.core.db import get_db
from app.core.pagination import Page
from app.integrations.instagram import queries
from app.integrations.instagram.models import SocialAccount
from app.operations import accounts
from app.operations.schemas import MockAccountCreate, SocialAccountOut

router = APIRouter(prefix="/workspaces/{workspace_id}/social-accounts", tags=["integrations"])


def account_out(account: SocialAccount) -> SocialAccountOut:
    return SocialAccountOut(
        id=account.id,
        platform=account.platform,
        provider_kind=account.provider_kind,
        username=account.username,
        status=account.status,
        capabilities=account.capabilities,
        connection_expires_at=account.token_expires_at,
        last_error_code=account.last_error_code,
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
    ctx: WorkspaceContext = Depends(require_membership("integrations.manage")),
    db: Session = Depends(get_db),
    clock: Clock = Depends(get_clock),
) -> SocialAccountOut:
    return account_out(accounts.disconnect(db, clock, ctx, account_id))
