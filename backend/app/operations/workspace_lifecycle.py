"""Workspace deletion lifecycle and grace-period management (P8-05, ADR-025 §3.3).

Covers:
- Owner-only deletion request initiating 7-day grace period.
- Immediate automation pausing (AccountAgent -> paused, social accounts disconnected).
- Confirmation email dispatch to all workspace owners.
- Cancellation boundary (POST /cancel-deletion) restoring active status before scheduled date.
- Status inspection (GET /deletion-status).
- Hard purge procedure (purge_workspace) with durable deletion_tombstones record.
"""

import uuid
from datetime import timedelta
from typing import Any

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app.agent.models import (
    AccountAgent,
    AgentAction,
    AgentDelegation,
    AgentEvent,
    AgentSession,
    AgentStep,
    AgentThread,
    OwnerTask,
)
from app.approvals.models import Approval
from app.audit import service as audit
from app.comments.models import (
    PrivateReplyOpportunity,
    PublicComment,
    PublicCommentAction,
    PublicMedia,
    PublicThread,
)
from app.content.models import ContentItem, MediaAsset
from app.core.clock import Clock
from app.core.config import Settings
from app.core.context import WorkspaceContext
from app.core.email import send_workspace_deletion_email
from app.core.errors import AppError
from app.identity.models import Invite, User, Workspace, WorkspaceMember
from app.identity.permissions import has_permission
from app.inbox.models import Conversation, InboundEvent, Message, ReplyDraft
from app.integrations.instagram.models import SocialAccount
from app.memory.models import (
    CustomerIdentity,
    CustomerMemory,
    MemorySource,
    MemoryVersion,
    SourceFence,
    SummaryVersion,
)
from app.operations.models import DeletionTombstone, Operation
from app.owner_requests.models import OwnerAnswer, OwnerQuestion

GRACE_PERIOD_DAYS = 7


def request_workspace_deletion(
    session: Session,
    clock: Clock,
    ctx: WorkspaceContext,
    settings: Settings,
) -> dict[str, Any]:
    """Initiate a 7-day deletion grace period and pause all outbound automation (Owner only)."""
    if not has_permission(ctx.role, "workspace.manage") and not has_permission(
        ctx.role, "data.delete"
    ):
        raise AppError("FORBIDDEN")

    workspace = session.get(Workspace, ctx.workspace_id)
    if workspace is None:
        raise AppError("NOT_FOUND")

    if workspace.status == "deleting":
        raise AppError("CONFLICT_STATE")

    now = clock.now()
    scheduled_at = now + timedelta(days=GRACE_PERIOD_DAYS)
    requested_by_id = uuid.UUID(ctx.actor.id) if ctx.actor.id and ctx.actor.type == "user" else None

    workspace.status = "deleting"
    workspace.deletion_requested_at = now
    workspace.deletion_scheduled_at = scheduled_at
    workspace.deletion_requested_by = requested_by_id

    # 1. Immediately pause all outbound automation
    session.execute(
        update(AccountAgent)
        .where(AccountAgent.workspace_id == ctx.workspace_id)
        .values(operating_mode="paused")
    )

    # 2. Cancel pending/queued reply drafts
    session.execute(
        update(ReplyDraft)
        .where(
            ReplyDraft.workspace_id == ctx.workspace_id,
            ReplyDraft.status.in_(["pending_approval", "queued"]),
        )
        .values(status="cancelled")
    )

    # 3. Cancel pending approvals
    session.execute(
        update(Approval)
        .where(
            Approval.workspace_id == ctx.workspace_id,
            Approval.status == "pending",
        )
        .values(status="rejected", decision_note="Workspace deletion requested")
    )

    # 4. Cancel scheduled content items
    session.execute(
        update(ContentItem)
        .where(
            ContentItem.workspace_id == ctx.workspace_id,
            ContentItem.status == "scheduled",
        )
        .values(status="cancelled")
    )

    # 5. Revoke active delegations
    session.execute(delete(AgentDelegation).where(AgentDelegation.workspace_id == ctx.workspace_id))

    # 6. Disconnect social accounts to stop polling/token refreshes
    session.execute(
        update(SocialAccount)
        .where(SocialAccount.workspace_id == ctx.workspace_id)
        .values(status="disconnected")
    )

    # 7. Audit log
    audit.record(
        session,
        ctx,
        "workspace.deletion_requested",
        "workspace",
        ctx.workspace_id,
        {"scheduled_at": scheduled_at.isoformat()},
        clock=clock,
    )

    # 8. Dispatch notification email to all workspace owners
    base_origin = (settings.frontend_origin or settings.app_base_url).rstrip("/")
    cancel_url = f"{base_origin}/w/{ctx.workspace_id}/settings"
    owner_rows = list(
        session.execute(
            select(User.email)
            .join(WorkspaceMember, WorkspaceMember.user_id == User.id)
            .where(
                WorkspaceMember.workspace_id == ctx.workspace_id,
                WorkspaceMember.role == "owner",
            )
        ).all()
    )
    scheduled_str = scheduled_at.strftime("%Y-%m-%d %H:%M UTC")
    for (email_addr,) in owner_rows:
        if email_addr:
            send_workspace_deletion_email(
                settings=settings,
                to_email=email_addr,
                workspace_name=workspace.name,
                scheduled_date_str=scheduled_str,
                cancel_url=cancel_url,
                ui_locale=workspace.default_locale or "tr",
            )

    session.commit()
    return get_workspace_deletion_status(session, clock, ctx)


def cancel_workspace_deletion(
    session: Session,
    clock: Clock,
    ctx: WorkspaceContext,
) -> dict[str, Any]:
    """Cancel a pending workspace deletion before the grace period expires (Owner only)."""
    if not has_permission(ctx.role, "workspace.manage") and not has_permission(
        ctx.role, "data.delete"
    ):
        raise AppError("FORBIDDEN")

    workspace = session.get(Workspace, ctx.workspace_id)
    if workspace is None:
        raise AppError("NOT_FOUND")

    if workspace.status != "deleting":
        raise AppError("CONFLICT_STATE")

    if workspace.deletion_scheduled_at and clock.now() >= workspace.deletion_scheduled_at:
        raise AppError("CONFLICT_STATE")

    workspace.status = "active"
    workspace.deletion_requested_at = None
    workspace.deletion_scheduled_at = None
    workspace.deletion_requested_by = None

    audit.record(
        session,
        ctx,
        "workspace.deletion_cancelled",
        "workspace",
        ctx.workspace_id,
        clock=clock,
    )
    session.commit()
    return get_workspace_deletion_status(session, clock, ctx)


def get_workspace_deletion_status(
    session: Session,
    clock: Clock,
    ctx: WorkspaceContext,
) -> dict[str, Any]:
    """Get the current deletion status and grace period details for the workspace."""
    workspace = session.get(Workspace, ctx.workspace_id)
    if workspace is None:
        raise AppError("NOT_FOUND")

    is_deleting = workspace.status == "deleting"
    days_remaining: int | None = None
    can_cancel = False

    if is_deleting and workspace.deletion_scheduled_at:
        delta = workspace.deletion_scheduled_at - clock.now()
        days_remaining = max(0, delta.days)
        can_cancel = clock.now() < workspace.deletion_scheduled_at

    return {
        "workspace_id": str(ctx.workspace_id),
        "status": workspace.status,
        "is_deleting": is_deleting,
        "deletion_requested_at": (
            workspace.deletion_requested_at.isoformat() if workspace.deletion_requested_at else None
        ),
        "deletion_scheduled_at": (
            workspace.deletion_scheduled_at.isoformat() if workspace.deletion_scheduled_at else None
        ),
        "days_remaining": days_remaining,
        "can_cancel": can_cancel,
    }


def purge_workspace(session: Session, clock: Clock, workspace_id: uuid.UUID) -> None:
    """Hard-purge a workspace after its deletion grace period expires (ADR-025 §3.3)."""
    workspace = session.get(Workspace, workspace_id)
    if workspace is None:
        return

    now = clock.now()
    if workspace.status != "deleting":
        raise AppError("CONFLICT_STATE")
    if workspace.deletion_scheduled_at and now < workspace.deletion_scheduled_at:
        raise AppError("CONFLICT_STATE")

    # Verify no unresolved operations remain in_progress
    in_progress = list(
        session.scalars(
            select(Operation.id).where(
                Operation.workspace_id == workspace_id,
                Operation.status == "in_progress",
            )
        ).all()
    )
    if in_progress:
        raise AppError("CONFLICT_STATE")

    # Delete workspace-scoped rows in foreign-key dependency order
    tables_to_purge = [
        Approval,
        ReplyDraft,
        Message,
        Conversation,
        InboundEvent,
        ContentItem,
        MediaAsset,
        AgentEvent,
        AgentStep,
        AgentAction,
        AgentSession,
        OwnerTask,
        AgentDelegation,
        AgentThread,
        AccountAgent,
        OwnerAnswer,
        OwnerQuestion,
        MemorySource,
        MemoryVersion,
        CustomerMemory,
        SummaryVersion,
        SourceFence,
        CustomerIdentity,
        PublicCommentAction,
        PrivateReplyOpportunity,
        PublicComment,
        PublicThread,
        PublicMedia,
        SocialAccount,
        Operation,
        Invite,
        WorkspaceMember,
    ]

    for model in tables_to_purge:
        ws_col = getattr(model, "workspace_id", None)
        if ws_col is not None:
            session.execute(delete(model).where(ws_col == workspace_id))

    # Durable tombstone
    session.add(
        DeletionTombstone(
            workspace_id=workspace_id,
            entity_type="workspace",
            entity_id=str(workspace_id),
            purged_at=now,
            details={"workspace_name": workspace.name},
        )
    )

    # Finally delete workspace row
    session.delete(workspace)
    session.commit()
