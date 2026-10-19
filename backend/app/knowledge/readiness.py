"""Readiness (workflows.md §A step 7): is this workspace ready to draft and to automate?

``compute_readiness`` is a pure function over the *usable* facts (verified, in window, not
contested), so a contested or expired fact lowers readiness. Levels:

* ``not_ready``: a requirement for drafts is missing.
* ``ready_for_drafts``: business name, a contact, a location, opening hours are usable.
* ``ready``: additionally booking instructions, a price policy (prices, or an answer text if
  prices are not shared), at least one service, a connected account and a reviewed
  automation policy.

The account requirement reports ``not_connected`` until the workspace has a connected account.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.core.clock import Clock
from app.core.context import WorkspaceContext
from app.core.errors import AppError
from app.identity import repository as identity_repo
from app.identity.schemas import WorkspaceSettings
from app.integrations.instagram import queries as account_queries
from app.knowledge import service
from app.knowledge.templates import Template, load_template

LEVELS = ("not_ready", "ready_for_drafts", "ready")


@dataclass(frozen=True)
class ReadinessLink:
    """Where the user fixes it. The frontend maps ``target`` to a route."""

    target: str  # knowledge | integrations | automation
    category: str | None = None
    key: str | None = None


@dataclass(frozen=True)
class Requirement:
    code: str
    required_for: str  # drafts | ready
    satisfied: bool
    status: str  # ok | missing | not_connected | not_reviewed
    link: ReadinessLink
    missing_keys: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class Readiness:
    level: str
    requirements: tuple[Requirement, ...]


def _group_keys(template: Template, group: str) -> tuple[str, ...]:
    return tuple(i.key for i in template.items if i.required_group == group and i.key is not None)


def _link(key: str) -> ReadinessLink:
    return ReadinessLink("knowledge", key.split(".")[0], key)


def compute_readiness(
    template: Template,
    usable: Mapping[str, Mapping[str, Any]],
    *,
    account_connected: bool,
    automation_reviewed_at: datetime | None,
) -> Readiness:
    """``usable`` maps fact key -> value for the usable facts only."""

    def fact_requirement(code: str, required_for: str, key: str) -> Requirement:
        ok = key in usable
        return Requirement(
            code, required_for, ok, "ok" if ok else "missing", _link(key), () if ok else (key,)
        )

    contact_keys = _group_keys(template, "contact")
    contact_ok = any(key in usable for key in contact_keys)
    online_only = usable.get("location.online_only", {}).get("value") is True
    location_ok = "location.address" in usable or online_only

    disclosure = usable.get("policy.price_disclosure", {}).get("value")
    if disclosure == "share":
        needed = tuple(
            i.key
            for i in template.items
            if i.key is not None
            and i.required_for == "ready"
            and i.required_when == "price_disclosure=share"
        )
        missing_prices = tuple(key for key in needed if key not in usable)
        price_missing: tuple[str, ...] = missing_prices
        price_link = (
            _link(missing_prices[0]) if missing_prices else _link("policy.price_disclosure")
        )
    elif disclosure == "do_not_share":
        price_missing = (
            () if "policy.price_answer_text" in usable else ("policy.price_answer_text",)
        )
        price_link = _link("policy.price_answer_text")
    else:
        price_missing = ("policy.price_disclosure",)
        price_link = _link("policy.price_disclosure")

    service_patterns = [i for i in template.items if i.pattern and i.required_for == "ready"]
    services_ok = any(item.matches(key) for item in service_patterns for key in usable)

    requirements = (
        fact_requirement("business_name", "drafts", "identity.business_name"),
        Requirement(
            "contact",
            "drafts",
            contact_ok,
            "ok" if contact_ok else "missing",
            _link(contact_keys[0]),
            () if contact_ok else contact_keys,
        ),
        Requirement(
            "location",
            "drafts",
            location_ok,
            "ok" if location_ok else "missing",
            _link("location.address"),
            () if location_ok else ("location.address",),
        ),
        fact_requirement("hours", "drafts", "hours.weekly"),
        fact_requirement("booking_instructions", "ready", "booking.instructions"),
        Requirement(
            "price_policy",
            "ready",
            not price_missing,
            "ok" if not price_missing else "missing",
            price_link,
            price_missing,
        ),
        Requirement(
            "services",
            "ready",
            services_ok,
            "ok" if services_ok else "missing",
            ReadinessLink("knowledge", "service", None),
            () if services_ok else ("service.*",),
        ),
        Requirement(
            "account_connected",
            "ready",
            account_connected,
            "ok" if account_connected else "not_connected",
            ReadinessLink("integrations"),
        ),
        Requirement(
            "automation_reviewed",
            "ready",
            automation_reviewed_at is not None,
            "ok" if automation_reviewed_at is not None else "not_reviewed",
            ReadinessLink("automation"),
        ),
    )
    drafts_ok = all(r.satisfied for r in requirements if r.required_for == "drafts")
    ready_ok = drafts_ok and all(r.satisfied for r in requirements)
    level = "ready" if ready_ok else "ready_for_drafts" if drafts_ok else "not_ready"
    return Readiness(level=level, requirements=requirements)


def readiness(
    session: Session,
    clock: Clock,
    ctx: WorkspaceContext,
    *,
    account_connected: bool | None = None,
) -> Readiness:
    """Readiness of the workspace now. ``account_connected`` is read from the workspace's
    social account unless a caller already knows it."""
    workspace = identity_repo.get_workspace(session, ctx)
    if workspace is None:
        raise AppError("NOT_FOUND")
    usable = {f.key: f.value for f in service.usable_facts(session, clock, ctx)}
    settings = WorkspaceSettings.model_validate(workspace.settings)
    if account_connected is None:
        account_connected = account_queries.has_connected_account(session, ctx.workspace_id)
    return compute_readiness(
        load_template(workspace.business_category),
        usable,
        account_connected=account_connected,
        automation_reviewed_at=settings.automation_reviewed_at,
    )
