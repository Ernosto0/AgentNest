"""Candidates: proposed values that have not been accepted (business-knowledge.md §5).

A candidate never changes a fact by itself and is never used in replies or content. Its
**relation** to the current fact is a pure function of (source tier, current fact), computed
when the candidate is created and recomputed whenever the fact changes:

==============================  ===============  =============
Situation                       Relation         Fact usable?
==============================  ===============  =============
no live fact, or fact unverified ``new``          (not verified)
equals the verified value        ``same``         yes (auto-superseded)
tier 3 differs from verified     ``discrepancy``  yes
tier 2 (staff) differs           ``contest``      **no** until resolved
==============================  ===============  =============

Against an *unverified* fact the relation is ``new`` even if the value is equal, so accepting
it verifies the fact.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.audit import service as audit
from app.core.clock import Clock
from app.core.context import WorkspaceContext
from app.knowledge import repository as repo
from app.knowledge.constants import STAFF_SOURCES
from app.knowledge.models import BusinessFact, FactCandidate
from app.knowledge.transitions import apply_candidate_event
from app.knowledge.values import values_equal


@dataclass(frozen=True)
class FactSnapshot:
    """The part of a fact that decides a candidate's relation."""

    id: uuid.UUID
    status: str
    value_type: str
    value: dict[str, Any]


def snapshot_of(fact: BusinessFact | None) -> FactSnapshot | None:
    if fact is None:
        return None
    return FactSnapshot(fact.id, fact.status, fact.value_type, fact.value)


def compute_relation(
    fact: FactSnapshot | None, proposed_value: dict[str, Any], value_type: str, source_type: str
) -> str:
    if fact is None or fact.status != "verified" or fact.value_type != value_type:
        return "new"
    if values_equal(value_type, fact.value, proposed_value):
        return "same"
    return "contest" if source_type in STAFF_SOURCES else "discrepancy"


def propose_candidate(
    session: Session,
    clock: Clock,
    ctx: WorkspaceContext,
    *,
    key: str,
    value_type: str,
    value: dict[str, Any],
    source_type: str,
    source_excerpt: str | None = None,
    fact: BusinessFact | None = None,
    agent_run_id: uuid.UUID | None = None,
) -> FactCandidate:
    """Store a candidate (``value`` must already be validated and canonical).

    ``fact`` is the live fact for ``key`` (or ``None``). Older pending candidates for the same
    key, source and proposer are superseded. A candidate equal to the verified value is stored
    as ``superseded`` straight away: nothing for anyone to decide.
    """
    relation = compute_relation(snapshot_of(fact), value, value_type, source_type)
    for older in repo.list_candidates(session, ctx, status="pending", fact_key=key, lock=True):
        if (
            older.source_type == source_type
            and older.proposed_by_actor_type == ctx.actor.type
            and older.proposed_by_actor_id == ctx.actor.id
        ):
            older.status = apply_candidate_event(older.status, "supersede")
    status = apply_candidate_event(None, "propose_same" if relation == "same" else "propose")
    candidate = repo.add_candidate(
        session,
        FactCandidate(
            workspace_id=ctx.workspace_id,
            fact_key=key,
            fact_id=fact.id if fact is not None else None,
            proposed_value=value,
            value_type=value_type,
            source_type=source_type,
            source_excerpt=source_excerpt[:500] if source_excerpt else None,
            relation=relation,
            status=status,
            proposed_by_actor_type=ctx.actor.type,
            proposed_by_actor_id=ctx.actor.id,
            agent_run_id=agent_run_id,
        ),
    )
    if status == "pending":
        audit.record(
            session,
            ctx,
            "fact_candidate.created",
            "fact_candidate",
            candidate.id,
            {"key": key, "relation": relation, "source_type": source_type},
            clock=clock,
        )
    return candidate


def recompute_relations(
    session: Session, ctx: WorkspaceContext, key: str, fact: BusinessFact | None
) -> None:
    """Re-evaluate the pending candidates of ``key`` after the fact changed.

    A candidate that now equals the verified value becomes ``superseded`` (no audit entry,
    state-machines.md §2); the others keep or change their relation.
    """
    snapshot = snapshot_of(fact if fact is not None and fact.status != "archived" else None)
    for candidate in repo.list_candidates(session, ctx, status="pending", fact_key=key, lock=True):
        relation = compute_relation(
            snapshot, candidate.proposed_value, candidate.value_type, candidate.source_type
        )
        if relation == "same":
            candidate.status = apply_candidate_event(candidate.status, "supersede")
            continue
        candidate.relation = relation
        candidate.fact_id = snapshot.id if snapshot is not None else None
    session.flush()


def resolve(candidate: FactCandidate, event: str, user_id: uuid.UUID | None, now: datetime) -> None:
    """Apply ``accept`` / ``reject`` and stamp who resolved it."""
    candidate.status = apply_candidate_event(candidate.status, event)
    candidate.resolved_by_user_id = user_id
    candidate.resolved_at = now
