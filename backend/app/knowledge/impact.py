"""Impact analysis and propagation of fact changes (business-knowledge.md §8, workflows.md §B).

``fact_references`` records which fact *version* a referrer (reply draft, content item,
approved answer) rendered. When a fact changes, each referrer type has a deterministic
reaction (supersede the draft, put scheduled content on hold, mark an answer for review, ...).
Those reactions live with the referrer's module and are registered here as ``ReferrerHandler``s,
so this module knows nothing about drafts or content. Phase 3 registers no handler of its own:
the framework and its tests come first, and Phases 4-5 add the real referrers.

Sent messages and published content are **never** touched (INV-17); a handler must not
modify them.
"""

import uuid
from collections.abc import Iterable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.clock import Clock
from app.core.context import WorkspaceContext
from app.knowledge.models import BusinessFact, FactReference
from app.notifications import service as notifications

ChangeKind = Literal["value_changed", "archived"]


@dataclass(frozen=True)
class ImpactEntry:
    """What one referrer type holds on a fact: referrer status -> number of referrers."""

    referrer_type: str
    counts: dict[str, int]

    @property
    def total(self) -> int:
        return sum(self.counts.values())


@dataclass(frozen=True)
class ImpactReport:
    fact_id: uuid.UUID
    entries: tuple[ImpactEntry, ...] = field(default=())

    @property
    def total(self) -> int:
        return sum(entry.total for entry in self.entries)

    def to_dict(self) -> dict[str, Any]:
        """JSON for approval summaries and notification params."""
        return {
            "total": self.total,
            "items": [
                {"referrer_type": e.referrer_type, "counts": e.counts, "total": e.total}
                for e in self.entries
                if e.total
            ],
        }


class ReferrerHandler(Protocol):
    """How one referrer type is counted and how it reacts to a fact change."""

    referrer_type: str

    def count(self, session: Session, ctx: WorkspaceContext, fact_id: uuid.UUID) -> dict[str, int]:
        """Live referrers of the fact by status. Read-only; historical rows are not counted."""
        ...

    def apply_change(
        self,
        session: Session,
        clock: Clock,
        ctx: WorkspaceContext,
        fact: BusinessFact,
        change: ChangeKind,
        old_version: int,
    ) -> dict[str, int]:
        """React to the change inside the caller's transaction (never commit). Returns what
        happened by outcome (e.g. ``{"superseded": 2}``) for the notification."""
        ...


_HANDLERS: dict[str, ReferrerHandler] = {}


def register_handler(handler: ReferrerHandler) -> None:
    if handler.referrer_type in _HANDLERS:
        raise ValueError(f"referrer handler already registered: {handler.referrer_type}")
    _HANDLERS[handler.referrer_type] = handler


@contextmanager
def handlers_snapshot(*, clear: bool = False) -> Iterator[None]:
    """Restore the registry on exit (tests); ``clear`` starts from an empty one."""
    saved = dict(_HANDLERS)
    if clear:
        _HANDLERS.clear()
    try:
        yield
    finally:
        _HANDLERS.clear()
        _HANDLERS.update(saved)


def analyze_impact(session: Session, ctx: WorkspaceContext, fact_id: uuid.UUID) -> ImpactReport:
    """What a change of this fact would touch, for confirmation summaries. Read-only."""
    entries = tuple(
        ImpactEntry(handler.referrer_type, handler.count(session, ctx, fact_id))
        for handler in _HANDLERS.values()
    )
    return ImpactReport(fact_id, entries)


@dataclass(frozen=True)
class ChangeEffects:
    """The outcome of ``apply_change`` across all handlers."""

    by_referrer: dict[str, dict[str, int]] = field(default_factory=dict)

    @property
    def total(self) -> int:
        return sum(sum(outcomes.values()) for outcomes in self.by_referrer.values())

    def to_dict(self) -> dict[str, Any]:
        return {"total": self.total, "by_referrer": self.by_referrer}


def apply_change(
    session: Session,
    clock: Clock,
    ctx: WorkspaceContext,
    fact: BusinessFact,
    change: ChangeKind,
    old_version: int,
) -> ChangeEffects:
    """Run every handler for a fact change (in the caller's transaction)."""
    by_referrer: dict[str, dict[str, int]] = {}
    for handler in _HANDLERS.values():
        outcome = handler.apply_change(session, clock, ctx, fact, change, old_version)
        if outcome:
            by_referrer[handler.referrer_type] = dict(outcome)
    return ChangeEffects(by_referrer)


def notify_fact_changed(
    session: Session,
    clock: Clock,
    ctx: WorkspaceContext,
    fact: BusinessFact,
    *,
    change: ChangeKind,
    old_display: str,
    new_display: str,
    effects: ChangeEffects,
) -> None:
    """Tell the other owners and managers that a fact changed and what it touched.

    The person who made the change is not notified of their own action. Deduped per fact and
    version (an unread notification for the same version is never repeated).
    """
    actor = uuid.UUID(ctx.actor.id) if ctx.actor.type == "user" and ctx.actor.id else None
    notifications.notify_permission_holders(
        session,
        clock,
        ctx,
        permission="knowledge.verify",
        type="knowledge.fact_changed",
        params={
            "fact_key": fact.key,
            "label": fact.label,
            "change": change,
            "old_display": old_display,
            "new_display": new_display,
            "version": fact.current_version,
            "impact": effects.to_dict(),
        },
        subject_type="business_fact",
        subject_id=fact.id,
        dedup_key=f"fact:{fact.id}:v{fact.current_version}",
        exclude_user_id=actor,
    )


# --- fact_references helpers (used by referrer modules) ------------------------------------


def replace_references(
    session: Session,
    ctx: WorkspaceContext,
    referrer_type: str,
    referrer_id: uuid.UUID,
    references: Iterable[tuple[uuid.UUID, int]],
) -> None:
    """Make ``references`` ((fact_id, version) pairs) the referrer's complete set of rows."""
    session.execute(
        delete(FactReference).where(
            FactReference.workspace_id == ctx.workspace_id,
            FactReference.referrer_type == referrer_type,
            FactReference.referrer_id == referrer_id,
        )
    )
    seen: dict[uuid.UUID, int] = {}
    for fact_id, version in references:
        seen[fact_id] = version  # one row per fact per referrer
    for fact_id, version in seen.items():
        session.add(
            FactReference(
                workspace_id=ctx.workspace_id,
                fact_id=fact_id,
                fact_version=version,
                referrer_type=referrer_type,
                referrer_id=referrer_id,
            )
        )
    session.flush()


def references_to_fact(
    session: Session, ctx: WorkspaceContext, fact_id: uuid.UUID, referrer_type: str | None = None
) -> Sequence[FactReference]:
    statement = select(FactReference).where(
        FactReference.workspace_id == ctx.workspace_id, FactReference.fact_id == fact_id
    )
    if referrer_type is not None:
        statement = statement.where(FactReference.referrer_type == referrer_type)
    return session.scalars(statement.order_by(FactReference.created_at, FactReference.id)).all()


def count_references(session: Session, ctx: WorkspaceContext, fact_id: uuid.UUID) -> int:
    return int(
        session.scalar(
            select(func.count())
            .select_from(FactReference)
            .where(FactReference.workspace_id == ctx.workspace_id, FactReference.fact_id == fact_id)
        )
        or 0
    )
