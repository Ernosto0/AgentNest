"""Synthetic provisional mock-only events. R75-01/02 remain unverified."""

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, ValidationError, field_validator

from app.integrations.instagram.base import NormalizedInboundEvent


class CommentEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal["synthetic-comment-v1"] = Field(
        default="synthetic-comment-v1", alias="schema"
    )
    id: str = Field(min_length=1, max_length=200)
    media_id: str = Field(min_length=1, max_length=200)
    root_id: str = Field(min_length=1, max_length=200)
    parent_id: str | None = Field(default=None, min_length=1, max_length=200)
    author_id: str | None = Field(default=None, min_length=1, max_length=200)
    text: str | None = Field(default=None, max_length=2000)
    state: Literal["visible", "hidden", "deleted", "unknown"] = "visible"
    version: int = Field(ge=1)
    timestamp: AwareDatetime
    media_caption: str | None = Field(default=None, max_length=2000)
    media_verified: bool = False
    media_deleted: bool = False
    media_version: int = Field(default=1, ge=1)

    @field_validator("timestamp")
    @classmethod
    def utc(cls, value: datetime) -> datetime:
        return value.astimezone(UTC)


def normalize(account: str, item: dict[str, Any]) -> NormalizedInboundEvent | None:
    try:
        value = CommentEvent.model_validate(item)
    except ValidationError:
        return None
    return NormalizedInboundEvent(
        event_type="comment",
        account_id=account,
        customer_id=value.author_id,
        provider_timestamp=value.timestamp,
        mid=value.id,
        text=value.text,
        raw_item=value.model_dump(mode="json", by_alias=True),
    )


def parse(payload: Any) -> list[NormalizedInboundEvent]:
    events: list[NormalizedInboundEvent] = []
    if not isinstance(payload, dict) or payload.get("object") != "instagram":
        return events
    entries = payload.get("entry")
    for entry in entries if isinstance(entries, list) else []:
        if not isinstance(entry, dict) or not isinstance(entry.get("id"), str):
            continue
        items = entry.get("synthetic_comments")
        for item in items if isinstance(items, list) else []:
            event = normalize(entry["id"], item) if isinstance(item, dict) else None
            if event:
                events.append(event)
    return events
