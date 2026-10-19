"""Pure decision guards (ADR-014 §2, state-machines.md §1): no database, no clock.

``decision_blocker`` answers one question: may *this actor* decide *this approval* *now* with
*this payload hash*? It returns the error code to raise, or ``None``. Keeping it pure makes
every guard unit-testable; ``service.decide`` only adds locking and persistence.
"""

import hmac
from dataclasses import dataclass
from datetime import datetime

from app.core.context import ActorRef
from app.identity.permissions import has_permission


@dataclass(frozen=True)
class ApprovalFacts:
    """The fields of an approval the guards look at."""

    kind: str
    status: str
    required_permission: str
    requested_by_actor_type: str
    requested_by_actor_id: str | None
    payload_hash: str
    subject_version: int
    expires_at: datetime


def may_decide(approval: ApprovalFacts, actor: ActorRef, role: str | None) -> bool:
    """Permission to decide: hold the required permission, or be the requester of a
    ``confirmation`` (the user confirming the system's reading of their own command)."""
    if actor.type != "user":
        return False  # decisions come only from explicit human actions (INV-04)
    if has_permission(role, approval.required_permission):
        return True
    return (
        approval.kind == "confirmation"
        and approval.requested_by_actor_type == "user"
        and approval.requested_by_actor_id is not None
        and approval.requested_by_actor_id == actor.id
    )


def is_expired(approval: ApprovalFacts, now: datetime) -> bool:
    return now >= approval.expires_at


def decision_blocker(
    approval: ApprovalFacts,
    *,
    actor: ActorRef,
    role: str | None,
    now: datetime,
    supplied_hash: str,
    subject_version: int | None,
) -> str | None:
    """The first guard that fails, as an error code; ``None`` when the decision may proceed.

    Order matters: permission first (nothing about the approval leaks to someone who may not
    decide it), then state, then expiry, then binding.
    """
    if not may_decide(approval, actor, role):
        return "FORBIDDEN"
    if approval.status == "expired":
        return "APPROVAL_EXPIRED"  # expired earlier (sweep or read): still "expired" to the user
    if approval.status != "pending":
        return "APPROVAL_ALREADY_DECIDED"
    if is_expired(approval, now):
        return "APPROVAL_EXPIRED"
    hash_matches = hmac.compare_digest(supplied_hash.encode(), approval.payload_hash.encode())
    if not hash_matches or subject_version != approval.subject_version:
        return "APPROVAL_STALE"
    return None
