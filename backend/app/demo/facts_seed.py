"""Seed demo business facts (Phase 2): realistic, fictional, and idempotent per key.

Facts are validated through the same value models as the API and created through
``knowledge.service.insert_trusted_fact`` (source ``seed``), so versions and audit entries
exist exactly as for real data. ``seed --reset`` deletes the workspace (children cascade) and
this module re-creates the facts.
"""

import calendar
from collections.abc import Collection
from datetime import date
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, model_validator
from sqlalchemy.orm import Session, sessionmaker

from app.core.clock import Clock
from app.core.context import ActorRef
from app.identity import repository as identity_repo
from app.identity import service as identity_service
from app.identity.models import Workspace
from app.knowledge import candidates as candidate_ops
from app.knowledge import repository as repo
from app.knowledge import service as fact_service
from app.knowledge import usability
from app.knowledge.templates import load_template
from app.knowledge.values import validate_value

DATA_DIR = Path(__file__).parent / "data"
# workspace slug -> facts file
FACT_FILES = {
    "golkent-fitness": "facts_golkent_fitness.yaml",
    "harbor-cafe": "facts_harbor_cafe.yaml",
}
SEED_ACTOR = ActorRef.system("seed")


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RelativeEndOfMonth(_Strict):
    """``{end_of_month: 1}`` = the last day of next month, in the workspace timezone."""

    end_of_month: int


class SeedFact(_Strict):
    key: str
    value: dict[str, Any]
    status: Literal["verified", "unverified"] = "verified"
    value_type: str | None = None
    label: dict[str, str] | None = None
    valid_until: RelativeEndOfMonth | date | None = None


class SeedCandidate(_Strict):
    key: str
    value: dict[str, Any]
    source_type: Literal["pasted_text", "instagram_profile", "website"]
    excerpt: str


class FactsSeed(_Strict):
    facts: list[SeedFact]
    candidates: list[SeedCandidate] = []

    @model_validator(mode="after")
    def _unique_keys(self) -> "FactsSeed":
        keys = [fact.key for fact in self.facts]
        if len(keys) != len(set(keys)):
            raise ValueError("duplicate fact keys in the seed file")
        return self


def load_facts_seed(slug: str) -> FactsSeed:
    path = DATA_DIR / FACT_FILES[slug]
    return FactsSeed.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


def _end_of_month(today: date, offset: int) -> date:
    month_index = today.year * 12 + (today.month - 1) + offset
    year, month = divmod(month_index, 12)
    return date(year, month + 1, calendar.monthrange(year, month + 1)[1])


def _seed_workspace_facts(
    session: Session, clock: Clock, workspace: Workspace, data: FactsSeed
) -> int:
    """Create the missing facts and candidates of one workspace. Returns how many were added."""
    ctx = identity_service.workspace_context(workspace, SEED_ACTOR, None)
    today = usability.local_today(clock.now(), workspace.timezone)
    template = load_template(workspace.business_category)
    added = 0
    for fact in data.facts:
        if repo.get_live_fact_by_key(session, ctx, fact.key) is not None:
            continue
        valid_until = fact.valid_until
        if isinstance(valid_until, RelativeEndOfMonth):
            valid_until = _end_of_month(today, valid_until.end_of_month)
        fact_service.insert_trusted_fact(
            session,
            clock,
            ctx,
            key=fact.key,
            value=fact.value,
            verified=fact.status == "verified",
            value_type=fact.value_type,
            label=fact.label,
            valid_until=valid_until,
            source_type="seed",
        )
        added += 1
    for candidate in data.candidates:
        item = template.find(candidate.key)
        if item is None:
            raise ValueError(f"seed candidate for unknown key {candidate.key}")
        pending = repo.list_candidates(session, ctx, status="pending", fact_key=candidate.key)
        if any(c.source_type == candidate.source_type for c in pending):
            continue
        value = validate_value(
            item.value_type,
            candidate.value,
            allowed_values=item.allowed_values or None,
            default_currency=workspace.currency,
        )
        candidate_ops.propose_candidate(
            session,
            clock,
            ctx,
            key=candidate.key,
            value_type=item.value_type,
            value=value,
            source_type=candidate.source_type,
            source_excerpt=candidate.excerpt,
            fact=repo.get_live_fact_by_key(session, ctx, candidate.key),
        )
        session.commit()
        added += 1
    return added


def seed_facts(
    session_factory: sessionmaker[Session], clock: Clock, slugs: Collection[str] | None = None
) -> dict[str, int]:
    """Seed facts for every demo workspace that has a facts file (only ``slugs`` when given).
    Returns slug -> items added."""
    report: dict[str, int] = {}
    with session_factory() as session:
        for slug in FACT_FILES:
            if slugs is not None and slug not in slugs:
                continue
            workspace = identity_repo.get_workspace_by_slug(session, slug)
            if workspace is None:
                continue
            report[slug] = _seed_workspace_facts(session, clock, workspace, load_facts_seed(slug))
    return report
