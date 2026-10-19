"""API schemas for knowledge. Request models are strict; response models are explicit
allow-lists (INV-10).

``value`` is an open object in OpenAPI: its shape depends on ``value_type`` (see
business-knowledge.md §2) and is validated server-side by ``knowledge.values``. The frontend
keeps matching hand-written types.
"""

import uuid
from datetime import date, datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

# Literal types for query parameters and responses; a test pins them to ``constants``.
Category = Literal[
    "identity", "contact", "location", "hours", "service", "pricing", "promotion",
    "policy", "booking", "faq", "brand", "escalation", "schedule", "custom",
]  # fmt: skip
FactStatus = Literal["unverified", "verified", "archived"]
FactState = Literal["unverified", "verified", "contested", "expired", "not_started", "archived"]
Criticality = Literal["critical", "standard"]
CandidateStatus = Literal["pending", "accepted", "rejected", "superseded"]
CandidateRelation = Literal["new", "same", "discrepancy", "contest"]
Reason = Annotated[str, StringConstraints(max_length=500)]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LabelIn(StrictModel):
    tr: str | None = Field(default=None, max_length=100)
    en: str | None = Field(default=None, max_length=100)


# --- requests -------------------------------------------------------------------------------


class FactCreate(StrictModel):
    key: Annotated[str, StringConstraints(min_length=3, max_length=100)]
    value: dict[str, Any]
    value_type: str | None = None
    label: LabelIn | None = None  # pattern (``service.*``) and ``custom.*`` keys
    criticality: Criticality | None = None  # ``custom.*`` keys only; templates decide otherwise
    valid_from: date | None = None
    valid_until: date | None = None
    reason: Reason | None = None


class FactPatch(StrictModel):
    """Only the fields that are sent change. ``valid_from``/``valid_until`` may be null to
    clear the window."""

    expected_version: int = Field(ge=1)
    value: dict[str, Any] | None = None
    valid_from: date | None = None
    valid_until: date | None = None
    reason: Reason | None = None


class FactTransition(StrictModel):
    """Body of verify / archive / restore."""

    expected_version: int = Field(ge=1)
    reason: Reason | None = None


# --- responses ------------------------------------------------------------------------------


class FactOut(BaseModel):
    kind: Literal["fact"] = "fact"
    id: uuid.UUID
    key: str
    category: Category
    label: dict[str, str]
    value_type: str
    value: dict[str, Any]
    display: str
    status: FactStatus
    state: FactState
    criticality: Criticality
    current_version: int
    valid_from: date | None
    valid_until: date | None
    last_verified_at: datetime | None
    last_verified_by_name: str | None
    source_type: str | None
    usable: bool
    open_candidates_count: int


class CandidateOut(BaseModel):
    kind: Literal["candidate"] = "candidate"
    id: uuid.UUID
    fact_key: str
    fact_id: uuid.UUID | None
    fact_label: dict[str, str]
    value_type: str
    proposed_value: dict[str, Any]
    proposed_display: str
    current_display: str | None
    relation: CandidateRelation
    status: CandidateStatus
    source_type: str
    source_excerpt: str | None
    proposed_by_name: str | None
    created_at: datetime
    resolved_at: datetime | None


class VersionOut(BaseModel):
    version: int
    value: dict[str, Any]
    display: str
    status: FactStatus
    valid_from: date | None
    valid_until: date | None
    source_type: str
    source_ref: str | None
    actor_type: str
    actor_name: str | None
    reason: str | None
    change_kind: str
    created_at: datetime


class TemplateItemOut(BaseModel):
    identifier: str
    key: str | None
    pattern: str | None
    category: Category
    label: dict[str, str]
    description: dict[str, str]
    value_types: list[str]
    criticality: Criticality
    required_for: Literal["drafts", "ready"] | None
    required_group: str | None
    required_when: str | None
    allowed_values: list[str]
    status: str
    fact_ids: list[uuid.UUID]


class ReadinessLinkOut(BaseModel):
    target: Literal["knowledge", "integrations", "automation"]
    category: str | None
    key: str | None


class RequirementOut(BaseModel):
    code: str
    required_for: Literal["drafts", "ready"]
    satisfied: bool
    status: str
    link: ReadinessLinkOut
    missing_keys: list[str]


class ReadinessOut(BaseModel):
    level: Literal["not_ready", "ready_for_drafts", "ready"]
    requirements: list[RequirementOut]


class ExtractionCreate(StrictModel):
    text: str
    client_request_id: str


class ExtractionOut(BaseModel):
    run_id: uuid.UUID
    status: Literal["queued", "running", "succeeded", "failed"]
    candidates_created: int
    error_code: str | None = None
    injection_suspected: bool = False
