"""Job payloads of the operations module (ids only)."""

import uuid

from pydantic import BaseModel, ConfigDict


class _Payload(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ReconcileSendPayload(_Payload):
    operation_id: uuid.UUID
    round: int = 1  # which check this is (a new job per check, so each has its own dedup key)


class EmitEchoPayload(_Payload):
    """Simulator only: deliver the echo webhook of a message the mock "sent"."""

    operation_id: uuid.UUID


class ReconcileStuckPayload(_Payload):
    pass
