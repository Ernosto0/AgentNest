"""How content items react to a change of a fact they quote (workflows.md section B step 3.4,
plan.md G14, AC-C4).

Registered with the knowledge impact registry at startup (``app.handlers``), so every fact
update (UI edit, accepted candidate, command) reaches content the same way. All of it runs in
the fact update's own transaction:

- ``scheduled`` / ``retry_scheduled`` -> ``on_hold (FACT_CHANGED)``. The queued publish job of
  the version is cancelled, a waiting operation is cancelled through the ledger hook, and
  ``content.on_hold`` goes to every ``content.approve`` holder **including the person who changed
  the fact** (the fact notification skips them, a held post does not). The approval of a
  scheduled item is already ``approved`` and an approval never leaves that state, so it is not
  "cancelled" here: it can authorise nothing because the item left ``scheduled`` (the executor
  refuses by status and version, INV-16), and re-approving creates a new approval for version + 1.
- ``pending_approval`` -> ``draft`` with ``hold_reason=FACT_CHANGED``; the pending approval is
  cancelled (``FACT_CHANGED``), so nobody can approve the old text.
- ``draft`` -> ``validation.stale = true``: the claim report was computed against the old facts.
- ``publishing`` is **not touched**: the provider call is already in flight and cannot be
  recalled, and the operations ledger must resolve its outcome (INV-05, INV-06). Holding it
  would only hide a post that may be live. ``published`` content is immutable (INV-17).
  ``on_hold``, ``failed``, ``rejected`` and ``cancelled`` items are not live, and a later
  re-approval or resubmission validates the text again.

An item references the fact when it has a ``fact_references`` row for an older version of it, or
when its caption or an overlay suggestion **contains the old display string** of a critical
value even without such a row (an owner may have typed the price by hand: plan.md G6).
"""

import re
import uuid
from collections.abc import Sequence
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.approvals import service as approvals
from app.content import hooks, transitions
from app.content import notifications as content_notifications
from app.content.models import ContentItem
from app.content.payload import publish_job_key
from app.core.clock import Clock
from app.core.context import WorkspaceContext
from app.core.i18n import SUPPORTED_LOCALES
from app.jobs.queue import cancel_queued
from app.knowledge import impact
from app.knowledge import repository as knowledge_repo
from app.knowledge.formatting import format_value
from app.knowledge.models import BusinessFact, FactReference

FACT_CHANGED = "FACT_CHANGED"
HELD = ("scheduled", "retry_scheduled")
LIVE_STATUSES = ("draft", "pending_approval", *HELD)

# Only values that identify themselves in a caption are searched for as text. A boolean, an
# enum or a free text ("Evet", a brand voice paragraph) would hold posts that merely share a word.
SWEEP_VALUE_TYPES = frozenset({"money", "weekly_hours", "phone", "email", "address", "url"})
MIN_NEEDLE_LENGTH = 4


def _needles(fact_type: str, value: dict[str, Any], ctx: WorkspaceContext) -> set[str]:
    """How a value reads in each supported locale (a caption may be in either)."""
    if fact_type not in SWEEP_VALUE_TYPES:
        return set()
    shown = {format_value(fact_type, value, loc, ctx.locale).strip() for loc in SUPPORTED_LOCALES}
    return {text for text in shown if len(text) >= MIN_NEEDLE_LENGTH}


def _pattern(needle: str) -> re.Pattern[str]:
    """The display as a whole token: ``6.000 ₺`` is not found inside ``16.000 ₺``; whitespace
    of any kind matches whitespace."""
    words = r"\s+".join(re.escape(word) for word in needle.split())
    return re.compile(rf"(?<![\w.,]){words}(?!\w)", re.IGNORECASE)


def _texts(item: ContentItem) -> list[str]:
    return [t for t in (item.caption, *(item.overlay_text_suggestions or [])) if t]


def _shows(item: ContentItem, patterns: Sequence[re.Pattern[str]]) -> bool:
    texts = _texts(item)
    return any(p.search(text) for p in patterns for text in texts)


def _live_items(
    session: Session, ctx: WorkspaceContext, *, lock: bool = False
) -> Sequence[ContentItem]:
    statement = (
        select(ContentItem)
        .where(ContentItem.workspace_id == ctx.workspace_id, ContentItem.status.in_(LIVE_STATUSES))
        .order_by(ContentItem.id)
    )
    return session.scalars(statement.with_for_update(of=ContentItem) if lock else statement).all()


def _referencing_ids(
    session: Session, ctx: WorkspaceContext, fact_id: uuid.UUID, *, except_version: int | None
) -> set[uuid.UUID]:
    """Items with a ``fact_references`` row for the fact, other than ``except_version`` of it."""
    statement = select(FactReference.referrer_id).where(
        FactReference.workspace_id == ctx.workspace_id,
        FactReference.referrer_type == transitions.SUBJECT_TYPE,
        FactReference.fact_id == fact_id,
    )
    if except_version is not None:
        statement = statement.where(FactReference.fact_version != except_version)
    return set(session.scalars(statement).all())


class ContentItemReferrers:
    referrer_type = transitions.SUBJECT_TYPE

    def count(self, session: Session, ctx: WorkspaceContext, fact_id: uuid.UUID) -> dict[str, int]:
        """Live items that quote the fact now (a reference row, or its current display in the
        text), by status. Published and publishing items are not counted: nothing touches them."""
        fact = knowledge_repo.get_fact(session, ctx, fact_id)
        if fact is None:
            return {}
        referenced = _referencing_ids(session, ctx, fact_id, except_version=None)
        patterns = [_pattern(n) for n in sorted(_needles(fact.value_type, fact.value, ctx))]
        counts: dict[str, int] = {}
        for item in _live_items(session, ctx):
            if item.id in referenced or _shows(item, patterns):
                counts[item.status] = counts.get(item.status, 0) + 1
        return counts

    def apply_change(
        self,
        session: Session,
        clock: Clock,
        ctx: WorkspaceContext,
        fact: BusinessFact,
        change: impact.ChangeKind,
        old_version: int,
    ) -> dict[str, int]:
        # Items that rendered an older version of the fact, plus those showing its old display.
        affected = _referencing_ids(session, ctx, fact.id, except_version=fact.current_version)
        old = knowledge_repo.get_version(session, ctx, fact.id, old_version)
        patterns: list[re.Pattern[str]] = []
        if old is not None:
            gone = _needles(fact.value_type, old.value, ctx)
            if change == "value_changed":  # a text still valid today is not out of date
                gone -= _needles(fact.value_type, fact.value, ctx)
            patterns = [_pattern(n) for n in sorted(gone)]

        outcome = {"on_hold": 0, "returned_to_draft": 0, "marked_stale": 0}
        for item in _live_items(session, ctx, lock=True):
            if item.id not in affected and not _shows(item, patterns):
                continue
            if item.status in HELD:
                self._hold(session, clock, ctx, item)
                outcome["on_hold"] += 1
            elif item.status == "pending_approval":
                self._return_to_draft(session, clock, ctx, item)
                outcome["returned_to_draft"] += 1
            else:  # draft
                item.validation = {**(item.validation or {}), "stale": True}
                item.updated_at = clock.now()
                outcome["marked_stale"] += 1
        session.flush()
        return {key: value for key, value in outcome.items() if value}

    @staticmethod
    def _hold(session: Session, clock: Clock, ctx: WorkspaceContext, item: ContentItem) -> None:
        # The queued job of this version can never fire; a job already claimed re-checks the
        # status and finds the item on hold. The ledger hook releases a waiting operation.
        cancel_queued(session, publish_job_key(item.id, item.version), clock)
        hooks.get().cancel_operation(session, clock, ctx, item, FACT_CHANGED)
        approvals.cancel_for_subject(
            session, clock, ctx, transitions.SUBJECT_TYPE, item.id, FACT_CHANGED
        )
        transitions.apply(session, clock, ctx, item, "hold", reason=FACT_CHANGED)
        content_notifications.notify(
            session, clock, ctx, item, content_notifications.ON_HOLD, reason=FACT_CHANGED
        )

    @staticmethod
    def _return_to_draft(
        session: Session, clock: Clock, ctx: WorkspaceContext, item: ContentItem
    ) -> None:
        approvals.cancel_for_subject(
            session, clock, ctx, transitions.SUBJECT_TYPE, item.id, FACT_CHANGED
        )
        transitions.apply(session, clock, ctx, item, "withdraw", reason=FACT_CHANGED)


impact.register_handler(ContentItemReferrers())
