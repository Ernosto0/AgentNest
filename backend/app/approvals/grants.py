"""Approvals granted by policy rather than by a person (ADR-014, workflows.md §C step 3.8).

When the automation policy of an action class is ``auto`` and no rule restricts the reply, the
authorization is **recorded**, not skipped: an approval row with ``requested_by = system``,
``decided_by = null`` and ``decision_channel = policy``, so every send is still bound to an
approval and the audit trail is uniform. It never notifies anyone (nobody is asked).
"""

import uuid
from collections.abc import Mapping
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.approvals.models import Approval
from app.approvals.transitions import apply_approval_event
from app.audit import service as audit
from app.core.canonical import payload_hash as compute_payload_hash
from app.core.clock import Clock
from app.core.context import WorkspaceContext


def record_policy_grant(
    session: Session,
    clock: Clock,
    ctx: WorkspaceContext,
    *,
    action: str,
    subject_type: str,
    subject_id: uuid.UUID,
    subject_version: int,
    payload: Mapping[str, Any],
    summary: Mapping[str, Any],
    required_permission: str,
    expires_at: datetime,
    execute_before: datetime | None = None,
    is_simulated: bool = False,
) -> Approval:
    """Create an already-approved authorization (in the caller's transaction, no commit)."""
    now = clock.now()
    approval = Approval(
        workspace_id=ctx.workspace_id,
        kind="authorization",
        action=action,
        subject_type=subject_type,
        subject_id=subject_id,
        subject_version=subject_version,
        payload_hash=compute_payload_hash(payload),
        summary=dict(summary),
        required_permission=required_permission,
        status=apply_approval_event(apply_approval_event(None, "request"), "approve"),
        requested_by_actor_type="system",
        requested_by_actor_id=ctx.actor.id,
        decided_at=now,
        decision_channel="policy",
        expires_at=expires_at,
        execute_before=execute_before,
        is_simulated=is_simulated,
        created_at=now,
    )
    session.add(approval)
    session.flush()
    audit.record(
        session,
        ctx,
        "approval.granted",
        "approval",
        approval.id,
        {
            "action": action,
            "kind": "authorization",
            "subject_type": subject_type,
            "subject_id": subject_id,
            "channel": "policy",
        },
        is_simulated=is_simulated,
        clock=clock,
    )
    return approval
