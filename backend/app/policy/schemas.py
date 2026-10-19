"""API models of the automation policies (api-design.md §2.3)."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Mode = Literal["auto", "approval", "off"]
ActionClass = Literal[
    "reply.hours",
    "reply.location_contact",
    "reply.pricing",
    "reply.services",
    "reply.booking",
    "reply.promotions",
    "reply.general_faq",
    "content.publish",
]


class PolicyItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action_class: ActionClass
    mode: Mode


class PoliciesOut(BaseModel):
    items: list[PolicyItem]
    # `auto` can only be enabled while the workspace is `ready` (ADR-014).
    readiness_level: str
    auto_allowed: bool
    reviewed_at: str | None


class PoliciesIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[PolicyItem] = Field(min_length=1, max_length=20)
