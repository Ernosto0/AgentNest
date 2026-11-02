"""Data-rights export endpoints (P8-05, ADR-025 §3.1).

Owner-only (data.export permission), workspace-scoped conversation and customer exports.
"""

import uuid
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_clock, require_membership
from app.core.clock import Clock
from app.core.context import WorkspaceContext
from app.core.db import get_db
from app.operations import data_rights

router = APIRouter(prefix="/workspaces/{workspace_id}", tags=["data-rights"])


@router.get(
    "/conversations/{conversation_id}/export",
    summary="Export conversation data subject records (Owner only)",
)
def export_conversation_endpoint(
    conversation_id: uuid.UUID,
    ctx: WorkspaceContext = Depends(require_membership("data.export")),
    db: Session = Depends(get_db),
    clock: Clock = Depends(get_clock),
) -> dict[str, Any]:
    """Export all messages, drafts, approvals, memory, and linked comments for a conversation."""
    return data_rights.export_conversation(db, clock, ctx, conversation_id)


@router.get(
    "/customers/{customer_identity_id}/export",
    summary="Export customer data subject records (Owner only)",
)
def export_customer_endpoint(
    customer_identity_id: uuid.UUID,
    ctx: WorkspaceContext = Depends(require_membership("data.export")),
    db: Session = Depends(get_db),
    clock: Clock = Depends(get_clock),
) -> dict[str, Any]:
    """Export all conversations, messages, memories, and public comments for a customer identity."""
    return data_rights.export_customer(db, clock, ctx, customer_identity_id)
