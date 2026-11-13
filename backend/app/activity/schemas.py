"""Response models of the Activity route (api-design.md section 2.8)."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class ActivityActorOut(BaseModel):
    type: Literal["user", "system", "agent", "provider"]
    label: str


class ActivityResourceOut(BaseModel):
    type: str
    id: uuid.UUID
    # Resolved at read time from the record itself; never message text.
    label: str
    # A frontend route, or null where no screen shows the record.
    link: str | None


class ActivityDetailOut(BaseModel):
    # A whitelisted metadata field; ``label`` and ``value`` are display text in the reader's
    # language (codes mapped through the catalog, never free text).
    key: str
    label: str
    value: str


class ActivityEntryOut(BaseModel):
    id: uuid.UUID
    action: str
    group: str
    occurred_at: datetime
    actor: ActivityActorOut
    text: str
    resource: ActivityResourceOut | None
    is_simulated: bool
    # Read-time classification (activity/classify.py): what the event was, not the record's
    # current state.
    level: Literal["failure", "warning", "success", "info"]
    # Internal bookkeeping that repeats or only tracks progress; never a failure or warning.
    routine: bool
    # Opaque; adjacent entries with equal keys describe the same kind of thing and may be shown
    # as one visual group. Grouping never removes an entry from the response.
    collapse_key: str
    # Entries written for the same flow share it; filter with ``correlation``.
    correlation_id: uuid.UUID | None
    details: list[ActivityDetailOut]


class ActivitySummaryOut(BaseModel):
    days: int
    period_start: datetime
    period_end: datetime
    # Key activity (everything that is not routine) in the period, and how much of it failed,
    # warned or completed. ``routine`` counts the routine entries left out of ``total``.
    total: int
    routine: int
    failure: int
    warning: int
    success: int
