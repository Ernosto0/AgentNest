"""Seed demo data: users, workspaces and memberships (Phase 1), business facts (Phase 2).

Later phases extend the seed (history, content). The seed is idempotent: existing users,
workspaces and facts are left alone; ``reset=True`` removes the seeded ones first.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, model_validator
from sqlalchemy import delete, select
from sqlalchemy.orm import Session, sessionmaker

from app.audit import service as audit
from app.core.clock import Clock
from app.core.config import Settings
from app.core.context import ActorRef
from app.demo.connections_seed import seed_connections
from app.demo.facts_seed import seed_facts
from app.demo.history_seed import seed_history
from app.identity import repository as repo
from app.identity import service
from app.identity.models import User, Workspace, WorkspaceMember
from app.identity.schemas import BusinessCategory, Locale, Market, Role, WorkspaceCreate

DATA_FILE = Path(__file__).parent / "data" / "identity.yaml"
SEED_ACTOR = ActorRef.system("seed")


class SeedError(Exception):
    """The seed cannot run (unsafe environment or invalid data)."""


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SeedUser(_Strict):
    email: str
    display_name: str
    ui_locale: Locale


class SeedWorkspace(_Strict):
    slug: str
    name: str
    business_category: BusinessCategory
    market: Market
    default_locale: Locale
    timezone: str
    currency: str
    is_demo: Literal[True] = True
    members: dict[str, Role]

    @model_validator(mode="after")
    def _has_an_owner(self) -> "SeedWorkspace":
        if "owner" not in self.members.values():
            raise ValueError(f"workspace {self.slug} needs at least one owner")
        return self


class SeedData(_Strict):
    users: list[SeedUser]
    workspaces: list[SeedWorkspace]

    @model_validator(mode="after")
    def _members_are_known_users(self) -> "SeedData":
        known = {u.email for u in self.users}
        for workspace in self.workspaces:
            unknown = set(workspace.members) - known
            if unknown:
                raise ValueError(f"workspace {workspace.slug}: unknown members {sorted(unknown)}")
        return self


def load_seed_data(path: Path = DATA_FILE) -> SeedData:
    return SeedData.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


@dataclass
class SeedReport:
    created_users: list[str] = field(default_factory=list)
    existing_users: list[str] = field(default_factory=list)
    created_workspaces: list[str] = field(default_factory=list)
    existing_workspaces: list[str] = field(default_factory=list)
    removed_users: int = 0
    removed_workspaces: int = 0
    seeded_facts: dict[str, int] = field(default_factory=dict)  # workspace slug -> items added
    connected_accounts: list[str] = field(default_factory=list)  # slugs given a simulated account


def reset_identity_data(session: Session, data: SeedData) -> tuple[int, int]:
    """Delete the seeded workspaces and users (children cascade). Audit rows are kept."""
    workspaces = session.execute(
        delete(Workspace).where(Workspace.slug.in_([w.slug for w in data.workspaces]))
    )
    users = session.execute(delete(User).where(User.email.in_([u.email for u in data.users])))
    session.commit()
    return workspaces.rowcount, users.rowcount  # type: ignore[attr-defined]


def seed(
    session_factory: sessionmaker[Session],
    clock: Clock,
    settings: Settings,
    *,
    reset: bool = False,
    data: SeedData | None = None,
) -> SeedReport:
    if settings.app_env == "production":
        raise SeedError("The seed refuses to run in production.")
    data = data or load_seed_data()
    password = settings.demo_password.get_secret_value()
    report = SeedReport()

    with session_factory() as session:
        if reset:
            report.removed_workspaces, report.removed_users = reset_identity_data(session, data)

        users: dict[str, User] = {}
        for user_entry in data.users:
            existing = repo.get_user_by_email(session, user_entry.email)
            if existing is not None:
                users[user_entry.email] = existing
                report.existing_users.append(user_entry.email)
                continue
            try:
                users[user_entry.email] = service.create_user(
                    session,
                    email=user_entry.email,
                    password=password,
                    display_name=user_entry.display_name,
                    ui_locale=user_entry.ui_locale,
                )
            except Exception as exc:
                raise SeedError(
                    f"cannot create demo user {user_entry.email}: {exc} "
                    "(DEMO_PASSWORD must be at least 10 characters and not a common password)"
                ) from exc
            report.created_users.append(user_entry.email)

        for ws_entry in data.workspaces:
            existing_ws = session.scalars(
                select(Workspace).where(Workspace.slug == ws_entry.slug)
            ).one_or_none()
            if existing_ws is not None:
                report.existing_workspaces.append(ws_entry.slug)
                continue
            owner_email = next(e for e, role in ws_entry.members.items() if role == "owner")
            workspace = service.create_workspace(
                session,
                clock,
                users[owner_email],
                WorkspaceCreate(
                    name=ws_entry.name,
                    business_category=ws_entry.business_category,
                    market=ws_entry.market,
                    default_locale=ws_entry.default_locale,
                    timezone=ws_entry.timezone,
                    currency=ws_entry.currency,
                ),
                slug=ws_entry.slug,
                is_demo=ws_entry.is_demo,
                actor=SEED_ACTOR,
            )
            ctx = service.workspace_context(workspace, SEED_ACTOR, None)
            for email, role in ws_entry.members.items():
                if email == owner_email:
                    continue  # already the owner through create_workspace
                repo.add_member(
                    session,
                    WorkspaceMember(workspace_id=workspace.id, user_id=users[email].id, role=role),
                )
                audit.record(
                    session,
                    ctx,
                    "member.joined",
                    "user",
                    users[email].id,
                    {"role": role, "source": "seed"},
                    clock=clock,
                )
            session.commit()
            report.created_workspaces.append(ws_entry.slug)
    # Facts are seeded separately from workspace creation: a workspace that already exists
    # (for example from Phase 1) still receives the facts it is missing.
    report.seeded_facts = seed_facts(session_factory, clock)
    report.connected_accounts = seed_connections(session_factory, clock)
    seed_history(session_factory, clock, settings)
    return report
