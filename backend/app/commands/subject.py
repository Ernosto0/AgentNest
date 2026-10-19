"""Registers ``owner_command`` as an approval subject (workflows.md §D).

Imported by ``app.handlers.load_handlers`` in the API and the worker, so a confirmation decided
in the API runs its callback in the same request.
"""

from app.approvals import callbacks
from app.commands import service

callbacks.register(
    "owner_command",
    service.on_approval_decided,
    current_version=service.subject_version,
    status_of=service.subject_status,
)
