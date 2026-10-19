"""Shared fixtures.

Database strategy (testing-strategy.md §2): the test database is rebuilt and migrated once
per session. By default each test runs in an outer transaction with SAVEPOINTs and is rolled
back. Tests marked ``@pytest.mark.commits`` use real commits and truncate all tables after.
"""

import os
from collections.abc import Callable, Iterator

# --- environment must be fixed before the app is imported -------------------------------
os.environ["APP_ENV"] = "test"
os.environ.setdefault("LOG_LEVEL", "WARNING")

from app.core.config import Settings, get_settings  # noqa: E402

# Tests always run against TEST_DATABASE_URL (from the environment or .env).
os.environ["DATABASE_URL"] = Settings().test_database_url
get_settings.cache_clear()

import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.engine import Engine, make_url  # noqa: E402
from sqlalchemy.orm import Session, sessionmaker  # noqa: E402

from app.core.clock import FrozenClock  # noqa: E402
from app.core.db import BACKEND_DIR, Base, get_db, get_engine  # noqa: E402
from app.handlers import load_handlers  # noqa: E402
from app.main import create_app  # noqa: E402

# Register every job handler and approval subject once, before any test snapshots a registry:
# a module first imported inside a snapshot would lose its registrations when it is restored.
load_handlers()


@pytest.fixture(scope="session")
def settings() -> Settings:
    cfg = get_settings()
    assert cfg.app_env == "test"
    database = make_url(cfg.database_url).database or ""
    # Safety: never run destructive test setup against a development database.
    assert database.endswith("_test"), f"refusing to run tests against database {database!r}"
    return cfg


@pytest.fixture(scope="session")
def engine(settings: Settings) -> Iterator[Engine]:
    eng = get_engine()
    with eng.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    command.upgrade(config, "head")  # also proves the migrations work
    yield eng
    eng.dispose()


def _truncate_all(engine: Engine) -> None:
    tables = ", ".join(f'"{t.name}"' for t in Base.metadata.sorted_tables)
    with engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))


@pytest.fixture
def db_session(engine: Engine, request: pytest.FixtureRequest) -> Iterator[Session]:
    """A session whose changes (including ``commit()``) are rolled back after the test."""
    if request.node.get_closest_marker("commits"):
        pytest.fail("tests marked 'commits' must use the session_factory fixture")
    connection = engine.connect()
    outer = connection.begin()
    session = Session(
        bind=connection,
        join_transaction_mode="create_savepoint",
        expire_on_commit=False,
        autoflush=False,
    )
    try:
        yield session
    finally:
        session.close()
        outer.rollback()
        connection.close()


@pytest.fixture
def session_factory(engine: Engine) -> Iterator[sessionmaker[Session]]:
    """Real commits. Tables are truncated afterwards. Use with ``@pytest.mark.commits``."""
    factory = sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)
    _truncate_all(engine)
    try:
        yield factory
    finally:
        _truncate_all(engine)


@pytest.fixture
def shared_session_factory(db_session: Session) -> sessionmaker[Session]:
    """Sessions that commit into the test's outer transaction (rolled back with the test).

    For code that opens its own short sessions (the task runner, job handlers) but is tested
    without real commits: ``db_session`` sees everything those sessions write.
    """
    return sessionmaker(
        bind=db_session.get_bind(),
        expire_on_commit=False,
        autoflush=False,
        join_transaction_mode="create_savepoint",
    )


@pytest.fixture
def clock() -> FrozenClock:
    return FrozenClock()


@pytest.fixture
def build_app(
    settings: Settings, clock: FrozenClock, db_session: Session
) -> Callable[..., FastAPI]:
    """Build an app on the test session; keyword arguments override settings."""

    def _build(**overrides: object) -> FastAPI:
        application = create_app(settings.model_copy(update=overrides), clock)

        def _get_db() -> Iterator[Session]:
            yield db_session

        application.dependency_overrides[get_db] = _get_db
        return application

    return _build


@pytest.fixture
def app(build_app: Callable[..., FastAPI]) -> FastAPI:
    return build_app()


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def make_client(app: FastAPI) -> Iterator[Callable[[], TestClient]]:
    """Factory for additional independent clients (separate cookie jars)."""
    clients: list[TestClient] = []

    def _make() -> TestClient:
        c = TestClient(app)
        clients.append(c)
        return c

    yield _make
    for c in clients:
        c.close()
