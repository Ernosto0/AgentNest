"""Engine, session factory, declarative base, mixins and readiness checks.

Services commit; repositories never do (ADR-003). Constraint names follow the naming
convention below (``pk_``, ``fk_``, ``uq_``, ``ck_``, ``ix_``).
"""

import contextlib
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
from sqlalchemy import (
    DateTime,
    ForeignKey,
    MetaData,
    UniqueConstraint,
    create_engine,
    event,
    func,
    text,
)
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


SESSION_TENANT_KEY = "tenant_workspace_id"


def set_tenant_context(session: Session, workspace_id: uuid.UUID | str) -> None:
    """Set transaction-local tenant context for RLS enforcement (P8-03 / ADR-025 §1.2).

    Validates that ``workspace_id`` is a valid UUID, stores it in ``session.info``
    for automatic re-application on subsequent transactions in this session, and executes
    ``SELECT set_config('app.workspace_id', :ws_id, true)``.
    """
    valid_uuid = str(uuid.UUID(str(workspace_id)))
    session.info[SESSION_TENANT_KEY] = valid_uuid
    session.execute(
        text("SELECT set_config('app.workspace_id', :ws_id, true)"),
        {"ws_id": valid_uuid},
    )


def clear_tenant_context(session: Session) -> None:
    """Clear transaction-local tenant context."""
    session.info.pop(SESSION_TENANT_KEY, None)
    session.execute(text("SELECT set_config('app.workspace_id', '', true)"))


def get_current_tenant_guc(session: Session) -> str | None:
    """Return the current transaction's ``app.workspace_id`` GUC setting, or ``None``."""
    val = session.scalar(text("SELECT nullif(current_setting('app.workspace_id', true), '')"))
    return str(val) if val is not None else None


@contextlib.contextmanager
def tenant_session(
    workspace_id: uuid.UUID | str,
    session_factory: sessionmaker[Session] | None = None,
) -> Iterator[Session]:
    """Scoped session context manager that guarantees tenant context is set and closed cleanly."""
    factory = session_factory or get_session_factory()
    session = factory()
    try:
        set_tenant_context(session, workspace_id)
        yield session
    except BaseException:
        session.rollback()
        raise
    finally:
        session.close()


def make_tenant_session_factory(
    base_factory: sessionmaker[Session],
    workspace_id: uuid.UUID | str,
) -> sessionmaker[Session]:
    """Return a session factory callable that produces sessions bound to ``workspace_id``."""
    valid_uuid = str(uuid.UUID(str(workspace_id)))

    def _factory(**kwargs: Any) -> Session:
        session = base_factory(**kwargs)
        set_tenant_context(session, valid_uuid)
        return session

    return _factory  # type: ignore[return-value]


@event.listens_for(Session, "after_begin")
def _on_session_after_begin(session: Session, transaction: Any, connection: Any) -> None:
    """Ensure newly begun transactions within a session inherit the active tenant context."""
    ws_id = session.info.get(SESSION_TENANT_KEY)
    if ws_id and connection.dialect.name == "postgresql":
        connection.execute(
            text("SELECT set_config('app.workspace_id', :ws_id, true)"),
            {"ws_id": str(ws_id)},
        )


@dataclass(frozen=True)
class ReadinessReport:
    database: bool
    migrations: bool
    current_revision: str | None
    head_revision: str | None

    @property
    def ready(self) -> bool:
        return self.database and self.migrations


def _alembic_script_directory() -> ScriptDirectory:
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    return ScriptDirectory.from_config(config)


def migration_head() -> str | None:
    return _alembic_script_directory().get_current_head()


def migration_revisions() -> tuple[str, ...]:
    """Return all Alembic revision IDs known to this code version (oldest to newest)."""
    revs = [rev.revision for rev in _alembic_script_directory().walk_revisions()]
    revs.reverse()
    return tuple(revs)


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
