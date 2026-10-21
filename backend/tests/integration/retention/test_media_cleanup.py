"""``media_cleanup`` (plan H18): orphaned and old published images are deleted from disk and their
rows marked ``deleted``; the media of a scheduled (or any unfinished) item is kept.

``ago(d, s)`` is an instant ``d`` days and ``s`` seconds before ``NOW``: the extra second puts it
just past the limit, ``-1`` just inside it.
"""

import io
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.content import media_cleanup
from app.content.models import ContentItem, MediaAsset
from app.core.clock import FrozenClock
from app.core.config import Settings
from app.integrations.storage.base import build_key
from app.integrations.storage.local import LocalMediaStorage
from app.jobs.models import Job
from app.jobs.testing import run_due_jobs
from tests.factories import add_member, create_user, create_workspace
from tests.helpers.env import Env
from tests.helpers.publishing import Publishing
from tests.helpers.reporting import Builder
from tests.integration.content.conftest import app as app  # noqa: F401  (fixture)
from tests.integration.content.conftest import env as env  # noqa: F401  (fixture)
from tests.integration.content.conftest import make_pub as make_pub  # noqa: F401  (fixture)
from tests.integration.content.conftest import media_root as media_root  # noqa: F401  (fixture)

NOW = datetime(2026, 10, 21, 2, 30, tzinfo=UTC)
SessionFactory = sessionmaker[Session]


def ago(days: int, seconds: int = 0) -> datetime:
    return NOW - timedelta(days=days, seconds=seconds)


class Studio:
    """A workspace, a storage in a temp folder and helpers to create assets and items."""

    def __init__(self, session: Session, root: Path, settings: Settings) -> None:
        self.session = session
        self.settings = settings.model_copy(update={"media_local_root": str(root)})
        self.storage = LocalMediaStorage(root, FrozenClock(NOW))
        self.workspace = create_workspace(session)
        self.user = create_user(session)
        add_member(session, self.workspace, self.user, "owner")
        self.builder = Builder(session, self.workspace, self.user)

    def asset(self, created_at: datetime, *, status: str = "ready") -> MediaAsset:
        key = build_key(self.workspace.id, uuid.uuid4(), created_at)
        self.storage.put(key, io.BytesIO(b"\xff\xd8jpeg"), "image/jpeg")
        asset = MediaAsset(
            workspace_id=self.workspace.id,
            storage_backend="local",
            storage_key=key,
            mime_type="image/jpeg",
            byte_size=6,
            width=10,
            height=10,
            sha256="a" * 64,
            status=status,
            created_at=created_at,
        )
        self.session.add(asset)
        self.session.flush()
        return asset

    def item(
        self, asset: MediaAsset, status: str, *, published_at: datetime | None = None
    ) -> ContentItem:
        return self.builder.content(status, media_asset_id=asset.id, published_at=published_at)

    def has_file(self, asset: MediaAsset) -> bool:
        return (self.settings.media_root / asset.storage_key).exists()

    def run(self, session_factory: SessionFactory, now: datetime = NOW) -> int:
        self.session.commit()
        deleted = media_cleanup.run_media_cleanup(session_factory, self.storage, self.settings, now)
        self.session.expire_all()
        return deleted


@pytest.fixture
def studio(db_session: Session, tmp_path: Path, settings: Settings) -> Studio:
    return Studio(db_session, tmp_path / "media", settings)


def test_an_orphan_is_deleted_after_7_days_and_not_before(
    studio: Studio, shared_session_factory: SessionFactory
) -> None:
    young = studio.asset(ago(7, -1))
    old = studio.asset(ago(7, 1))
    assert studio.run(shared_session_factory) == 1

    assert (young.status, studio.has_file(young)) == ("ready", True)
    assert (old.status, studio.has_file(old)) == ("deleted", False)
    assert old.deleted_at == NOW  # the row stays, for its foreign keys


def test_published_media_goes_90_days_after_publication(
    studio: Studio, shared_session_factory: SessionFactory
) -> None:
    recent = studio.asset(ago(300))
    studio.item(recent, "published", published_at=ago(90, -1))
    old = studio.asset(ago(300))
    studio.item(old, "published", published_at=ago(90, 1))
    assert studio.run(shared_session_factory) == 1

    assert (recent.status, studio.has_file(recent)) == ("ready", True)
    assert (old.status, studio.has_file(old)) == ("deleted", False)


@pytest.mark.parametrize(
    "status", ["draft", "pending_approval", "scheduled", "retry_scheduled", "on_hold", "failed"]
)
def test_the_media_of_an_unfinished_item_is_kept_however_old(
    studio: Studio, shared_session_factory: SessionFactory, status: str
) -> None:
    asset = studio.asset(ago(400))
    studio.item(asset, status)
    assert studio.run(shared_session_factory) == 0
    assert (asset.status, studio.has_file(asset)) == ("ready", True)


def test_the_media_of_a_scheduled_item_is_kept_next_to_deleted_orphans(
    studio: Studio, shared_session_factory: SessionFactory
) -> None:
    scheduled = studio.asset(ago(30))
    studio.item(scheduled, "scheduled")
    orphan = studio.asset(ago(30))
    assert studio.run(shared_session_factory) == 1
    assert studio.has_file(scheduled) and not studio.has_file(orphan)


def test_an_asset_used_by_an_old_post_and_a_live_item_is_kept(
    studio: Studio, shared_session_factory: SessionFactory
) -> None:
    asset = studio.asset(ago(300))
    studio.item(asset, "published", published_at=ago(200))
    studio.item(asset, "scheduled")
    assert studio.run(shared_session_factory) == 0
    assert studio.has_file(asset)


def test_a_published_item_without_a_publication_time_is_not_old(
    studio: Studio, shared_session_factory: SessionFactory
) -> None:
    asset = studio.asset(ago(300))
    studio.item(asset, "published", published_at=None)
    assert studio.run(shared_session_factory) == 0


def test_a_run_is_idempotent_and_a_missing_file_is_not_an_error(
    studio: Studio, shared_session_factory: SessionFactory
) -> None:
    gone = studio.asset(ago(30))
    (studio.settings.media_root / gone.storage_key).unlink()  # e.g. a crash after the delete
    already = studio.asset(ago(30), status="deleted")
    assert studio.run(shared_session_factory) == 1
    assert gone.status == "deleted" and already.status == "deleted"
    assert studio.run(shared_session_factory) == 0


def test_the_file_goes_first_and_a_failing_delete_leaves_the_row_for_the_next_run(
    studio: Studio, shared_session_factory: SessionFactory
) -> None:
    broken = studio.asset(ago(30))
    fine = studio.asset(ago(30))
    studio.session.commit()
    seen: dict[uuid.UUID, str] = {}

    class FlakyStorage:
        backend = "local"

        def delete(self, key: str) -> None:
            # The row is still ``ready`` while its file is removed (file first, then the row).
            with shared_session_factory() as other:
                asset = other.scalar(select(MediaAsset).where(MediaAsset.storage_key == key))
                assert asset is not None
                seen[asset.id] = asset.status
            if key == broken.storage_key:
                raise OSError("disk unavailable")
            studio.storage.delete(key)

    deleted = media_cleanup.run_media_cleanup(
        shared_session_factory,
        FlakyStorage(),  # type: ignore[arg-type]
        studio.settings,
        NOW,
    )
    studio.session.expire_all()
    assert deleted == 1
    assert seen == {broken.id: "ready", fine.id: "ready"}
    assert (broken.status, fine.status) == ("ready", "deleted")
    assert studio.run(shared_session_factory) == 1  # the next run takes the one that failed
    assert broken.status == "deleted"


def test_more_than_one_page_of_assets_is_processed(
    studio: Studio, shared_session_factory: SessionFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(media_cleanup, "PAGE", 2)
    assets = [studio.asset(ago(30)) for _ in range(5)]
    assert studio.run(shared_session_factory) == 5
    assert all(a.status == "deleted" and not studio.has_file(a) for a in assets)


# --- the job --------------------------------------------------------------------------------


def _tick(session: Session, at: datetime) -> int:
    count = media_cleanup.enqueue_media_cleanup(session, FrozenClock(at))
    session.commit()
    return count


def test_one_job_per_utc_day_from_02_30(
    studio: Studio,
    db_session: Session,
    shared_session_factory: SessionFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(media_cleanup, "get_settings", lambda: studio.settings)
    orphan = studio.asset(ago(30))
    studio.session.commit()

    assert _tick(db_session, datetime(2026, 10, 21, 2, 29, tzinfo=UTC)) == 0
    assert _tick(db_session, datetime(2026, 10, 21, 2, 30, tzinfo=UTC)) == 1
    job = db_session.scalar(select(Job).where(Job.job_type == "media_cleanup"))
    assert job is not None and job.dedup_key == "media_cleanup:2026-10-21"
    assert job.workspace_id is None and job.max_attempts == 1
    assert _tick(db_session, datetime(2026, 10, 21, 2, 31, tzinfo=UTC)) == 0  # queued

    assert run_due_jobs(FrozenClock(NOW), session_factory=shared_session_factory) == 1
    db_session.expire_all()
    assert orphan.status == "deleted" and not studio.has_file(orphan)
    assert job.status == "succeeded"
    assert _tick(db_session, datetime(2026, 10, 21, 12, 0, tzinfo=UTC)) == 0  # done for today
    assert _tick(db_session, datetime(2026, 10, 22, 2, 30, tzinfo=UTC)) == 1


# --- what the owner sees ----------------------------------------------------------------------


def test_the_content_detail_says_the_image_was_deleted(
    env: Env,  # noqa: F811
    make_pub: Callable[..., Publishing],  # noqa: F811
    shared_session_factory: SessionFactory,
    settings: Settings,
    media_root: Path,  # noqa: F811
) -> None:
    pub = make_pub()
    item = pub.scheduled()
    assert pub.execute(item).kind == "published"
    published = pub.reload(item)
    assert published.media_asset_id is not None
    path = f"/content-items/{published.id}"

    before = env.call(env.owner, "GET", path).json()
    assert before["media_deleted"] is False
    assert (
        env.call(env.owner, "GET", f"/media/{published.media_asset_id}/content").status_code == 200
    )

    later = pub.clock.now() + timedelta(days=91)
    cfg = settings.model_copy(update={"media_local_root": str(media_root)})
    assert media_cleanup.run_media_cleanup(shared_session_factory, pub.storage, cfg, later) == 1
    env.session.expire_all()

    after = env.call(env.owner, "GET", path).json()
    assert after["media_deleted"] is True and after["media_asset_id"] == str(
        published.media_asset_id
    )
    assert (
        env.call(env.owner, "GET", f"/media/{published.media_asset_id}/content").status_code == 404
    )
