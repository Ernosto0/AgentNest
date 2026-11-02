"""Data-rights export, erasure, and workspace deletion lifecycle endpoints (P8-05).

Owner-only (data.export, data.delete, workspace.manage permissions), workspace-scoped.
"""

import uuid
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_app_settings, get_clock, require_membership
from app.core.clock import Clock
from app.core.config import Settings
from app.core.context import WorkspaceContext
from app.core.db import get_db
from app.operations import data_rights, workspace_lifecycle

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


@router.delete(
    "/conversations/{conversation_id}",
    summary="Erase conversation data subject records (Owner only)",
)
def erase_conversation_endpoint(
    conversation_id: uuid.UUID,
    ctx: WorkspaceContext = Depends(require_membership("data.delete")),
    db: Session = Depends(get_db),
    clock: Clock = Depends(get_clock),
) -> dict[str, Any]:
    """Idempotently erase or redact conversation records and emit durable tombstone."""
    return data_rights.erase_conversation(db, clock, ctx, conversation_id)


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


@router.delete(
    "/customers/{customer_identity_id}",
    summary="Erase customer data subject records (Owner only)",
)
def erase_customer_endpoint(
    customer_identity_id: uuid.UUID,
    ctx: WorkspaceContext = Depends(require_membership("data.delete")),
    db: Session = Depends(get_db),
    clock: Clock = Depends(get_clock),
) -> dict[str, Any]:
    """Idempotently erase customer records across all conversations and memories."""
    return data_rights.erase_customer(db, clock, ctx, customer_identity_id)


# --- Workspace Deletion Lifecycle (7-Day Grace Period) -----------------------------


@router.post(
    "/delete-request",
    summary="Request workspace deletion with 7-day grace period (Owner only)",
)
def request_workspace_deletion_endpoint(
    ctx: WorkspaceContext = Depends(require_membership("workspace.manage")),
    db: Session = Depends(get_db),
    clock: Clock = Depends(get_clock),
    settings: Settings = Depends(get_app_settings),
) -> dict[str, Any]:
    """Initiate workspace deletion grace period, pause automation, and dispatch owner email."""
    return workspace_lifecycle.request_workspace_deletion(db, clock, ctx, settings)


@router.post(
    "/cancel-deletion",
    summary="Cancel workspace deletion during grace period (Owner only)",
)
def cancel_workspace_deletion_endpoint(
    ctx: WorkspaceContext = Depends(require_membership("workspace.manage")),
    db: Session = Depends(get_db),
    clock: Clock = Depends(get_clock),
) -> dict[str, Any]:
    """Cancel pending workspace deletion and restore active workspace status."""
    return workspace_lifecycle.cancel_workspace_deletion(db, clock, ctx)


@router.get(
    "/deletion-status",
    summary="Get workspace deletion grace period status",
)
def get_workspace_deletion_status_endpoint(
    ctx: WorkspaceContext = Depends(require_membership("workspace.manage")),
    db: Session = Depends(get_db),
    clock: Clock = Depends(get_clock),
) -> dict[str, Any]:
    """Get the current deletion status and remaining days in grace period."""
    return workspace_lifecycle.get_workspace_deletion_status(db, clock, ctx)
