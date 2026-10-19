"""Account health after provider results (workflows.md §G.1, simplified for Phase 4).

Phase 4 counts consecutive failures and reacts to an invalid token or a missing permission.
The automatic ``degraded`` state and the circuit breaker arrive in Phase 6.
"""

from sqlalchemy.orm import Session

from app.core.clock import Clock
from app.core.context import WorkspaceContext
from app.integrations.instagram.models import SocialAccount
from app.notifications import service as notifications
from app.operations.accounts import transition_account


def record_success(account: SocialAccount) -> None:
    """Any success resets the failure counter."""
    account.consecutive_failures = 0


def record_transient_failure(account: SocialAccount, code: str) -> None:
    account.consecutive_failures += 1
    account.last_error_code = code


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
        dedup_key=f"account-reauth:{account.id}",
        is_simulated=account.is_simulated,
    )


def handle_permission_error(account: SocialAccount) -> None:
    """A required permission is missing: messaging is unavailable until it is granted."""
    account.capabilities = {**account.capabilities, "messaging": False}
    account.last_error_code = "CAPABILITY_MISSING"
