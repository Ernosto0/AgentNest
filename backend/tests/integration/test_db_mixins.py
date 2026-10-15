"""Tenant mixin (INV-01): composite uniqueness is the target of composite FKs."""

import uuid

import pytest
from sqlalchemy import ForeignKeyConstraint, Text, inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from app.core.db import (
    NAMING_CONVENTION,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
    WorkspaceScopedMixin,
    workspace_unique_constraint,
)


class _Base(DeclarativeBase):
    from sqlalchemy import MetaData

    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class _Workspace(UUIDPrimaryKeyMixin, _Base):
    __tablename__ = "workspaces"  # stand-in so the mixin's FK resolves in this private metadata


class _Parent(WorkspaceScopedMixin, UUIDPrimaryKeyMixin, TimestampMixin, _Base):
    __tablename__ = "mixin_parents"
    name: Mapped[str] = mapped_column(Text)


class _Child(UUIDPrimaryKeyMixin, _Base):
    """Composite FK: a child can only reference a parent of the same workspace."""

    __tablename__ = "mixin_children"
    __table_args__ = (
        workspace_unique_constraint(),
        ForeignKeyConstraint(
            ["workspace_id", "parent_id"], ["mixin_parents.workspace_id", "mixin_parents.id"]
        ),
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column()
    parent_id: Mapped[uuid.UUID] = mapped_column()


@pytest.fixture
def tables(db_session: Session) -> Session:
    # Postgres DDL is transactional: everything below is rolled back with the test. A private
    # schema keeps the stand-in ``workspaces`` table away from the real one in ``public``.
    connection = db_session.connection()
    connection.execute(text("CREATE SCHEMA mixin_test"))
    connection.execute(text("SET LOCAL search_path TO mixin_test"))
    _Base.metadata.create_all(connection)
    return db_session


def test_mixin_adds_workspace_id_and_composite_unique(tables: Session) -> None:
    inspector = inspect(tables.connection())
    columns = {c["name"]: c for c in inspector.get_columns("mixin_parents")}
    assert columns["workspace_id"]["nullable"] is False
    uniques = [u["column_names"] for u in inspector.get_unique_constraints("mixin_parents")]
    assert ["workspace_id", "id"] in uniques
    assert {"created_at", "updated_at"} <= set(columns)


def test_cross_workspace_reference_is_rejected_by_the_database(tables: Session) -> None:
    ws_a, ws_b = uuid.uuid4(), uuid.uuid4()
    tables.add_all([_Workspace(id=ws_a), _Workspace(id=ws_b)])
    tables.flush()  # no relationship() links these models, so order the inserts explicitly
    parent = _Parent(workspace_id=ws_a, name="p")
    tables.add(parent)
    tables.flush()

    tables.add(_Child(workspace_id=ws_a, parent_id=parent.id))
    tables.flush()  # same workspace: fine

    tables.add(_Child(workspace_id=ws_b, parent_id=parent.id))
    with pytest.raises(IntegrityError):
        tables.flush()  # foreign workspace: the composite FK refuses it
