"""Knowledge queries. Every function takes the ``WorkspaceContext`` and filters on it (INV-01).

Repositories flush but never commit (ADR-003). ``lock=True`` takes ``SELECT … FOR UPDATE``;
services lock the candidate first and the fact second, so concurrent accept/edit cannot
deadlock.
"""

import uuid
from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.context import WorkspaceContext
from app.knowledge.models import BusinessFact, FactCandidate, FactVersion

# --- facts ----------------------------------------------------------------------------------


def add_fact(session: Session, fact: BusinessFact) -> BusinessFact:
    session.add(fact)
    session.flush()
    return fact


def get_fact(
    session: Session, ctx: WorkspaceContext, fact_id: uuid.UUID, *, lock: bool = False
) -> BusinessFact | None:
    query = select(BusinessFact).where(
        BusinessFact.workspace_id == ctx.workspace_id, BusinessFact.id == fact_id
    )
    if lock:
        query = query.with_for_update()
    return session.scalars(query).one_or_none()


def get_live_fact_by_key(
    session: Session, ctx: WorkspaceContext, key: str, *, lock: bool = False
) -> BusinessFact | None:
    """The non-archived fact for ``key`` (at most one, by a partial unique index)."""
    query = select(BusinessFact).where(
        BusinessFact.workspace_id == ctx.workspace_id,
        BusinessFact.key == key,
        BusinessFact.status != "archived",
    )
    if lock:
        query = query.with_for_update()
    return session.scalars(query).one_or_none()


def list_facts(
    session: Session,
    ctx: WorkspaceContext,
    *,
    category: str | None = None,
    status: str | None = None,
) -> Sequence[BusinessFact]:
    query = select(BusinessFact).where(BusinessFact.workspace_id == ctx.workspace_id)
    if category is not None:
        query = query.where(BusinessFact.category == category)
    if status is not None:
        query = query.where(BusinessFact.status == status)
    return session.scalars(query.order_by(BusinessFact.category, BusinessFact.key)).all()


def count_facts(session: Session, ctx: WorkspaceContext) -> int:
    return (
        session.scalar(
            select(func.count())
            .select_from(BusinessFact)
            .where(BusinessFact.workspace_id == ctx.workspace_id)
        )
        or 0
    )


# --- versions (insert-only) -----------------------------------------------------------------


def add_version(session: Session, version: FactVersion) -> FactVersion:
    session.add(version)
    session.flush()
    return version


def list_versions(
    session: Session, ctx: WorkspaceContext, fact_id: uuid.UUID
) -> Sequence[FactVersion]:
    return session.scalars(
        select(FactVersion)
        .where(FactVersion.workspace_id == ctx.workspace_id, FactVersion.fact_id == fact_id)
        .order_by(FactVersion.version.desc())
    ).all()


def get_version(
    session: Session, ctx: WorkspaceContext, fact_id: uuid.UUID, version: int
) -> FactVersion | None:
    return session.scalars(
        select(FactVersion).where(
            FactVersion.workspace_id == ctx.workspace_id,
            FactVersion.fact_id == fact_id,
            FactVersion.version == version,
        )
    ).one_or_none()


# --- candidates -----------------------------------------------------------------------------


def add_candidate(session: Session, candidate: FactCandidate) -> FactCandidate:
    session.add(candidate)
    session.flush()
    return candidate


def get_candidate(
    session: Session, ctx: WorkspaceContext, candidate_id: uuid.UUID, *, lock: bool = False
) -> FactCandidate | None:
    query = select(FactCandidate).where(
        FactCandidate.workspace_id == ctx.workspace_id, FactCandidate.id == candidate_id
    )
    if lock:
        query = query.with_for_update()
    return session.scalars(query).one_or_none()


def list_candidates(
    session: Session,
    ctx: WorkspaceContext,
    *,
    status: str | None = None,
    fact_key: str | None = None,
    lock: bool = False,
) -> Sequence[FactCandidate]:
    query = select(FactCandidate).where(FactCandidate.workspace_id == ctx.workspace_id)
    if status is not None:
        query = query.where(FactCandidate.status == status)
    if fact_key is not None:
        query = query.where(FactCandidate.fact_key == fact_key)
    query = query.order_by(FactCandidate.created_at, FactCandidate.id)
    if lock:
        query = query.with_for_update()
    return session.scalars(query).all()


def pending_candidate_counts(session: Session, ctx: WorkspaceContext) -> dict[str, int]:
    """Pending candidates per fact key (``open_candidates_count``)."""
    rows = session.execute(
        select(FactCandidate.fact_key, func.count())
        .where(FactCandidate.workspace_id == ctx.workspace_id, FactCandidate.status == "pending")
        .group_by(FactCandidate.fact_key)
    ).all()
    return {row[0]: row[1] for row in rows}


def contested_keys(session: Session, ctx: WorkspaceContext) -> set[str]:
    """Keys that have a pending ``contest`` candidate: their facts are not usable."""
    rows = session.scalars(
        select(FactCandidate.fact_key)
        .where(
            FactCandidate.workspace_id == ctx.workspace_id,
            FactCandidate.status == "pending",
            FactCandidate.relation == "contest",
        )
        .distinct()
    ).all()
    return set(rows)
