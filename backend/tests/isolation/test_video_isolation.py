"""Video columns inherit forced media RLS and workspace composite FKs."""

import io
import uuid
from datetime import timedelta

import pytest
from sqlalchemy import select, update
from sqlalchemy.exc import DBAPIError

from app.content.media_cleanup import run_media_cleanup
from app.content.models import MediaAsset
from app.content.router import get_storage
from app.content.video_ingest import stored_video_bytes
from app.core.db import clear_tenant_context, set_tenant_context
from app.integrations.storage.base import build_key
from app.integrations.storage.local import LocalMediaStorage
from tests.factories import knowledge_ctx
from tests.helpers.videos import fake_video
from tests.isolation.test_carousel_isolation import asset
from tests.isolation.test_delegation_suggestions_isolation import as_role


def pair(db, workspace):
    thumbnail = asset(db, workspace)
    thumbnail.kind = "video_thumbnail"
    video = asset(db, workspace)
    video.kind = "video"
    video.duration_ms = 10000
    video.video_codec = "h264"
    video.container = "mp4"
    video.frame_rate = 30
    video.thumbnail_media_asset_id = thumbnail.id
    db.flush()
    return video, thumbnail


def test_foreign_video_and_thumbnail_are_404(two_workspaces, db_session):
    t = two_workspaces
    video, thumb = pair(db_session, t.b.id)
    db_session.commit()
    for row in (video, thumb):
        for workspace in (t.a, t.b):
            for suffix in ("", "/content"):
                response = t.a_client.get(
                    f"/api/v1/workspaces/{workspace.id}/media/{row.id}{suffix}"
                )
                assert response.status_code == 404
        for content_type in ("feed_image", "story_image", "feed_carousel"):
            fields = (
                {"media_asset_ids": [str(row.id)]}
                if content_type == "feed_carousel"
                else {"media_asset_id": str(row.id)}
            )
            result = t.a_client.post(
                f"/api/v1/workspaces/{t.a.id}/content-items",
                headers=t.a_headers,
                json={"content_type": content_type, "title": "Foreign", **fields},
            )
            assert result.status_code == 404
    assert stored_video_bytes(db_session, knowledge_ctx(t.a, t.a_owner, "owner")) == 0
    assert stored_video_bytes(db_session, knowledge_ctx(t.b, t.b_owner, "owner")) == 2


def test_composite_fk_and_runtime_rls(two_workspaces, db_session):
    t, db = two_workspaces, db_session
    own, _ = pair(db, t.a.id)
    foreign, thumb = pair(db, t.b.id)
    aid, bid, wa, wb, tid = own.id, foreign.id, t.a.id, t.b.id, thumb.id
    db.commit()
    db.expunge_all()
    clear_tenant_context(db)
    with as_role(db, "agentnest_app"):
        assert db.scalars(select(MediaAsset)).all() == []
    set_tenant_context(db, wa)
    with as_role(db, "agentnest_app"):
        assert db.scalar(select(MediaAsset.id).where(MediaAsset.id == bid)) is None
        assert (
            db.execute(
                update(MediaAsset).where(MediaAsset.id == bid).values(duration_ms=3000)
            ).rowcount
            == 0
        )
        with pytest.raises(DBAPIError), db.begin_nested():
            db.execute(
                update(MediaAsset).where(MediaAsset.id == aid).values(thumbnail_media_asset_id=tid)
            )
        with pytest.raises(DBAPIError), db.begin_nested():
            db.execute(update(MediaAsset).where(MediaAsset.id == aid).values(workspace_id=wb))
    assert uuid.UUID(str(aid))


def test_upload_and_quota_are_scoped_to_the_caller(two_workspaces, db_session, tmp_path, clock):
    t, db = two_workspaces, db_session
    foreign, thumbnail = pair(db, t.b.id)
    foreign.byte_size, thumbnail.byte_size = 1000000, 1000000
    db.commit()
    storage = LocalMediaStorage(tmp_path / "media", clock)
    t.app.dependency_overrides[get_storage] = lambda: storage
    t.app.state.settings.media_video_workspace_quota_bytes = 1000
    response = t.a_client.post(
        f"/api/v1/workspaces/{t.a.id}/media/video",
        headers=t.a_headers,
        files={"file": ("phone.mp4", fake_video(), "video/mp4")},
    )
    assert response.status_code == 201, response.text
    ids = [uuid.UUID(response.json()[key]) for key in ("id", "thumbnail_media_asset_id")]
    assert list(db.scalars(select(MediaAsset.workspace_id).where(MediaAsset.id.in_(ids)))) == [
        t.a.id,
        t.a.id,
    ]
    assert stored_video_bytes(db, knowledge_ctx(t.a, t.a_owner, "owner")) < 1000
    assert stored_video_bytes(db, knowledge_ctx(t.b, t.b_owner, "owner")) == 2000000


def test_cleanup_preserves_another_tenants_live_video_and_thumbnail(
    two_workspaces, db_session, tmp_path, clock, settings, shared_session_factory
):
    t, db = two_workspaces, db_session
    own, own_thumb = pair(db, t.a.id)
    foreign, foreign_thumb = pair(db, t.b.id)
    for row in (own, own_thumb, foreign_thumb):
        row.created_at = clock.now() - timedelta(days=8)
    foreign.created_at = clock.now()
    objects = []
    for row in (own, own_thumb, foreign, foreign_thumb):
        row.storage_key = build_key(
            row.workspace_id, row.id, clock.now(), "mp4" if row.kind == "video" else "jpg"
        )
        objects.append((row.id, row.storage_key))
    db.commit()
    storage = LocalMediaStorage(tmp_path / "media", clock)
    for _, key in objects:
        storage.put(key, io.BytesIO(b"private object"), "application/octet-stream")
    assert run_media_cleanup(shared_session_factory, storage, settings, clock.now()) == 2
    db.expire_all()
    for row in (own, own_thumb):
        assert row.status == "deleted"
    kept_keys = []
    for row in (foreign, foreign_thumb):
        assert row.status == "ready"
        kept_keys.append(row.storage_key)
    db.commit()
    for key in kept_keys:
        with storage.open(key) as stream:
            assert stream.read() == b"private object"
