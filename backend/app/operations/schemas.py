"""API models of the operations module (account connection)."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class SocialAccountOut(BaseModel):
    """An allow-list: no credential, token or key column is ever part of a response."""

    id: uuid.UUID
    platform: str
    provider_kind: str
    username: str | None
    status: str
    capabilities: dict[str, Any]
    connection_expires_at: datetime | None
    last_error_code: str | None
    is_simulated: bool


class MockAccountCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str | None = Field(default=None, min_length=1, max_length=64)
