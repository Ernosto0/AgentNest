"""The result of a command: a message key, params and links, rendered by the client.

The backend never builds user-facing sentences for commands. It returns a stable
``message_key`` plus ``params`` (values already formatted for the user, e.g. ``"7.000 ₺"``)
and structured ``links``; the frontend renders them in the user's language (ADR-016).
"""

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from app.commands.models import OwnerCommand
from app.core.clock import Clock
from app.core.context import WorkspaceContext


@dataclass(frozen=True)
class CommandResult:
    message_key: str
    params: dict[str, Any] = field(default_factory=dict)
    links: list[dict[str, Any]] = field(default_factory=list)
    # Set when the outcome is a failure rather than a completion (e.g. FACT_CHANGED_MEANWHILE).
    error_code: str | None = None

    def to_json(self) -> dict[str, Any]:
        return {"message_key": self.message_key, "params": self.params, "links": self.links}


@dataclass(frozen=True)
class ExecContext:
    """What an executor gets. ``ctx`` is the **human** whose permissions apply: the requester
    for a read-only command, the person who decided the confirmation for a state change
    (INV-04). ``user_locale`` is that person's UI language, used to format values."""

    session: Session
    clock: Clock
    ctx: WorkspaceContext
    command: OwnerCommand
    user_locale: str


def knowledge_link(*, category: str | None = None, key: str | None = None) -> dict[str, Any]:
    """Structured like readiness links, so the API stays free of frontend routes."""
    link: dict[str, Any] = {"target": "knowledge"}
    if category:
        link["category"] = category
    if key:
        link["key"] = key
    return link
