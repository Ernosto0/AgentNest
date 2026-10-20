"""How the content module reaches the operations ledger without importing it (plan.md section 1).

``app.content`` must not import ``app.operations`` (the publish executor imports content, not
the other way round). Cancel and hold need to cancel a waiting operation (plan.md G2) and the
item view shows the operation's state, so the operations module registers these two callables
**at startup** (``app.handlers``), the same pattern as the approval callbacks and the impact
handlers. Until something is registered the no-op default is used: no operation exists, and
nothing needs cancelling.

P5-02 only defines the hook. The registration comes with the publish executor.
"""

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session

from app.content.models import ContentItem
from app.core.clock import Clock
from app.core.context import WorkspaceContext


@dataclass(frozen=True)
class OperationSummary:
    """What the content API shows of the item's current publish operation."""

    status: str
    attempts: int
    next_attempt_at: datetime | None
    last_error_code: str | None


OperationSummaryHook = Callable[[Session, WorkspaceContext, ContentItem], OperationSummary | None]
CancelOperationHook = Callable[[Session, Clock, WorkspaceContext, ContentItem, str], bool]


def _no_summary(session: Session, ctx: WorkspaceContext, item: ContentItem) -> None:
    return None


def _no_cancel(
    session: Session, clock: Clock, ctx: WorkspaceContext, item: ContentItem, reason: str
) -> bool:
    return False


@dataclass(frozen=True)
class LedgerHooks:
    # (session, ctx, item) -> the operation of the item's current version, if any.
    operation_summary: OperationSummaryHook
    # (session, clock, ctx, item, reason) -> moves a pending/retry_wait operation to
    # ``cancelled``; True if one was cancelled. Runs in the caller's transaction.
    cancel_operation: CancelOperationHook


NO_LEDGER = LedgerHooks(operation_summary=_no_summary, cancel_operation=_no_cancel)

_hooks: LedgerHooks = NO_LEDGER


def register(hooks: LedgerHooks) -> None:
    """Install the ledger hooks (once, at startup)."""
    global _hooks
    if _hooks is not NO_LEDGER:
        raise ValueError("content ledger hooks are already registered")
    _hooks = hooks


def get() -> LedgerHooks:
    return _hooks


@contextmanager
def hooks_snapshot(*, clear: bool = False) -> Iterator[None]:
    """Restore the registration on exit (tests); ``clear`` starts from the no-op default."""
    global _hooks
    saved = _hooks
    if clear:
        _hooks = NO_LEDGER
    try:
        yield
    finally:
        _hooks = saved
