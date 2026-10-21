"""Operation detail for failure explanations (api-design.md section 2.8).

Owner and manager only (``system_health.view``). The answer is an allow-list: what the operation
was, how it ended and, from the error catalog, what happened and what to do next. Provider
payloads are never part of it. An id from another workspace is a 404 (INV-01).
"""

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import current_auth, require_membership
from app.core.context import WorkspaceContext
from app.core.db import get_db
from app.core.errors import AppError
from app.identity.service import AuthenticatedSession
from app.operations import explain
from app.operations.models import Operation
from app.operations.schemas import OperationOut

router = APIRouter(prefix="/workspaces/{workspace_id}/operations", tags=["operations"])


@router.get("/{operation_id}", response_model=OperationOut)
def get_operation(
    operation_id: uuid.UUID,
    ctx: WorkspaceContext = Depends(require_membership("system_health.view")),
    auth: AuthenticatedSession = Depends(current_auth),
    db: Session = Depends(get_db),
) -> OperationOut:
    operation = db.scalar(
        select(Operation).where(
            Operation.workspace_id == ctx.workspace_id, Operation.id == operation_id
        )
    )
    if operation is None:
        raise AppError("NOT_FOUND")
    explanation = explain.explain(operation, auth.user.ui_locale)
    return OperationOut(
        id=operation.id,
        type=operation.operation_type,
        status=operation.status,
        attempts=operation.attempts,
        last_error_code=operation.last_error_code,
        what=explanation.what if explanation else None,
        next=explanation.next if explanation else None,
        subject_type=operation.subject_type,
        subject_id=operation.subject_id,
        created_at=operation.created_at,
        completed_at=operation.completed_at,
        is_simulated=operation.is_simulated,
    )
