"""P4-01: the seed connects a simulated account and makes the demo studios ``ready``."""

import pytest
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.core.clock import FrozenClock
from app.core.config import Settings
from app.core.context import ActorRef
from app.demo.seed import seed
from app.identity import service as identity_service
from app.identity.models import Workspace
from app.integrations.instagram.models import SocialAccount
from app.knowledge import readiness as readiness_module

pytestmark = pytest.mark.commits

SessionFactory = sessionmaker[Session]


@pytest.fixture
def seed_settings(settings: Settings) -> Settings:
    return settings.model_copy(update={"demo_password": SecretStr("demo-password")})


def workspace_row(session: Session, slug: str) -> Workspace:
    return session.scalars(select(Workspace).where(Workspace.slug == slug)).one()


def test_seed_connects_a_simulated_account_to_each_studio(
    session_factory: SessionFactory, clock: FrozenClock, seed_settings: Settings
) -> None:
    report = seed(session_factory, clock, seed_settings)
    assert report.connected_accounts == ["golkent-fitness", "harbor-cafe"]
    with session_factory() as session:
        accounts = {}
        for slug in ("golkent-fitness", "harbor-cafe", "other-workspace"):
            workspace = workspace_row(session, slug)
            found = session.scalars(
                select(SocialAccount).where(SocialAccount.workspace_id == workspace.id)
            ).first()
            if found is not None:
                accounts[slug] = found
    assert set(accounts) == {"golkent-fitness", "harbor-cafe"}
    assert all(a.provider_kind == "mock" and a.status == "connected" for a in accounts.values())
    assert accounts["golkent-fitness"].username == "golkent.fitness.demo"


def test_seed_is_idempotent_for_accounts(
    session_factory: SessionFactory, clock: FrozenClock, seed_settings: Settings
) -> None:
    seed(session_factory, clock, seed_settings)
    again = seed(session_factory, clock, seed_settings)
    assert again.connected_accounts == []
    with session_factory() as session:
        assert len(list(session.scalars(select(SocialAccount)))) == 2


def test_the_demo_studios_become_ready_and_answer_in_their_languages(
    session_factory: SessionFactory, clock: FrozenClock, seed_settings: Settings
) -> None:
    seed(session_factory, clock, seed_settings)
    with session_factory() as session:
        golkent = workspace_row(session, "golkent-fitness")
        harbor = workspace_row(session, "harbor-cafe")
        assert golkent.reply_languages == ["tr", "en"]
        assert harbor.reply_languages == ["en"]
        for workspace in (golkent, harbor):
            ctx = identity_service.workspace_context(workspace, ActorRef.system("test"), None)
            assert readiness_module.readiness(session, clock, ctx).level == "ready"
