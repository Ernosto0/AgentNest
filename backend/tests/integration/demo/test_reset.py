"""P6-07 (H15): demo reset."""

import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text

from app.audit.models import AuditLog
from app.core.clock import FrozenClock
from app.core.config import Settings
from app.core.errors import AppError
from app.demo.reset import reset_workspace
from app.demo.seed import seed
from app.identity.models import User, Workspace, WorkspaceMember
from app.knowledge.models import BusinessFact
from app.main import create_app
from tests.factories import create_workspace
from tests.helpers.demo import (
    SIM_TABLES,
    STUDIOS,
    YESTERDAY_REPORT,
    SessionFactory,
    post_reset,
    row_ids,
    sign_in,
    sim_count,
    stored_report,
    tenant_tables,
    workspace_ids,
)

pytestmark = pytest.mark.commits


def media_files(root: Path, workspace_id: uuid.UUID) -> list[Path]:
    folder = root / str(workspace_id)
    return [p for p in folder.rglob("*") if p.is_file()] if folder.exists() else []


def test_reset_recreates_the_workspace_with_a_new_id(
    seeded: SessionFactory, client: TestClient, seed_settings: Settings
) -> None:
    ids = workspace_ids(seeded)
    old = ids["golkent-fitness"]
    with seeded() as session:
        members = set(
            session.execute(
                select(WorkspaceMember.user_id, WorkspaceMember.role).where(
                    WorkspaceMember.workspace_id == old
                )
            ).all()
        )
        facts_before = session.scalar(
            select(func.count()).select_from(BusinessFact).where(BusinessFact.workspace_id == old)
        )
        old_audit = session.scalar(
            select(func.count()).select_from(AuditLog).where(AuditLog.workspace_id == old)
        )
        account_ids = [
            r[0]
            for r in session.execute(
                text("select id from social_accounts where workspace_id = :w"), {"w": old}
            )
        ]
        sim_before = {t: sim_count(session, t) for t in SIM_TABLES}
        old_sim = {t: sim_count(session, t, account_ids) for t in SIM_TABLES}
    media_root = seed_settings.media_root
    assert len(media_files(media_root, old)) == 2  # one upload per history post
    assert old_sim["sim_inbound_messages"] > 0 and old_sim["sim_published_media"] == 1
    harbor_before = row_ids(seeded, ids["harbor-pilates"])
    other_before = row_ids(seeded, ids["other-workspace"])

    headers = sign_in(client, "owner@demo.local")
    response = post_reset(client, headers, old)

    assert response.status_code == 200, response.text
    new = uuid.UUID(response.json()["workspace_id"])
    assert new != old
    after = workspace_ids(seeded)
    assert after["golkent-fitness"] == new  # same slug, new id
    with seeded() as session:
        workspace = session.get(Workspace, new)
        assert workspace is not None and workspace.is_demo
        assert session.get(Workspace, old) is None
        new_members = set(
            session.execute(
                select(WorkspaceMember.user_id, WorkspaceMember.role).where(
                    WorkspaceMember.workspace_id == new
                )
            ).all()
        )
        assert new_members == members
        assert (
            session.scalar(
                select(func.count())
                .select_from(BusinessFact)
                .where(BusinessFact.workspace_id == new)
            )
            == facts_before
        )
        assert (
            session.scalar(
                text("select count(*) from social_accounts where workspace_id = :w"), {"w": new}
            )
            == 1
        )
        # The old audit rows stay, untouched; the new workspace has its own trail.
        assert (
            session.scalar(
                select(func.count()).select_from(AuditLog).where(AuditLog.workspace_id == old)
            )
            == old_audit
        )
        reset_entries = session.scalars(
            select(AuditLog).where(AuditLog.workspace_id == new, AuditLog.action == "demo.reset")
        ).all()
        # Every tenant table is empty for the old id, except the insert-only audit trail.
        for table in tenant_tables():
            if table.name == "audit_logs":
                continue
            left = session.scalar(
                select(func.count()).select_from(table).where(table.c.workspace_id == old)
            )
            assert left == 0, table.name
        # The old sim_* rows are gone; the new history created its own.
        for table_name in SIM_TABLES:
            assert sim_count(session, table_name, account_ids) == 0, table_name
        sim_after = {t: sim_count(session, t) for t in SIM_TABLES}
    assert [e.metadata_ for e in reset_entries] == [{"previous_workspace_id": str(old)}]
    assert reset_entries[0].actor_type == "user" and reset_entries[0].is_simulated is True
    assert sim_after == sim_before  # same history shape: old rows replaced one for one

    # Media: the old files are gone, the new history wrote its own.
    assert media_files(media_root, old) == []
    assert len(media_files(media_root, new)) == 2
    # History present: yesterday's report for the new workspace, same numbers.
    values = {k: v["value"] for k, v in stored_report(seeded, new).metrics.items()}
    assert all(values[k] == v for k, v in YESTERDAY_REPORT.items())
    # Other workspaces are untouched: same primary keys in every table.
    assert row_ids(seeded, after["harbor-pilates"]) == harbor_before
    assert row_ids(seeded, after["other-workspace"]) == other_before


def test_reset_by_slug_for_the_cli_path(
    seeded: SessionFactory, clock: FrozenClock, seed_settings: Settings
) -> None:
    old = workspace_ids(seeded)["harbor-pilates"]
    new = reset_workspace(seeded, clock, seed_settings, slug="harbor-pilates")
    assert new != old
    assert workspace_ids(seeded)["harbor-pilates"] == new
    with pytest.raises(AppError) as unknown:
        reset_workspace(seeded, clock, seed_settings, slug="nope")
    assert unknown.value.code == "NOT_FOUND"


def test_reset_refuses_a_workspace_that_is_not_a_demo_workspace(
    seeded: SessionFactory, client: TestClient
) -> None:
    with seeded() as session:
        real = create_workspace(session, slug="real-business", is_demo=False)
        owner = session.scalars(select(User).where(User.email == "owner@demo.local")).one()
        session.add(WorkspaceMember(workspace_id=real.id, user_id=owner.id, role="owner"))
        session.commit()
        real_id = real.id
    ids = workspace_ids(seeded)
    before = {slug: row_ids(seeded, wid) for slug, wid in ids.items()}

    headers = sign_in(client, "owner@demo.local")
    response = post_reset(client, headers, real_id)

    assert response.status_code == 403
    assert response.json()["code"] == "FORBIDDEN"
    assert {slug: row_ids(seeded, wid) for slug, wid in workspace_ids(seeded).items()} == before


def test_reset_refuses_a_demo_workspace_outside_the_seed_data(
    seeded: SessionFactory, client: TestClient
) -> None:
    with seeded() as session:
        stray = create_workspace(session, slug="stray-demo", is_demo=True)
        owner = session.scalars(select(User).where(User.email == "owner@demo.local")).one()
        session.add(WorkspaceMember(workspace_id=stray.id, user_id=owner.id, role="owner"))
        session.commit()
        stray_id = stray.id

    headers = sign_in(client, "owner@demo.local")
    response = post_reset(client, headers, stray_id)

    assert response.status_code == 409
    assert response.json()["code"] == "CONFLICT_STATE"
    assert workspace_ids(seeded)["stray-demo"] == stray_id


def test_reset_needs_the_owner_and_hides_foreign_workspaces(
    seeded: SessionFactory, client: TestClient
) -> None:
    ids = workspace_ids(seeded)
    headers = sign_in(client, "manager@demo.local")
    assert post_reset(client, headers, ids["golkent-fitness"]).status_code == 403
    client.post("/api/v1/auth/logout", headers=headers)

    headers = sign_in(client, "other@demo.local")
    assert post_reset(client, headers, ids["golkent-fitness"]).status_code == 404
    assert post_reset(client, headers, uuid.uuid4()).status_code == 404
    assert workspace_ids(seeded) == ids


def test_the_reset_route_is_absent_without_demo_tools(
    seeded: SessionFactory, seed_settings: Settings, clock: FrozenClock
) -> None:
    """INV-20."""
    ids = workspace_ids(seeded)
    off = seed_settings.model_copy(update={"demo_tools_enabled": False})
    disabled = TestClient(create_app(off, clock))
    headers = sign_in(disabled, "owner@demo.local")
    response = post_reset(disabled, headers, ids["golkent-fitness"])
    assert response.status_code == 404
    assert workspace_ids(seeded) == ids


def test_seed_reset_removes_the_media_files_of_the_old_workspaces(
    seeded: SessionFactory, clock: FrozenClock, seed_settings: Settings
) -> None:
    old = workspace_ids(seeded)
    root = seed_settings.media_root
    assert all(len(media_files(root, old[s])) == 2 for s in STUDIOS)

    seed(seeded, clock, seed_settings, reset=True)

    new = workspace_ids(seeded)
    assert all(media_files(root, old[s]) == [] for s in STUDIOS)
    assert all(len(media_files(root, new[s])) == 2 for s in STUDIOS)
    assert all(new[s] != old[s] for s in STUDIOS)
