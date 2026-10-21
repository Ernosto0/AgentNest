"""Demo reset (H15): re-create one demo workspace with a fresh id, for
``POST /api/v1/dev/workspaces/{ws}/reset``. ``seed --reset`` shares the media-file cleanup
(``demo.seed.remove_media_files``) and the workspace creation (``create_seed_workspace``).

The audit trail is insert-only and keyed by ``workspace_id`` (INV-12), so resetting a workspace
*in place* would leave its old history in the feed. Instead the workspace is deleted (children
cascade: accounts, ``sim_*`` rows, content, messages, invites, ...) and re-created with the same
slug, members and settings from the seed data, a **new id**, and yesterday's history (H16). The
old audit rows stay, orphaned and untouched. The old local media files are removed from disk
after the commit (never inside the transaction).
"""

from __future__ import annotations

import uuid

from sqlalchemy.orm import Session, sessionmaker

from app.audit import service as audit
from app.core.clock import Clock
from app.core.config import Settings
from app.core.context import ActorRef
from app.core.errors import AppError
from app.demo.connections_seed import seed_connections
from app.demo.facts_seed import seed_facts
from app.demo.history_seed import seed_history
from app.demo.seed import (
    create_seed_workspace,
    load_seed_data,
    remove_media_files,
    workspace_entry_by_slug,
    workspace_media_keys,
)
from app.identity import repository as identity_repo
from app.identity import service as identity_service
from app.identity.models import User, Workspace

SEED_ACTOR = ActorRef.system("seed")


def reset_workspace(
    session_factory: sessionmaker[Session],
    clock: Clock,
    settings: Settings,
    *,
    slug: str | None = None,
    workspace_id: uuid.UUID | None = None,
    actor: ActorRef = SEED_ACTOR,
) -> uuid.UUID:
    """Reset one demo workspace and return its **new** id.

    ``NOT_FOUND`` for an unknown workspace, ``FORBIDDEN`` when it is not a demo workspace, and
    ``CONFLICT_STATE`` for a demo workspace that is not in the seed data (there is nothing to
    re-create it from). Everything is checked before anything is deleted. The old audit rows
    and every other workspace are untouched; ``demo.reset`` is audited on the new workspace in
    the same transaction that creates it.
    """
    data = load_seed_data()
    with session_factory() as session:
        if workspace_id is not None:
            workspace = session.get(Workspace, workspace_id)
        else:
            workspace = identity_repo.get_workspace_by_slug(session, slug) if slug else None
        if workspace is None:
            raise AppError("NOT_FOUND")
        if not workspace.is_demo:
            raise AppError("FORBIDDEN", permission="workspace.manage")
        entry = workspace_entry_by_slug(data, workspace.slug)
        if entry is None:
            raise AppError("CONFLICT_STATE", entity="workspace", reason="not_in_seed")
        users: dict[str, User] = {}
        for email in entry.members:
            user = identity_repo.get_user_by_email(session, email)
            if user is None:
                raise AppError("CONFLICT_STATE", entity="workspace", reason="seed_user_missing")
            users[email] = user

        previous_id = workspace.id
        media_keys = workspace_media_keys(session, settings, [entry.slug])
        session.delete(workspace)  # children cascade; audit rows are not children
        session.flush()  # frees the slug for the new row
        new_workspace = create_seed_workspace(session, clock, entry, users)
        audit.record(
            session,
            identity_service.workspace_context(new_workspace, actor, None),
            "demo.reset",
            "workspace",
            new_workspace.id,
            {"previous_workspace_id": str(previous_id)},
            is_simulated=True,
            clock=clock,
        )
        session.commit()
        new_id = new_workspace.id

    remove_media_files(media_keys, clock, settings)

    # The same idempotent seeders used by ``seed`` add what the new workspace is missing.
    slugs = [entry.slug]
    seed_facts(session_factory, clock, slugs)
    seed_connections(session_factory, clock, slugs)
    seed_history(session_factory, clock, settings, slugs)
    return new_id
