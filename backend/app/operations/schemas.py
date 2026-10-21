"""API models of the operations module (account connection, operation detail)."""

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


class OperationOut(BaseModel):
    """An allow-list for failure explanations: never the provider reference, the result payload
    or the error detail (they may hold provider text and identifiers)."""

    id: uuid.UUID
    type: str
    status: str
    attempts: int
    last_error_code: str | None
    # Plain-language explanation from the error catalog, in the reader's language; ``null`` for an
    # operation that is not in trouble.
    what: str | None
    next: str | None
    subject_type: str
    subject_id: uuid.UUID
    created_at: datetime
    completed_at: datetime | None
    is_simulated: bool


class MockAccountCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str | None = Field(default=None, min_length=1, max_length=64)
