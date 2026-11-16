"""Per-user Web Push preferences (F-01 part 2): which kinds of event may buzz a phone.

Opt-in per category (``catalog.PUSH_CATEGORIES``): no row means off. A user changes only their
own preferences; nobody can read or set another member's (the key is the caller's user id and the
workspace comes from the route context).
"""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import Clock
from app.core.context import WorkspaceContext
from app.core.errors import AppError
from app.notifications.catalog import PUSH_CATEGORIES
from app.notifications.models import PushPreference


def get_preferences(
    session: Session, workspace_id: uuid.UUID, user_id: uuid.UUID
) -> dict[str, bool]:
    """Every category with the user's choice (off unless they switched it on)."""
    rows = session.scalars(
        select(PushPreference).where(
            PushPreference.workspace_id == workspace_id, PushPreference.user_id == user_id
        )
    )
    chosen = {row.category: row.enabled for row in rows}
    return {category: chosen.get(category, False) for category in PUSH_CATEGORIES}


def is_enabled(
    session: Session, workspace_id: uuid.UUID, user_id: uuid.UUID, category: str
) -> bool:
    row = session.scalar(
        select(PushPreference.enabled).where(
            PushPreference.workspace_id == workspace_id,
            PushPreference.user_id == user_id,
            PushPreference.category == category,
        )
    )
    return bool(row)


def set_preferences(
    session: Session,
    clock: Clock,
    ctx: WorkspaceContext,
    user_id: uuid.UUID,
    changes: dict[str, bool],
) -> dict[str, bool]:
    """Apply the given category choices (others stay as they are). Commits."""
    if any(category not in PUSH_CATEGORIES for category in changes):
        raise AppError("VALIDATION_FAILED")
    now = clock.now()
    for category, enabled in changes.items():
        row = session.scalar(
            select(PushPreference)
            .where(
                PushPreference.workspace_id == ctx.workspace_id,
                PushPreference.user_id == user_id,
                PushPreference.category == category,
            )
            .with_for_update()
        )
        if row is None:
            session.add(
                PushPreference(
                    id=uuid.uuid4(),
                    workspace_id=ctx.workspace_id,
                    user_id=user_id,
                    category=category,
                    enabled=enabled,
                    created_at=now,
                    updated_at=now,
                )
            )
        elif row.enabled != enabled:
            row.enabled = enabled
            row.updated_at = now
    session.flush()
    result = get_preferences(session, ctx.workspace_id, user_id)
    session.commit()
    return result
