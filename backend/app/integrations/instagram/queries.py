"""Read-only account lookups. They carry no policy, so ``knowledge`` (readiness), ``inbox``
(webhook resolution) and ``operations`` can all use them without owning the table."""

import uuid

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core.context import WorkspaceContext
from app.core.db import set_tenant_context
from app.integrations.instagram.models import SocialAccount


def get_account(
    session: Session, ctx: WorkspaceContext, account_id: uuid.UUID, *, lock: bool = False
) -> SocialAccount | None:
    stmt = select(SocialAccount).where(
        SocialAccount.workspace_id == ctx.workspace_id, SocialAccount.id == account_id
    )
    return session.scalars(stmt.with_for_update() if lock else stmt).one_or_none()


def get_account_in_workspace(
    session: Session, workspace_id: uuid.UUID, account_id: uuid.UUID, *, lock: bool = False
) -> SocialAccount | None:
    """For jobs, which carry a workspace id but no request context."""
    stmt = select(SocialAccount).where(
        SocialAccount.workspace_id == workspace_id, SocialAccount.id == account_id
    )
    return session.scalars(stmt.with_for_update() if lock else stmt).one_or_none()


def list_accounts(session: Session, ctx: WorkspaceContext) -> list[SocialAccount]:
    stmt = (
        select(SocialAccount)
        .where(SocialAccount.workspace_id == ctx.workspace_id)
        .order_by(SocialAccount.created_at.desc(), SocialAccount.id)
    )
    return list(session.scalars(stmt))


def get_active_for_workspace(
    session: Session, workspace_id: uuid.UUID, *, lock: bool = False
) -> SocialAccount | None:
    """The workspace's one non-disconnected account, if any."""
    stmt = select(SocialAccount).where(
        SocialAccount.workspace_id == workspace_id, SocialAccount.status != "disconnected"
    )
    return session.scalars(stmt.with_for_update() if lock else stmt).one_or_none()


def resolve_by_external(
    session: Session, provider_kind: str, external_account_id: str
) -> SocialAccount | None:
    """The webhook's receiving account. The workspace is resolved from this and nothing else;
    the provider kind comes from the webhook path (ADR-010).

    When running under tenant RLS without an active app.workspace_id, this uses the narrow
    SECURITY DEFINER function resolve_social_account_by_external to resolve (id, workspace_id)
    and binds tenant context before returning the SocialAccount entity (ADR-025 §1.4).
    """
    bind = session.get_bind()
    if bind.dialect.name == "postgresql":
        row = session.execute(
            text(
                "SELECT id, workspace_id, status "
                "FROM public.resolve_social_account_by_external(:kind, :ext_id)"
            ),
            {"kind": provider_kind, "ext_id": external_account_id},
        ).first()
        if row is None:
            return None
        set_tenant_context(session, row.workspace_id)
        return session.get(SocialAccount, row.id)

    stmt = (
        select(SocialAccount)
        .where(
            SocialAccount.provider_kind == provider_kind,
            SocialAccount.external_account_id == external_account_id,
        )
        .order_by((SocialAccount.status == "disconnected"), SocialAccount.created_at.desc())
        .limit(1)
    )
    return session.scalars(stmt).first()


def has_connected_account(session: Session, workspace_id: uuid.UUID) -> bool:
    """Readiness: an account that can still be used (``connected`` or briefly ``degraded``)."""
    stmt = select(SocialAccount.id).where(
        SocialAccount.workspace_id == workspace_id,
        SocialAccount.status.in_(("connected", "degraded")),
    )
    return session.scalars(stmt).first() is not None
