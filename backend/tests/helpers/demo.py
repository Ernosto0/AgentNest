"""Shared helpers of the demo seed, history and reset tests (P6-07)."""

import uuid
from datetime import date, timedelta
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import Table, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.clock import FrozenClock
from app.core.db import Base
from app.identity.models import Workspace
from app.reporting.models import DailyReport
from app.reporting.periods import local_date_of

SessionFactory = sessionmaker[Session]
PASSWORD = "demo-password"
STUDIOS = ("golkent-fitness", "harbor-cafe")
SIM_TABLES = (
    "sim_inbound_messages",
    "sim_sent_messages",
    "sim_failure_rules",
    "sim_containers",
    "sim_published_media",
)

# H16: yesterday, per studio.
YESTERDAY_REPORT = {
    "inbound_messages": 6,
    "conversations_with_inbound": 6,
    "new_conversations": 6,
    "replies_sent": 4,
    "replies_sent_approved": 4,
    "replies_sent_auto": 0,
    "replies_sent_by_owner": 0,
    "native_replies": 0,
    "escalations": 1,
    "missed_conversations": 0,
    "content_published": 1,
    "content_failed": 1,
    "integration_errors": 1,
    "fact_changes": 0,
}


def workspace_ids(factory: SessionFactory) -> dict[str, uuid.UUID]:
    with factory() as session:
        return {w.slug: w.id for w in session.scalars(select(Workspace))}


def sim_count(session: Session, name: str, account_ids: list[uuid.UUID] | None = None) -> int:
    """Rows of a ``sim_*`` table (of these accounts only, when given)."""
    table = Base.metadata.tables[name]
    query = select(func.count()).select_from(table)
    if account_ids is not None:
        query = query.where(table.c.social_account_id.in_(account_ids))
    return session.scalar(query) or 0


def tenant_tables() -> list[Table]:
    return [t for t in Base.metadata.sorted_tables if "workspace_id" in t.c]


def row_ids(factory: SessionFactory, workspace_id: uuid.UUID) -> dict[str, frozenset[Any]]:
    """The primary keys of every tenant row of one workspace, per table."""
    snapshot: dict[str, frozenset[Any]] = {}
    with factory() as session:
        for table in tenant_tables():
            rows = session.execute(
                select(*table.primary_key.columns).where(table.c.workspace_id == workspace_id)
            ).all()
            snapshot[table.name] = frozenset(tuple(r) for r in rows)
    return snapshot


def yesterday_of(clock: FrozenClock, timezone: str) -> date:
    return local_date_of(clock.now(), timezone) - timedelta(days=1)


def stored_report(factory: SessionFactory, workspace_id: uuid.UUID) -> DailyReport:
    with factory() as session:
        return session.scalars(
            select(DailyReport).where(DailyReport.workspace_id == workspace_id)
        ).one()


def sign_in(client: TestClient, email: str) -> dict[str, str]:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert response.status_code == 204, response.text
    return {"X-CSRF-Token": client.get("/api/v1/auth/me").json()["csrf_token"]}


def post_reset(client: TestClient, headers: dict[str, str], workspace_id: uuid.UUID) -> Any:
    return client.post(f"/api/v1/dev/workspaces/{workspace_id}/reset", headers=headers)
