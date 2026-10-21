"""Job payloads of the operations module (ids only)."""

import uuid

from pydantic import BaseModel, ConfigDict


class _Payload(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ReconcileSendPayload(_Payload):
    operation_id: uuid.UUID
    round: int = 1  # which check this is (a new job per check, so each has its own dedup key)


class ReconcilePublishPayload(_Payload):
    """A publish whose outcome is unknown (or whose container is still processing): read the
    container and conclude. One job per operation, checked again by rescheduling the same row."""

    operation_id: uuid.UUID


class EmitEchoPayload(_Payload):
    """Simulator only: deliver the echo webhook of a message the mock "sent"."""

    operation_id: uuid.UUID


class ReconcileStuckPayload(_Payload):
    pass


class ResumeAccountPayload(_Payload):
    """An account is connected again: send what waited for it."""

    social_account_id: uuid.UUID


class AccountHealthCheckPayload(_Payload):
    """A ``degraded`` account: read its profile to find out whether it works again."""

    social_account_id: uuid.UUID
