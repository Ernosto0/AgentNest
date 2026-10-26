"""Upgrade populated 0018 data without enabling the agent; reject evidence loss on rollback."""

import uuid
from collections.abc import Iterator

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from app.core.db import BACKEND_DIR


@pytest.fixture
def prior_schema(engine: Engine) -> Iterator[tuple[Config, Engine]]:
    schema = "agent_upgrade_" + uuid.uuid4().hex
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
        command.upgrade(config, "0018")
        yield config, isolated
    finally:
        isolated.dispose()
        with engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))


def test_upgrade_backfills_legacy_and_downgrade_refuses_agent_evidence(
    prior_schema: tuple[Config, Engine],
) -> None:
    config, engine = prior_schema
    workspace_id, account_id = uuid.uuid4(), uuid.uuid4()
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO workspaces "
                "(id,name,slug,business_category,market,default_locale,timezone,currency) "
                "VALUES (:w,'Old Shop',:slug,'services','global','en','UTC','USD')"
            ),
            {"w": workspace_id, "slug": f"old-{workspace_id.hex[:12]}"},
        )
        connection.execute(
            text(
                "INSERT INTO social_accounts (id,workspace_id,provider_kind,external_account_id) "
                "VALUES (:a,:w,'mock','old-shop')"
            ),
            {"a": account_id, "w": workspace_id},
        )
    command.upgrade(config, "0019")
    with engine.begin() as connection:
        row = connection.execute(
            text(
                "SELECT controller_mode,state,controller_epoch,goals FROM account_agents "
                "WHERE workspace_id=:w AND social_account_id=:a"
            ),
            {"w": workspace_id, "a": account_id},
        ).one()
        assert row.controller_mode == "legacy" and row.state == "inactive"
        assert row.controller_epoch == 0 and row.goals == {}
        assert connection.scalar(text("SELECT count(*) FROM agent_delegations")) == 0
        assert (
            connection.scalar(
                text("SELECT count(*) FROM agent_runs WHERE task='account_agent_step'")
            )
            == 0
        )
        thread_id = uuid.uuid4()
        connection.execute(
            text(
                "INSERT INTO agent_threads "
                "(id,workspace_id,social_account_id,surface,source_ref) "
                "VALUES (:id,:w,:a,'owner_task','task-1')"
            ),
            {"id": thread_id, "w": workspace_id, "a": account_id},
        )
    with pytest.raises(RuntimeError, match="agent evidence must be preserved"):
        command.downgrade(config, "0018")
    with engine.begin() as connection:
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "0019"
        connection.execute(text("DELETE FROM agent_threads WHERE id=:id"), {"id": thread_id})
    command.downgrade(config, "0018")
    with engine.begin() as connection:
        assert connection.scalar(text("SELECT count(*) FROM social_accounts")) == 1
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "0018"
    command.upgrade(config, "0019")
