"""API schemas for identity. Response models are explicit allow-lists (INV-10): no password
hash, token hash or session secret field exists in any model here."""

import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.core.pagination import Page as Page  # re-exported: the list envelope lives in core

Locale = Literal["tr", "en"]
Role = Literal["owner", "manager", "staff"]
BusinessCategory = Literal["gym", "pilates_studio", "other"]
Market = Literal["tr", "global"]

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


# --- workspaces.settings ---------------------------------------------------------------


class DisclosureText(StrictModel):
    tr: str = Field(default="", max_length=500)
    en: str = Field(default="", max_length=500)


class WorkspaceSettings(StrictModel):
    """Validates ``workspaces.settings`` (data-model.md §3.1)."""

    disclosure_enabled: bool = True
    disclosure_text: DisclosureText = Field(default_factory=DisclosureText)
    daily_report_hour: int = Field(default=20, ge=0, le=23)
    publish_max_delay_minutes: int = Field(default=1440, ge=1, le=1440)
    # Set by the server from the injected Clock when the owner reviews the automation policies
    # (POST /automation-policies/review); read-only for clients.
    automation_reviewed_at: datetime | None = None


class WorkspaceSettingsPatch(StrictModel):
    """Partial update of the settings: only the given top-level keys change."""

    disclosure_enabled: bool | None = None
    disclosure_text: DisclosureText | None = None
    daily_report_hour: int | None = Field(default=None, ge=0, le=23)
    publish_max_delay_minutes: int | None = Field(default=None, ge=1, le=1440)


# --- auth -------------------------------------------------------------------------------


class LoginRequest(StrictModel):
    email: str = Field(min_length=1, max_length=320)
    password: str = Field(min_length=1, max_length=1000)


class UserOut(BaseModel):
    id: uuid.UUID
    email: str
    display_name: str
    ui_locale: Locale


class MembershipOut(BaseModel):
    workspace_id: uuid.UUID
    workspace_name: str
    role: Role
    is_demo: bool


class MeResponse(BaseModel):
    user: UserOut
    csrf_token: str
    memberships: list[MembershipOut]


class MeUpdate(StrictModel):
    display_name: Name | None = None
    ui_locale: Locale | None = None


# --- workspaces -------------------------------------------------------------------------


class WorkspaceCreate(StrictModel):
    name: Name
    business_category: BusinessCategory
    market: Market
    default_locale: Locale
    timezone: str = Field(min_length=1, max_length=64)
    currency: str = Field(min_length=3, max_length=3)


class WorkspacePatch(StrictModel):
    name: Name | None = None
    business_category: BusinessCategory | None = None
    market: Market | None = None
    default_locale: Locale | None = None
    reply_languages: list[Locale] | None = Field(default=None, min_length=1)
    timezone: str | None = Field(default=None, min_length=1, max_length=64)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    settings: WorkspaceSettingsPatch | None = None


class WorkspaceOut(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    business_category: BusinessCategory
    market: Market
    default_locale: Locale
    reply_languages: list[Locale]
    timezone: str
    currency: str
    is_demo: bool
    status: Literal["active", "deleting"]
    settings: WorkspaceSettings
    created_at: datetime


class MemberOut(BaseModel):
    user_id: uuid.UUID
    email: str
    display_name: str
    role: Role
    joined_at: datetime


# --- members and invites (Phase 6) -----------------------------------------------------


class MemberRolePatch(StrictModel):
    role: Role


class InviteCreate(StrictModel):
    role: Role


class InviteOut(BaseModel):
    id: uuid.UUID
    role: Role
    expires_at: datetime
    invite_path: str
    invite_url: str
    created_at: datetime


class PendingInviteOut(BaseModel):
    id: uuid.UUID
    role: Role
    expires_at: datetime
    created_at: datetime


class InviteAccept(StrictModel):
    token: str = Field(min_length=1, max_length=200)
    email: str | None = Field(default=None, min_length=1, max_length=320)
    display_name: Name | None = None
    password: str | None = Field(default=None, min_length=1, max_length=1000)


class InviteAcceptOut(BaseModel):
    workspace_id: uuid.UUID
    workspace_name: str
    role: Role
