"""API models of the content module (api-design.md §2.7)."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class MediaAssetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    status: str
    width: int
    height: int
    mime_type: str
    byte_size: int
    original_filename: str | None
    rejection_code: str | None
    created_at: datetime
