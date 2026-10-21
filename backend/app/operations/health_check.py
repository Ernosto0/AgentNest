"""The health check of a ``degraded`` account (workflows.md section G.2, plan H12).

A cheap read (``get_account_profile``), not a ledger operation: INV-15 covers side effects only.
The provider call happens with **no transaction open**. The outcome decides the account:

* it works: ``connected`` (audit ``social_account.connected`` with ``recovered``), the managers
  are told, and ``resume_account`` makes the replies that waited due;
* a transient failure: the cooldown starts again;
* an invalid token: ``needs_reauth``.
"""

import uuid
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.core.clock import Clock
from app.core.config import Settings
from app.core.context import WorkspaceContext
from app.inbox.system import system_context
from app.integrations.instagram import queries
from app.integrations.instagram.base import AccountRef, InstagramProvider
from app.integrations.instagram.errors import ProviderAuthError, ProviderError
from app.integrations.instagram.models import SocialAccount
from app.integrations.instagram.registry import get_provider
from app.operations import health

Result = Literal["skipped", "recovered", "still_degraded", "needs_reauth"]


def run_health_check(
    session_factory: sessionmaker[Session],
    clock: Clock,
    settings: Settings,
    workspace_id: uuid.UUID,
    social_account_id: uuid.UUID,
    *,
    provider: InstagramProvider | None = None,
) -> Result:
    with session_factory() as session:
        account = queries.get_account_in_workspace(session, workspace_id, social_account_id)
        if account is None or account.status != "degraded":
            return "skipped"
        ref = AccountRef(account.id, workspace_id, account.external_account_id)
        kind = account.provider_kind
    reader = provider or get_provider(
        kind, settings=settings, session_factory=session_factory, clock=clock
    )
    error: ProviderError | None = None
    try:  # no transaction is open here
        reader.get_account_profile(ref)
    except ProviderError as exc:
        error = exc

    with session_factory() as session:
        locked = queries.get_account_in_workspace(
            session, workspace_id, social_account_id, lock=True
        )
        ctx = system_context(session, workspace_id, "operations.health")
        if locked is None or ctx is None or locked.status != "degraded":
            return "skipped"  # somebody else decided meanwhile
        result = _conclude(session, clock, ctx, locked, error)
        session.commit()
    return result


def _conclude(
    session: Session,
    clock: Clock,
    ctx: WorkspaceContext,
    account: SocialAccount,
    error: ProviderError | None,
) -> Result:
    if error is None:
        health.recover(session, clock, ctx, account)
        return "recovered"
    if isinstance(error, ProviderAuthError):
        health.handle_auth_error(session, clock, ctx, account)
        return "needs_reauth"
    health.extend_cooldown(clock, account, error.code)
    return "still_degraded"


def degraded_account_ids(session: Session) -> list[tuple[uuid.UUID, uuid.UUID]]:
    """``(workspace_id, account_id)`` of every degraded account (the scheduler's view)."""
    rows = session.execute(
        select(SocialAccount.workspace_id, SocialAccount.id).where(
            SocialAccount.status == "degraded"
        )
    ).all()
    return [(w, a) for w, a in rows]
