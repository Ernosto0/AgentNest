from alembic import command
from sqlalchemy import text

from tests.integration.agent.test_migration import prior_schema

__all__ = ["prior_schema"]

COLUMNS = (
    "SELECT count(*) FROM information_schema.columns "
    "WHERE table_schema = current_schema() AND column_name = 'message_tag' "
    "AND table_name IN ('reply_drafts', 'sim_sent_messages')"
)


def test_message_tag_up_down_up(prior_schema):  # type: ignore[no-untyped-def]
    config, engine = prior_schema
    command.upgrade(config, "0090")
    with engine.connect() as connection:
        assert connection.scalar(text(COLUMNS)) == 0
    command.upgrade(config, "0091")
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "0091"
        assert connection.scalar(text(COLUMNS)) == 2
    command.downgrade(config, "0090")
    with engine.connect() as connection:
        assert connection.scalar(text(COLUMNS)) == 0
    command.upgrade(config, "0091")
    with engine.connect() as connection:
        assert connection.scalar(text(COLUMNS)) == 2
