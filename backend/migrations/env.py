"""Alembic environment: uses the application metadata and settings."""

from alembic import context
from sqlalchemy import create_engine, pool

from app.core.config import get_settings
from app.core.db import Base

# Import every model module so that its tables are registered on Base.metadata.
# Later phases add their modules here.
import app.ai.models  # noqa: F401  # isort: skip
import app.approvals.models  # noqa: F401  # isort: skip
import app.audit.models  # noqa: F401  # isort: skip
import app.commands.models  # noqa: F401  # isort: skip
import app.identity.models  # noqa: F401  # isort: skip
import app.integrations.instagram.models  # noqa: F401  # isort: skip
import app.jobs.models  # noqa: F401  # isort: skip
import app.knowledge.models  # noqa: F401  # isort: skip
import app.notifications.models  # noqa: F401  # isort: skip

config = context.config
target_metadata = Base.metadata


def _url() -> str:
    return config.get_main_option("sqlalchemy.url") or get_settings().database_url


def run_migrations_offline() -> None:
    context.configure(
        url=_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(_url(), poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
