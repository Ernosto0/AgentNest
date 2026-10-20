"""Job payloads of the inbox (IDs only, background-jobs.md)."""

import uuid

from pydantic import BaseModel, ConfigDict


class _Payload(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ProcessInboundEventPayload(_Payload):
    event_id: uuid.UUID


def draft_reply_key(conversation_id: uuid.UUID, *, requested: bool = False) -> str:
    """The dedup key of the draft job: one per conversation, whatever triggered it.

    A queued job is kept as it is (``run_at`` is not extended); a customer message that arrives
    while the job runs is caught at the job's last step, which reschedules it. An explicit
    owner request ("suggest reply", allowed in human mode) has its own key: it carries the
    ``requested`` flag, which a job queued by a customer message does not."""
    return f"draft_reply:{conversation_id}" + (":requested" if requested else "")


class DraftReplyPayload(_Payload):
    """The job drafts for whatever the newest customer message is when it runs.

    ``message_id`` is optional and no longer set by the application; it is kept so that jobs
    queued before the change still validate (when set, the job proceeds only if that message is
    still the newest). ``requested`` is an explicit owner request: allowed in human mode."""

    conversation_id: uuid.UUID
    message_id: uuid.UUID | None = None
    requested: bool = False


class SendReplyPayload(_Payload):
    reply_draft_id: uuid.UUID


class ExpireReplyDraftsPayload(_Payload):
    pass
