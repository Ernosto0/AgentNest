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


class ActivityEntryOut(BaseModel):
    id: uuid.UUID
    action: str
    group: str
    occurred_at: datetime
    actor: ActivityActorOut
    text: str
    resource: ActivityResourceOut | None
    is_simulated: bool
