"""Isolation and Row-Level Security for workspace_plans and reply_usage (INV-01, P-11).

Proves: forced RLS and the tenant policy exist on both tables; under the runtime role nothing is
visible without a tenant context; one workspace cannot read, change, delete or insert into another
workspace's plan or ledger; one plan row per workspace.
"""

import contextlib
import uuid
from collections.abc import Iterator

import pytest
from sqlalchemy import delete, insert, select, text, update
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session

from app.core.clock import FrozenClock
from app.core.db import clear_tenant_context, set_tenant_context
from app.plans import service
from app.plans.models import ReplyUsage, WorkspacePlan
from tests.factories import workspace_with_members
from tests.helpers.roles import ensure_runtime_roles


@contextlib.contextmanager
def as_role(session: Session, role: str) -> Iterator[None]:
    ensure_runtime_roles(session)
    session.execute(text(f"SET LOCAL ROLE {role}"))
    session.execute(text("SET LOCAL search_path = public, pg_temp"))
    try:
        yield
    finally:
        session.execute(text("RESET ROLE"))


@pytest.mark.invariant("INV-01")
@pytest.mark.parametrize("table", ["workspace_plans", "reply_usage"])
def test_the_tables_have_forced_rls_and_the_tenant_policy(db_session: Session, table: str) -> None:
    row = db_session.execute(
        text(
            "SELECT relrowsecurity, relforcerowsecurity FROM pg_class "
            "WHERE relname = :t AND relnamespace = 'public'::regnamespace"
        ),
        {"t": table},
    ).one()
    assert tuple(row) == (True, True)
    policies = (
        db_session.execute(
            text("SELECT polname FROM pg_policy WHERE polrelid = CAST(:t AS regclass)"),
            {"t": f"public.{table}"},
        )
        .scalars()
        .all()
    )
    assert policies == ["tenant_isolation_policy"]


@pytest.mark.invariant("INV-01")
def test_workspaces_see_and_change_only_their_own_plan_and_ledger(
    db_session: Session, clock: FrozenClock
) -> None:
    ws_a, _ = workspace_with_members(db_session, name="Plan A")
    ws_b, _ = workspace_with_members(db_session, name="Plan B")
    for workspace in (ws_a, ws_b):
        set_tenant_context(db_session, workspace.id)
        service.get_plan(db_session, clock, workspace.id)
        assert service.consume(db_session, clock, workspace.id, f"draft-{workspace.id}")
    db_session.commit()
    db_session.expunge_all()

    clear_tenant_context(db_session)
    with as_role(db_session, "agentnest_app"):
        assert db_session.scalars(select(WorkspacePlan)).all() == []  # fail closed
        assert db_session.scalars(select(ReplyUsage)).all() == []

    set_tenant_context(db_session, ws_a.id)
    with as_role(db_session, "agentnest_app"):
        assert [p.workspace_id for p in db_session.scalars(select(WorkspacePlan))] == [ws_a.id]
        assert [u.workspace_id for u in db_session.scalars(select(ReplyUsage))] == [ws_a.id]
        changed = db_session.execute(
            update(WorkspacePlan).where(WorkspacePlan.workspace_id == ws_b.id).values(used=0)
        )
        assert changed.rowcount == 0
        deleted = db_session.execute(delete(ReplyUsage).where(ReplyUsage.workspace_id == ws_b.id))
        assert deleted.rowcount == 0

    set_tenant_context(db_session, ws_b.id)
    with as_role(db_session, "agentnest_app"):
        (only,) = db_session.scalars(select(WorkspacePlan)).all()
        assert only.workspace_id == ws_b.id and only.used == 1


@pytest.mark.invariant("INV-01")
def test_a_workspace_cannot_write_a_row_for_another(
    db_session: Session, clock: FrozenClock
) -> None:
    ws_a, _ = workspace_with_members(db_session, name="Write A")
    ws_b, _ = workspace_with_members(db_session, name="Write B")
    set_tenant_context(db_session, ws_a.id)
    db_session.commit()
    with as_role(db_session, "agentnest_app"), pytest.raises(DBAPIError), db_session.begin_nested():
        db_session.execute(
            insert(ReplyUsage).values(
                id=uuid.uuid4(),
                workspace_id=ws_b.id,
                draft_key="stolen",
                period_id=uuid.uuid4(),
                state="consumed",
                expires_at=clock.now(),
            )
        )


def test_the_database_keeps_one_plan_row_and_valid_values(
    db_session: Session, clock: FrozenClock
) -> None:
    workspace, _ = workspace_with_members(db_session, name="Constraints")
    row = service.get_plan(db_session, clock, workspace.id)
    for bad in ({"plan": "enterprise"}, {"status": "paid"}, {"used": -1}, {"monthly_quota": 0}):
        with pytest.raises(IntegrityError), db_session.begin_nested():
            db_session.execute(
                update(WorkspacePlan)
                .where(WorkspacePlan.workspace_id == row.workspace_id)
                .values(**bad)
            )
    with pytest.raises(IntegrityError), db_session.begin_nested():
        db_session.execute(
            update(WorkspacePlan)
            .where(WorkspacePlan.workspace_id == row.workspace_id)
            .values(period_end=row.period_start)
        )
