"""Job payloads of the commands module. IDs only: the owner's text stays in
``owner_commands.raw_text`` and never travels in a job payload (data-model.md §3.2)."""

import uuid

from pydantic import BaseModel


class InterpretCommandPayload(BaseModel):
    command_id: uuid.UUID


class ExpireCommandsPayload(BaseModel):
    pass
