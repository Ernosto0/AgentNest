"""P1-10 seed: demo users/workspaces, idempotence, reset, production refusal; AC 4."""

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.audit.models import AuditLog
from app.core.clock import FrozenClock
from app.core.config import Settings
from app.demo.seed import SeedData, SeedError, load_seed_data, seed
from app.identity.models import AuthSession, User, Workspace, WorkspaceMember
from app.main import create_app

pytestmark = pytest.mark.commits

SessionFactory = sessionmaker[Session]
DEMO_PASSWORD = "demo-password"


@pytest.fixture
def settings_for_seed(settings: Settings) -> Settings:
    return settings.model_copy(update={"demo_password": SecretStr(DEMO_PASSWORD)})


def count(factory: SessionFactory, model: type) -> int:
    with factory() as session:
        return session.scalar(select(func.count()).select_from(model)) or 0


def memberships(factory: SessionFactory) -> set[tuple[str, str, str]]:
    with factory() as session:
        rows = session.execute(
            select(Workspace.slug, User.email, WorkspaceMember.role)
            .join(WorkspaceMember, WorkspaceMember.workspace_id == Workspace.id)
            .join(User, User.id == WorkspaceMember.user_id)
        ).all()
    return {(r[0], r[1], r[2]) for r in rows}


def test_seed_creates_the_documented_demo_data(
    session_factory: SessionFactory, clock: FrozenClock, settings_for_seed: Settings
) -> None:
    report = seed(session_factory, clock, settings_for_seed)

    assert sorted(report.created_users) == [
        "manager@demo.local",
        "other@demo.local",
        "owner@demo.local",
        "staff@demo.local",
    ]
    assert report.created_workspaces == ["golkent-fitness", "harbor-pilates", "other-workspace"]
    assert memberships(session_factory) == {
        ("golkent-fitness", "owner@demo.local", "owner"),
        ("golkent-fitness", "manager@demo.local", "manager"),
        ("golkent-fitness", "staff@demo.local", "staff"),
        ("harbor-pilates", "owner@demo.local", "owner"),
        ("harbor-pilates", "manager@demo.local", "manager"),
        ("harbor-pilates", "staff@demo.local", "staff"),
        ("other-workspace", "other@demo.local", "owner"),
    }
    with session_factory() as session:
        by_slug = {w.slug: w for w in session.scalars(select(Workspace))}
    golkent, harbor = by_slug["golkent-fitness"], by_slug["harbor-pilates"]
    assert (golkent.default_locale, golkent.currency, golkent.timezone) == (
        "tr",
        "TRY",
        "Europe/Istanbul",
    )
    assert (golkent.business_category, golkent.market) == ("gym", "tr")
    assert (harbor.default_locale, harbor.currency, harbor.timezone) == (
        "en",
        "EUR",
        "Europe/Lisbon",
    )
    assert harbor.business_category == "pilates_studio"
    assert all(w.is_demo for w in by_slug.values())


def test_seeded_users_can_log_in_with_the_demo_password(
    session_factory: SessionFactory,
    clock: FrozenClock,
    settings: Settings,
    settings_for_seed: Settings,
) -> None:
    seed(session_factory, clock, settings_for_seed)
    client = TestClient(create_app(settings, clock))
    for email in ("owner@demo.local", "manager@demo.local", "staff@demo.local", "other@demo.local"):
        response = client.post(
            "/api/v1/auth/login", json={"email": email, "password": DEMO_PASSWORD}
        )
        assert response.status_code == 204, email
    bad = client.post(
        "/api/v1/auth/login", json={"email": "owner@demo.local", "password": "wrong-password"}
    )
    assert bad.status_code == 401


def test_other_user_is_isolated_from_the_gym_workspaces(
    session_factory: SessionFactory,
    clock: FrozenClock,
    settings: Settings,
    settings_for_seed: Settings,
) -> None:
    """Acceptance criterion 4: other@demo.local only sees other-workspace; others are 404."""
    seed(session_factory, clock, settings_for_seed)
    with session_factory() as session:
        ids = {w.slug: w.id for w in session.scalars(select(Workspace))}
    client = TestClient(create_app(settings, clock))
    client.post("/api/v1/auth/login", json={"email": "other@demo.local", "password": DEMO_PASSWORD})

    listing = client.get("/api/v1/workspaces").json()
    assert [i["workspace_name"] for i in listing["items"]] == ["Other Workspace"]
    for slug in ("golkent-fitness", "harbor-pilates"):
        for suffix in ("", "/members"):
            response = client.get(f"/api/v1/workspaces/{ids[slug]}{suffix}")
            assert response.status_code == 404
            assert response.json()["code"] == "NOT_FOUND"
    assert client.get(f"/api/v1/workspaces/{ids['other-workspace']}").status_code == 200


def test_owner_sees_both_gym_workspaces_but_not_the_isolation_one(
    session_factory: SessionFactory,
    clock: FrozenClock,
    settings: Settings,
    settings_for_seed: Settings,
) -> None:
    seed(session_factory, clock, settings_for_seed)
    client = TestClient(create_app(settings, clock))
    client.post("/api/v1/auth/login", json={"email": "owner@demo.local", "password": DEMO_PASSWORD})
    me = client.get("/api/v1/auth/me").json()
    assert [(m["workspace_name"], m["role"], m["is_demo"]) for m in me["memberships"]] == [
        ("Gölkent Fitness & Pilates", "owner", True),
        ("Harbor Pilates Studio", "owner", True),
    ]


def test_seeding_twice_changes_nothing(
    session_factory: SessionFactory, clock: FrozenClock, settings_for_seed: Settings
) -> None:
    seed(session_factory, clock, settings_for_seed)
    again = seed(session_factory, clock, settings_for_seed)
    assert again.created_users == [] and again.created_workspaces == []
    assert (count(session_factory, User), count(session_factory, Workspace)) == (4, 3)
    assert count(session_factory, WorkspaceMember) == 7


def test_reset_recreates_the_seed_and_drops_sessions_but_keeps_audit(
    session_factory: SessionFactory,
    clock: FrozenClock,
    settings: Settings,
    settings_for_seed: Settings,
) -> None:
    seed(session_factory, clock, settings_for_seed)
    client = TestClient(create_app(settings, clock))
    client.post("/api/v1/auth/login", json={"email": "owner@demo.local", "password": DEMO_PASSWORD})
    assert count(session_factory, AuthSession) == 1
    audit_before = count(session_factory, AuditLog)
    with session_factory() as session:
        old_owner_id = session.scalar(select(User.id).where(User.email == "owner@demo.local"))

    report = seed(session_factory, clock, settings_for_seed, reset=True)

    assert (report.removed_users, report.removed_workspaces) == (4, 3)
    assert len(report.created_users) == 4 and len(report.created_workspaces) == 3
    assert count(session_factory, AuthSession) == 0  # the old browser session is gone
    assert client.get("/api/v1/auth/me").status_code == 401
    with session_factory() as session:
        new_owner_id = session.scalar(select(User.id).where(User.email == "owner@demo.local"))
    assert new_owner_id != old_owner_id
    assert count(session_factory, AuditLog) > audit_before  # history is never deleted


def test_reset_leaves_unrelated_data_alone(
    session_factory: SessionFactory, clock: FrozenClock, settings_for_seed: Settings
) -> None:
    from app.identity.service import create_user

    with session_factory() as session:
        create_user(
            session, email="real@example.test", password="a-real-password", display_name="R"
        )
    seed(session_factory, clock, settings_for_seed, reset=True)
    with session_factory() as session:
        assert session.scalar(select(User.id).where(User.email == "real@example.test"))


def test_seed_refuses_to_run_in_production(
    session_factory: SessionFactory, clock: FrozenClock
) -> None:
    production = Settings(
        _env_file=None,
        app_env="production",
        secret_key="p" * 48,
        database_url="postgresql+psycopg://u:p@db.internal:5432/agentnest",
    )
    with pytest.raises(SeedError, match="production"):
        seed(session_factory, clock, production)
    assert count(session_factory, User) == 0
    assert count(session_factory, Workspace) == 0


def test_a_too_weak_demo_password_gives_a_clear_error(
    session_factory: SessionFactory, clock: FrozenClock, settings: Settings
) -> None:
    weak = settings.model_copy(update={"demo_password": SecretStr("short")})
    with pytest.raises(SeedError, match="DEMO_PASSWORD"):
        seed(session_factory, clock, weak)


def test_seed_audit_entries_are_attributed_to_the_seed(
    session_factory: SessionFactory, clock: FrozenClock, settings_for_seed: Settings
) -> None:
    seed(session_factory, clock, settings_for_seed)
    with session_factory() as session:
        created = session.scalars(
            select(AuditLog).where(AuditLog.action == "workspace.created")
        ).all()
        joined = session.scalars(select(AuditLog).where(AuditLog.action == "member.joined")).all()
    assert len(created) == 3 and len(joined) == 4  # the 4 non-owner memberships
    assert {(e.actor_type, e.actor_id) for e in created + joined} == {("system", "seed")}


def test_the_seed_data_file_is_valid_and_matches_the_docs() -> None:
    data = load_seed_data()
    assert [u.email for u in data.users] == [
        "owner@demo.local",
        "manager@demo.local",
        "staff@demo.local",
        "other@demo.local",
    ]
    assert [w.slug for w in data.workspaces] == [
        "golkent-fitness",
        "harbor-pilates",
        "other-workspace",
    ]


@pytest.mark.parametrize(
    "patch",
    [
        {
            "workspaces": [
                {
                    "slug": "x",
                    "name": "X",
                    "business_category": "gym",
                    "market": "tr",
                    "default_locale": "tr",
                    "timezone": "UTC",
                    "currency": "TRY",
                    "members": {"owner@demo.local": "manager"},
                }
            ]
        },
        {
            "workspaces": [
                {
                    "slug": "x",
                    "name": "X",
                    "business_category": "gym",
                    "market": "tr",
                    "default_locale": "tr",
                    "timezone": "UTC",
                    "currency": "TRY",
                    "members": {"ghost@demo.local": "owner"},
                }
            ]
        },
    ],
    ids=["no-owner", "unknown-member"],
)
def test_invalid_seed_data_is_rejected(patch: dict[str, object]) -> None:
    base = {"users": [{"email": "owner@demo.local", "display_name": "O", "ui_locale": "tr"}]}
    with pytest.raises(ValueError):
        SeedData.model_validate({**base, **patch})
