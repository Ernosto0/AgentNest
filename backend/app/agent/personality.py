"""Versioned business voice. Text examples are data and never authority."""

import uuid
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints
from sqlalchemy.orm import Session

from app.agent.models import AccountAgent
from app.agent.repository import AgentScopeError, scoped_account
from app.audit.service import record
from app.core.clock import Clock
from app.core.context import WorkspaceContext
from app.core.errors import AppError
from app.identity.permissions import has_permission


class Examples(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tr: list[Annotated[str, StringConstraints(max_length=160)]] = Field(
        default_factory=list,
        max_length=2,
    )
    en: list[Annotated[str, StringConstraints(max_length=160)]] = Field(
        default_factory=list,
        max_length=2,
    )


class Personality(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tone: Literal["warm", "neutral", "direct"] = "warm"
    formality: Literal["casual", "professional"] = "professional"
    length: Literal["short", "medium"] = "short"
    emoji: Literal["none", "sparse"] = "none"
    dm_style: Literal["conversational", "concise"] = "conversational"
    comment_style: Literal["conversational", "concise"] = "concise"
    examples: Examples = Field(default_factory=Examples)


class PersonalityChange(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=1)
    personality: Personality
    goals: str | None = Field(default=None, max_length=500)


class PersonalityOut(BaseModel):
    version: int
    personality: Personality
    goals: str = ""


def read_personality(account: AccountAgent) -> PersonalityOut:
    return PersonalityOut(
        goals=str(account.goals.get("instructions", "")),
        version=account.persona_version,
        personality=Personality.model_validate(account.persona),
    )


def change_personality(
    db: Session,
    clock: Clock,
    ctx: WorkspaceContext,
    account_id: uuid.UUID,
    change: PersonalityChange,
) -> PersonalityOut:
    if ctx.actor.type != "user" or not has_permission(ctx.role or "", "agent.settings.edit"):
        raise AppError("FORBIDDEN", permission="agent.settings.edit")
    try:
        account = scoped_account(db, ctx.workspace_id, account_id, lock=True)
    except AgentScopeError as exc:
        raise AppError("NOT_FOUND") from exc
    if account.persona_version != change.expected_version:
        raise AppError("VERSION_CONFLICT")
    account.persona = change.personality.model_dump(mode="json")
    if change.goals is not None:
        account.goals = {**account.goals, "instructions": change.goals.strip()}
    account.persona_version += 1
    account.config_version += 1
    account.updated_at = clock.now()
    record(
        db,
        ctx,
        "agent.personality_changed",
        "account_agent",
        account.id,
        {"persona_version": account.persona_version},
        clock=clock,
    )
    return read_personality(account)
