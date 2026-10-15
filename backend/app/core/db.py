"""Engine, session factory, declarative base, mixins and readiness checks.

Services commit; repositories never do (ADR-003). Constraint names follow the naming
convention below (``pk_``, ``fk_``, ``uq_``, ``ck_``, ``ix_``).
"""

import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import DateTime, ForeignKey, MetaData, UniqueConstraint, create_engine, func, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    Session,
    declared_attr,
    mapped_column,
    sessionmaker,
)
from sqlalchemy.types import Uuid

from app.core.config import get_settings
from app.core.ids import new_id

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_N_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

BACKEND_DIR = Path(__file__).resolve().parents[2]


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)
    type_annotation_map = {datetime: DateTime(timezone=True), uuid.UUID: Uuid(as_uuid=True)}


class TimestampMixin:
    """``created_at`` / ``updated_at`` as timestamptz (UTC) for mutable tables."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class WorkspaceScopedMixin:
    """Tenant table: ``workspace_id NOT NULL`` plus ``unique (workspace_id, id)`` (INV-01).

    The unique constraint is the target of composite foreign keys from tenant children.
    Models that declare their own ``__table_args__`` must keep ``workspace_unique_constraint()``.
    """

    @declared_attr
    def workspace_id(cls) -> Mapped[uuid.UUID]:
        return mapped_column(
            ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True
        )

    @declared_attr.directive
    def __table_args__(cls) -> tuple[Any, ...]:
        return (workspace_unique_constraint(),)


def workspace_unique_constraint() -> UniqueConstraint:
    return UniqueConstraint("workspace_id", "id")


class UUIDPrimaryKeyMixin:
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)


@lru_cache
def get_engine() -> Engine:
    return create_engine(get_settings().database_url, pool_pre_ping=True, future=True)


@lru_cache
def get_session_factory() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), expire_on_commit=False, autoflush=False)


def reset_engine_cache() -> None:
    """Dispose cached engine/factory (tests that change DATABASE_URL)."""
    if get_engine.cache_info().currsize:
        get_engine().dispose()
    get_engine.cache_clear()
    get_session_factory.cache_clear()


def get_db() -> Iterator[Session]:
    """FastAPI dependency: one session per request. The service commits; errors roll back."""
    session = get_session_factory()()
    try:
        yield session
    except BaseException:
        session.rollback()
        raise
    finally:
        session.close()


@dataclass(frozen=True)
class ReadinessReport:
    database: bool
    migrations: bool
    current_revision: str | None
    head_revision: str | None

    @property
    def ready(self) -> bool:
        return self.database and self.migrations


def migration_head() -> str | None:
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    return ScriptDirectory.from_config(config).get_current_head()


def check_readiness(engine: Engine | None = None) -> ReadinessReport:
    """DB reachable and the applied migration equals the code's head revision."""
    engine = engine or get_engine()
    head = migration_head()
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
            current = MigrationContext.configure(conn).get_current_revision()
    except SQLAlchemyError:
        return ReadinessReport(False, False, None, head)
    return ReadinessReport(True, current is not None and current == head, current, head)
