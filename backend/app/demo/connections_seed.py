"""Seed demo connections (Phase 4): a simulated Instagram account per demo studio, the reply
languages and the automation review, so demo readiness becomes ``ready`` (workflows.md §A).

Idempotent and independent of workspace creation: a workspace that already exists (from an
earlier phase) still receives what it is missing. Everything created here is simulated.
"""

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.audit import service as audit
from app.core.clock import Clock
from app.core.context import ActorRef
from app.identity import service as identity_service
from app.identity.models import Workspace
from app.identity.schemas import WorkspaceSettings
from app.integrations.instagram import queries
from app.integrations.instagram.models import SocialAccount
from app.operations.accounts import MOCK_CAPABILITIES

SEED_ACTOR = ActorRef.system("seed")


@dataclass(frozen=True)
class Connection:
    username: str
    reply_languages: tuple[str, ...]


# workspace slug -> the simulated account and the languages the studio answers in.
CONNECTIONS = {
    "golkent-fitness": Connection("golkent.fitness.demo", ("tr", "en")),
    "harbor-pilates": Connection("harbor.pilates.demo", ("en",)),
}


def seed_connections(session_factory: sessionmaker[Session], clock: Clock) -> list[str]:
    """Return the slugs that received a new account."""
    connected: list[str] = []
    with session_factory() as session:
        for slug, connection in CONNECTIONS.items():
            workspace = session.scalars(select(Workspace).where(Workspace.slug == slug)).first()
            if workspace is None:
                continue
            if _seed_workspace(session, clock, workspace, connection):
                connected.append(slug)
        session.commit()
    return connected


def _seed_workspace(
    session: Session, clock: Clock, workspace: Workspace, connection: Connection
) -> bool:
    ctx = identity_service.workspace_context(workspace, SEED_ACTOR, None)
    workspace.reply_languages = list(connection.reply_languages)
    settings = WorkspaceSettings.model_validate(workspace.settings)
    if settings.automation_reviewed_at is None:
        merged = settings.model_dump(mode="json")
        merged["automation_reviewed_at"] = clock.now().isoformat()
        workspace.settings = merged  # new dict: JSONB change detection
        audit.record(
            session,
            ctx,
            "policy.reviewed",
            "workspace",
            workspace.id,
            {"source": "seed"},
            clock=clock,
        )
    if queries.get_active_for_workspace(session, workspace.id) is not None:
        return False
    account = SocialAccount(
        workspace_id=workspace.id,
        platform="instagram",
        provider_kind="mock",
        external_account_id=f"mock-{workspace.slug}",
        username=connection.username,
        status="connected",
        capabilities=dict(MOCK_CAPABILITIES),
        granted_scopes=[],
        connected_at=clock.now(),
    )
    session.add(account)
    session.flush()
    audit.record(
        session,
        ctx,
        "social_account.connected",
        "social_account",
        account.id,
        {"from": None, "provider_kind": "mock", "source": "seed"},
        is_simulated=True,
        clock=clock,
    )
    return True
