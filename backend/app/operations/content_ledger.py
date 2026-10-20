"""How the content module reaches the operations ledger (plan.md section 1, G2).

``app.content`` cannot import ``app.operations``, so it asks two callables registered at startup
(``app.handlers``) that live here: the summary of an item's current publish operation, and the
cancellation of an operation that is only waiting (``pending`` / ``retry_wait``). Cancelling or
holding an item therefore also releases its ledger row, in the caller's transaction.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.content import hooks
from app.content.models import ContentItem
from app.content.payload import publish_job_key
from app.core.clock import Clock
from app.core.context import WorkspaceContext
from app.operations.models import Operation
from app.operations.resolution import set_operation


def _operation(
    session: Session, ctx: WorkspaceContext, item: ContentItem, *, lock: bool = False
) -> Operation | None:
    statement = select(Operation).where(
        Operation.workspace_id == ctx.workspace_id,
        Operation.idempotency_key == publish_job_key(item.id, item.version),
    )
    return session.scalars(statement.with_for_update() if lock else statement).one_or_none()


def operation_summary(
    session: Session, ctx: WorkspaceContext, item: ContentItem
) -> hooks.OperationSummary | None:
    """The operation of the item's current version, as the content API shows it."""
    op = _operation(session, ctx, item)
    if op is None:
        return None
    return hooks.OperationSummary(
        status=op.status,
        attempts=op.attempts,
        next_attempt_at=op.next_attempt_at,
        last_error_code=op.last_error_code,
    )


def cancel_operation(
    session: Session, clock: Clock, ctx: WorkspaceContext, item: ContentItem, reason: str
) -> bool:
    """Cancel the item's waiting operation. An operation that is running (``in_progress``,
    ``outcome_unknown``) or finished is left alone; True if one was cancelled."""
    op = _operation(session, ctx, item, lock=True)
    if op is None or op.status not in ("pending", "retry_wait"):
        return False
    set_operation(clock, op, "cancel")
    return True


hooks.register(
    hooks.LedgerHooks(operation_summary=operation_summary, cancel_operation=cancel_operation)
)
