"""Upgrade real 0014 data without inventing historical membership or dropping generations."""

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.audit.models import AuditLog
from app.core.db import BACKEND_DIR, Base
from app.reporting.models import DailyReport, ReportItem, ReportSourceGap
from tests.factories import create_workspace
from tests.helpers.reporting import DAY, at


@pytest.fixture
def old_schema(engine: Engine) -> Iterator[tuple[Config, Engine]]:
    schema = "report_upgrade_" + uuid.uuid4().hex
    with engine.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    url = engine.url.update_query_dict({"options": f"-csearch_path={schema}"})
    isolated = create_engine(url)
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    config.set_main_option(
        "sqlalchemy.url", url.render_as_string(hide_password=False).replace("%", "%%")
    )
    try:
        command.upgrade(config, "0014")
        yield config, isolated
    finally:
        isolated.dispose()
        with engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))


@pytest.mark.parametrize("prior_deletions", [False, True])
def test_upgrade_preserves_values_and_marks_legacy_uncertainty(
    old_schema: tuple[Config, Engine],
    prior_deletions: bool,
) -> None:
    config, isolated = old_schema
    report_id = uuid.uuid4()
    cleanup_at = datetime(2026, 10, 21, tzinfo=UTC)
    with Session(isolated) as session:
        workspace = create_workspace(session, business_category="gym")
        workspace.created_at = at(DAY, 0)
        session.flush()
        workspace_id = workspace.id
        session.execute(
            text("""
            INSERT INTO daily_reports
              (id, workspace_id, local_date, timezone, period_start, period_end,
               metrics, definitions_version, has_simulated_data, generated_at)
            VALUES (:id, :ws, :day, 'Europe/Istanbul', :start, :end,
                    CAST(:metrics AS jsonb), '1', true, :end)
        """),
            {
                "id": report_id,
                "ws": workspace_id,
                "day": DAY,
                "start": at(DAY, 0),
                "end": at(DAY, 23),
                "metrics": '{"inbound_messages":{"value":123}}',
            },
        )
        if prior_deletions:
            session.add(
                AuditLog(
                    actor_type="system",
                    action="retention.cleanup_ran",
                    occurred_at=cleanup_at,
                    metadata_={"webhook_rows_deleted": 7},
                )
            )
        session.commit()
    command.upgrade(config, "head")
    with Session(isolated) as session:
        row = session.get(DailyReport, report_id)
        assert row is not None
        assert row.metrics == {"inbound_messages": {"value": 123}}
        assert row.revision == 1 and row.evidence_complete is False
        gaps = list(session.scalars(select(ReportSourceGap)))
        if prior_deletions:
            assert len(gaps) == 1 and gaps[0].workspace_id == workspace_id
            assert gaps[0].start_at < at(DAY, 0) and gaps[0].end_at == cleanup_at
        else:
            assert gaps == []
    # Compare the changed tables; unrelated pre-existing metadata drift is out of scope.
    tables = {DailyReport.__tablename__, ReportItem.__tablename__, ReportSourceGap.__tablename__}
    with isolated.connect() as connection:
        context = MigrationContext.configure(
            connection,
            opts={
                "compare_type": True,
                "compare_server_default": True,
                "include_object": lambda obj, name, kind, reflected, compare_to: (
                    kind != "table" or name in tables
                ),
            },
        )
        assert compare_metadata(context, Base.metadata) == []


def test_downgrade_refuses_to_destroy_multiple_generations(
    old_schema: tuple[Config, Engine],
) -> None:
    config, isolated = old_schema
    command.upgrade(config, "head")
    with Session(isolated) as session:
        workspace = create_workspace(session)
        for revision in (1, 2):
            session.add(
                DailyReport(
                    workspace_id=workspace.id,
                    local_date=DAY,
                    revision=revision,
                    timezone="Europe/Istanbul",
                    period_start=at(DAY, 0),
                    period_end=at(DAY, 23),
                    metrics={},
                    definitions_version="1",
                    generated_at=at(DAY, 23),
                )
            )
        session.commit()
    with pytest.raises(RuntimeError, match="multiple report generations"):
        command.downgrade(config, "0014")
    assert "report_items" in inspect(isolated).get_table_names()
    with Session(isolated) as session:
        assert len(list(session.scalars(select(DailyReport)))) == 2
