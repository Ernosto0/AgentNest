"""Job payloads of the inbox (IDs only, background-jobs.md)."""

import uuid

from pydantic import BaseModel, ConfigDict


class _Payload(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ProcessInboundEventPayload(_Payload):
    event_id: uuid.UUID


class DraftReplyPayload(_Payload):
    """``message_id`` is the inbound message that scheduled this job. The job proceeds only if
    that message is still the newest one, which makes the delay a trailing-edge debounce: a
    burst leaves exactly one job that is allowed to draft (the one for its last message).
    ``requested`` is an explicit owner request ("suggest reply"): allowed in human mode."""

    conversation_id: uuid.UUID
    message_id: uuid.UUID | None = None
    requested: bool = False
