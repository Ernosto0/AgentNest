"""Upgrade the real prior schema and refuse a destructive deletion-event downgrade."""

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
    schema = "webhook_delete_" + uuid.uuid4().hex
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
        command.upgrade(config, "0015")
        yield config, isolated
    finally:
        isolated.dispose()
        with engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))


def test_upgrade_accepts_delete_preserves_existing_and_downgrade_refuses_loss(
    prior_schema: tuple[Config, Engine],
) -> None:
    config, engine = prior_schema
    insert = text(
        "INSERT INTO inbound_events "
        "(id,correlation_id,provider_kind,dedup_key,event_type,status,is_simulated) "
        "VALUES (:id,:id,'mock',:key,:kind,'ignored',true)"
    )
    with engine.begin() as connection:
        connection.execute(insert, {"id": uuid.uuid4(), "key": "original", "kind": "message"})
    command.upgrade(config, "0016")
    with engine.begin() as connection:
        connection.execute(insert, {"id": uuid.uuid4(), "key": "unsend", "kind": "delete"})
    with pytest.raises(RuntimeError, match="deletion webhook events must be preserved"):
        command.downgrade(config, "0015")
    with engine.begin() as connection:
        assert connection.scalar(text("SELECT count(*) FROM inbound_events")) == 2
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "0016"
        connection.execute(text("DELETE FROM inbound_events WHERE event_type='delete'"))
    command.downgrade(config, "0015")
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM inbound_events")) == 1
        constraint = connection.scalar(
            text(
                "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
                "WHERE conrelid='inbound_events'::regclass "
                "AND conname='ck_inbound_events_event_type'"
            )
        )
        assert "delete" not in constraint
    command.upgrade(config, "0016")
