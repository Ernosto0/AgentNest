"""Approval read model: the API shape, shared by the approvals router and the command API."""

from sqlalchemy.orm import Session

from app.approvals import callbacks, service
from app.approvals.models import Approval
from app.approvals.schemas import ApprovalOut, SubjectLinkOut, SubjectOut
from app.core.clock import Clock
from app.core.context import WorkspaceContext


def approval_out(
    session: Session, clock: Clock, ctx: WorkspaceContext, approval: Approval
) -> ApprovalOut:
    handler = callbacks.get(approval.subject_type)
    status = handler.status_of(session, ctx, approval.subject_id) if handler else None
    return ApprovalOut(
        id=approval.id,
        kind=approval.kind,
        action=approval.action,
        status=approval.status,
        summary=approval.summary,
        payload_hash=approval.payload_hash,
        subject=SubjectOut(
            type=approval.subject_type,
            id=approval.subject_id,
            version=approval.subject_version,
            status=status,
            link=SubjectLinkOut(target=approval.subject_type, id=approval.subject_id),
        ),
        expires_at=approval.expires_at,
        execute_before=approval.execute_before,
        required_permission=approval.required_permission,
        can_decide=service.can_decide(approval, ctx, clock.now())
        and (
            approval.subject_type != "agent_action"
            or (
                handler is not None
                and handler.current_version(session, ctx, approval.subject_id)
                == approval.subject_version
            )
        ),
        is_simulated=approval.is_simulated,
        created_at=approval.created_at,
        decided_at=approval.decided_at,
        cancel_reason=approval.cancel_reason,
    )
