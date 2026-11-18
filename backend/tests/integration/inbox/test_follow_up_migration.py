from alembic import command
from sqlalchemy import text

from tests.integration.agent.test_migration import prior_schema

__all__ = ["prior_schema"]


def test_follow_up_up_down_up(prior_schema):  # type: ignore[no-untyped-def]
    config, engine = prior_schema
    command.upgrade(config, "0061")
    command.upgrade(config, "0090")
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "0090"
        assert connection.scalar(text("SELECT to_regclass('conversation_follow_ups')")) is not None
    command.downgrade(config, "0061")
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT to_regclass('conversation_follow_ups')")) is None
    command.upgrade(config, "0090")
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "0090"
