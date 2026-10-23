"""P5-05: the mock publishing wiring: registry, settings, capabilities, migration 0011."""

import importlib.util
import io
import uuid
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from app.core.clock import FrozenClock
from app.core.config import Settings
from app.core.db import BACKEND_DIR
from app.integrations.instagram.base import AccountRef, ContainerSpec
from app.integrations.instagram.errors import ProviderInvalidRequest, ProviderRateLimited
from app.integrations.instagram.models import SocialAccount
from app.integrations.instagram.registry import get_provider
from app.integrations.storage.base import build_key
from app.integrations.storage.local import LocalMediaStorage
from app.operations.accounts import MOCK_CAPABILITIES
from tests.contract.test_instagram_provider_contract import jpeg_bytes
from tests.factories import create_workspace

MIGRATION = BACKEND_DIR / "migrations" / "versions" / "20261020_0011_phase_5_mock_capabilities.py"


def test_mock_accounts_get_the_documented_capability_names() -> None:
    assert MOCK_CAPABILITIES == {
        "messaging": True,
        "publish_feed_image": True,
        "publish_story_image": True,
    }
    assert "content_publish" not in MOCK_CAPABILITIES


def _settings(tmp_path: Path, **overrides: object) -> Settings:
    return Settings(_env_file=None, media_local_root=str(tmp_path), **overrides)  # type: ignore[call-arg]


def test_the_registry_wires_storage_and_the_publishing_settings_into_the_mock(
    db_session: Session,
    shared_session_factory: sessionmaker[Session],
    clock: FrozenClock,
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path, sim_container_delay_seconds=0, publish_daily_limit=1)
    workspace = create_workspace(db_session, name="Wiring")
    row = SocialAccount(
        workspace_id=workspace.id,
        provider_kind="mock",
        external_account_id="biz-w",
        status="connected",
    )
    db_session.add(row)
    db_session.commit()
    account = AccountRef(row.id, workspace.id, "biz-w")
    provider = get_provider(
        "mock", settings=settings, session_factory=shared_session_factory, clock=clock
    )
    storage = LocalMediaStorage(tmp_path, clock)
    key = build_key(workspace.id, uuid.uuid4(), clock.now())
    storage.put(key, io.BytesIO(jpeg_bytes()), "image/jpeg")
    spec = ContainerSpec("IMAGE", storage.public_fetch_url(key, 60), "x")

    first = provider.create_media_container(account, spec)  # no delay: finished at once
    assert provider.get_container_status(account, first).status_code == "FINISHED"
    provider.publish_container(account, first)
    assert provider.get_publishing_quota(account).limit == 1

    second = provider.create_media_container(account, spec)
    with pytest.raises(ProviderRateLimited):  # the configured limit applies
        provider.publish_container(account, second)


def test_without_a_buildable_storage_messaging_still_works_and_publishing_fails(
    shared_session_factory: sessionmaker[Session], clock: FrozenClock
) -> None:
    settings = Settings(
        _env_file=None,
        media_storage_backend="s3",
        s3_bucket="test-bucket",
        s3_access_key_id="synthetic-access-id",
        s3_secret_access_key="synthetic-secret-key",
    )  # type: ignore[call-arg]
    provider = get_provider(
        "mock", settings=settings, session_factory=shared_session_factory, clock=clock
    )
    account = AccountRef(uuid.uuid4(), uuid.uuid4(), "x")
    assert provider.get_publishing_quota(account).used == 0  # reads do not need the storage
    with pytest.raises(RuntimeError, match="media storage"):
        provider.create_media_container(account, ContainerSpec("IMAGE", "localmedia:x?exp=1", "x"))
    with pytest.raises(ProviderInvalidRequest):
        provider.get_container_status(account, "nope")


# --- migration 0011 (G4) ----------------------------------------------------------------------


def _migration() -> object:
    spec = importlib.util.spec_from_file_location("migration_0011", MIGRATION)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _account(
    db: Session, *, kind: str, external: str, capabilities: dict[str, object]
) -> uuid.UUID:
    workspace = create_workspace(db, name=f"M-{external}")
    row = SocialAccount(
        workspace_id=workspace.id,
        provider_kind=kind,
        external_account_id=external,
        status="connected",
        capabilities=capabilities,
    )
    db.add(row)
    db.commit()
    return row.id


def _capabilities(db: Session, account_id: uuid.UUID) -> dict[str, object]:
    db.expire_all()
    row = db.get(SocialAccount, account_id)
    assert row is not None
    return dict(row.capabilities)


def test_the_migration_renames_the_mock_capability_and_keeps_its_value(db_session: Session) -> None:
    module = _migration()
    allowed = _account(
        db_session,
        kind="mock",
        external="m-1",
        capabilities={"messaging": True, "content_publish": True},
    )
    degraded = _account(
        db_session,
        kind="mock",
        external="m-2",
        capabilities={"messaging": False, "content_publish": False},
    )
    meta = _account(db_session, kind="meta", external="m-3", capabilities={"content_publish": True})

    db_session.execute(text(module.UPGRADE_SQL))  # type: ignore[attr-defined]

    assert _capabilities(db_session, allowed) == {
        "messaging": True,
        "publish_feed_image": True,
        "publish_story_image": True,
    }
    assert _capabilities(db_session, degraded) == {
        "messaging": False,
        "publish_feed_image": False,
        "publish_story_image": False,
    }
    assert _capabilities(db_session, meta) == {"content_publish": True}  # only mock rows change

    db_session.execute(text(module.UPGRADE_SQL))  # idempotent
    assert _capabilities(db_session, allowed)["publish_feed_image"] is True

    db_session.execute(text(module.DOWNGRADE_SQL))  # type: ignore[attr-defined]
    assert _capabilities(db_session, allowed) == {"messaging": True, "content_publish": True}
    assert _capabilities(db_session, degraded) == {"messaging": False, "content_publish": False}
