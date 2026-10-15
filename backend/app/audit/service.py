"""Audit log writer and test query helper.

RULE: audit_logs is INSERT-ONLY. This module must never contain an UPDATE or DELETE
(INV-12, INV-17). ``record`` writes inside the caller's transaction and never commits, so the
audit row and the state change it describes succeed or fail together.
"""

import json
import uuid
from collections.abc import Mapping, Sequence
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit.models import AuditLog
from app.core.canonical import canonical_json
from app.core.clock import Clock, SystemClock
from app.core.context import ActorRef, WorkspaceContext

# Audit metadata holds IDs, codes and formatted values: never message text or secrets.
_FORBIDDEN_METADATA_KEYS = frozenset(
    {"text", "message", "message_text", "body", "caption", "token", "password", "secret"}
)


def _check_metadata(value: Any, path: str = "metadata") -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            if str(key).lower() in _FORBIDDEN_METADATA_KEYS:
                raise ValueError(
                    f"audit {path} must not contain {key!r} (no message text or secrets)"
                )
            _check_metadata(item, f"{path}.{key}")
    elif isinstance(value, list | tuple):
        for item in value:
            _check_metadata(item, path)


def record(
    session: Session,
    ctx: WorkspaceContext | None,
    action: str,
    resource_type: str | None,
    resource_id: uuid.UUID | None,
    metadata: Mapping[str, Any] | None = None,
    is_simulated: bool = False,
    correlation_id: uuid.UUID | None = None,
    *,
    clock: Clock | None = None,
    actor: ActorRef | None = None,
    workspace_id: uuid.UUID | None = None,
) -> AuditLog:
    """Append an audit entry to the caller's transaction.

    With a ``ctx`` the workspace and actor come from it. Without one the event is
    system-level (no workspace) unless ``workspace_id`` / ``actor`` are given explicitly,
    e.g. ``auth.login`` (actor = the user, no workspace).
    """
    _check_metadata(metadata or {})
    effective_actor = actor or (ctx.actor if ctx else ActorRef.system())
    entry = AuditLog(
        workspace_id=ctx.workspace_id if ctx else workspace_id,
        occurred_at=(clock or SystemClock()).now(),
        actor_type=effective_actor.type,
        actor_id=effective_actor.id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        correlation_id=correlation_id,
        is_simulated=is_simulated,
        # Normalise Decimals, UUIDs and datetimes into plain JSON.
        metadata_=json.loads(canonical_json(dict(metadata or {}))),
    )
    session.add(entry)
    session.flush()
    return entry


def list_entries(
    session: Session,
    *,
    workspace_id: uuid.UUID | None = None,
    action: str | None = None,
    system_level: bool = False,
    limit: int = 100,
) -> Sequence[AuditLog]:
    """Query helper (tests and, later, the activity feed). Newest first."""
    stmt = select(AuditLog).order_by(AuditLog.occurred_at.desc(), AuditLog.created_at.desc())
    if system_level:
        stmt = stmt.where(AuditLog.workspace_id.is_(None))
    elif workspace_id is not None:
        stmt = stmt.where(AuditLog.workspace_id == workspace_id)
    if action is not None:
        stmt = stmt.where(AuditLog.action == action)
    return session.scalars(stmt.limit(limit)).all()
