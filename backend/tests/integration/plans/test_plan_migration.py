"""The plans migration: existing workspaces get growth/trial starting now; down and up again."""

import uuid

from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, text

from app.core.db import BACKEND_DIR


def test_migration_0050_backfills_existing_workspaces_and_reverses_cleanly(engine: Engine) -> None:
    schema = "plans_mig_" + uuid.uuid4().hex
    with engine.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    url = engine.url.update_query_dict({"options": f"-csearch_path={schema}"})
    isolated = create_engine(url)
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    config.set_main_option(
        "sqlalchemy.url", url.render_as_string(hide_password=False).replace("%", "%%")
    )
    workspace_id = uuid.uuid4()
    try:
        command.upgrade(config, "0049")
        with isolated.begin() as connection:
            assert connection.scalar(text("SELECT to_regclass('workspace_plans')")) is None
            connection.execute(
                text(
                    "INSERT INTO workspaces (id, name, slug, business_category, market, "
                    "default_locale, timezone, currency) VALUES (:id, 'Old', 'old', "
                    "'other', 'tr', 'tr', 'Europe/Istanbul', 'TRY')"
                ),
                {"id": workspace_id},
            )
        command.upgrade(config, "0050")
        with isolated.connect() as connection:
            row = connection.execute(
                text(
                    "SELECT plan, monthly_quota, quota_override, status, used, "
                    "period_end > period_start AS ok, abs(extract(epoch FROM now() - "
                    "period_start)) < 60 AS starts_now, warned_80, warned_100, warned_paused "
                    "FROM workspace_plans WHERE workspace_id = :id"
                ),
                {"id": workspace_id},
            ).one()
            assert tuple(row) == ("growth", 2500, None, "trial", 0, True, True, False, False, False)
            assert connection.scalar(text("SELECT to_regclass('reply_usage')")) is not None
        command.downgrade(config, "0049")
        with isolated.connect() as connection:
            assert connection.scalar(text("SELECT to_regclass('workspace_plans')")) is None
            assert connection.scalar(text("SELECT to_regclass('reply_usage')")) is None
        command.upgrade(config, "0050")  # and back up again
        with isolated.connect() as connection:
            assert connection.scalar(text("SELECT count(*) FROM workspace_plans")) == 1
    finally:
        isolated.dispose()
        with engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
