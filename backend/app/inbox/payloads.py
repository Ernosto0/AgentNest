"""Job payloads of the inbox (IDs only, background-jobs.md)."""

import uuid

from pydantic import BaseModel, ConfigDict


class _Payload(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ProcessInboundEventPayload(_Payload):
    event_id: uuid.UUID


class DraftReplyPayload(_Payload):
    conversation_id: uuid.UUID
    # Set by an explicit owner request ("suggest reply"): allowed in human mode.
    requested: bool = False
