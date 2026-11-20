"""Offline streamed video ingest, rollback, kinds and retention."""

import hashlib
import io
from datetime import timedelta

import pytest
from sqlalchemy import select

from app.audit.models import AuditLog
from app.content import video_ingest
from app.content.media_cleanup import run_media_cleanup
from app.content.models import MediaAsset
from app.content.router import get_storage
from app.integrations.storage.local import LocalMediaStorage
from app.integrations.video.base import VideoProbeUnavailable
from app.integrations.video.fake import FakeVideoProber
from tests.helpers.videos import fake_video


def upload(env, raw=None):
    return env.call(
        env.owner,
        "POST",
        "/media/video",
        files={
            "file": ("phone.mp4", fake_video() if raw is None else raw, "video/mp4"),
        },
    )


def assets(env):
    return list(
        env.session.scalars(select(MediaAsset).where(MediaAsset.workspace_id == env.workspace.id))
    )


def audits(env, action):
    return list(
        env.session.scalars(
            select(AuditLog).where(
                AuditLog.workspace_id == env.workspace.id, AuditLog.action == action
            )
        )
    )


def test_video_and_thumbnail_roundtrip(env, media_root):
    raw = fake_video()
    response = upload(env, raw)
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["kind"] == "video" and body["duration_ms"] == 10000
    assert body["video_codec"] == "h264" and body["audio_codec"] == "aac"
    assert body["frame_rate"] == 30 and body["container"] == "mp4"
    video = env.session.get(MediaAsset, body["id"])
    thumb = env.session.get(MediaAsset, body["thumbnail_media_asset_id"])
    assert thumb.kind == "video_thumbnail" and thumb.mime_type == "image/jpeg"
    assert (media_root / video.storage_key).read_bytes() == raw
    assert video.sha256 == hashlib.sha256(raw).hexdigest()
    assert env.call(env.owner, "GET", f"/media/{video.id}").json()["kind"] == "video"
    result = env.call(env.owner, "GET", f"/media/{video.id}/content")
    assert result.content == raw and result.headers["content-type"] == "video/mp4"
    assert result.headers["x-content-type-options"] == "nosniff"
    result = env.call(env.owner, "GET", f"/media/{thumb.id}/content")
    assert result.status_code == 200 and result.content.startswith(b"\xff\xd8")
    assert len(audits(env, "media.uploaded")) == 1


def test_warnings_are_non_blocking_and_persisted(env):
    response = upload(env, fake_video(width=400, height=400, has_edit_list=True))
    assert response.status_code == 201, response.text
    expected = ["EDIT_LIST_PRESENT", "ASPECT_NOT_9_16", "RESOLUTION_BELOW_RECOMMENDED"]
    assert response.json()["video_warnings"] == expected
    assert audits(env, "media.uploaded")[0].metadata_["warnings"] == expected


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({"duration_ms": 2999}, "DURATION_TOO_SHORT"),
        ({"duration_ms": 900001}, "DURATION_TOO_LONG"),
        ({"duration_ms": 0}, "DURATION_UNKNOWN"),
        ({"container": "3gp"}, "UNSUPPORTED_CONTAINER"),
        ({"video_stream_count": 0}, "NO_VIDEO_STREAM"),
        ({"video_stream_count": 2}, "MULTIPLE_VIDEO_STREAMS"),
        ({"video_codec": "vp9"}, "UNSUPPORTED_VIDEO_CODEC"),
        ({"audio_codecs": ["mp3"]}, "UNSUPPORTED_AUDIO_CODEC"),
        ({"audio_sample_rate": 48001}, "UNSUPPORTED_AUDIO_SAMPLE_RATE"),
        ({"audio_channels": 3}, "UNSUPPORTED_AUDIO_CHANNELS"),
        ({"pix_fmt": "yuv422p"}, "UNSUPPORTED_PIXEL_FORMAT"),
        ({"field_order": "tt"}, "INTERLACED"),
        ({"frame_rate": 22}, "FRAME_RATE_OUT_OF_RANGE"),
        ({"width": 1921}, "WIDTH_TOO_LARGE"),
        ({"width": 63}, "RESOLUTION_TOO_LOW"),
        ({"height": 100000}, "ASPECT_RATIO_OUT_OF_RANGE"),
        ({"video_bitrate_bps": 25000001}, "BITRATE_TOO_HIGH"),
        ({"moov_first": False}, "MOOV_NOT_AT_FRONT"),
    ],
)
def test_rejections_leave_only_audit(env, media_root, tmp_path, overrides, reason):
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    env.owner.client.app.state.settings.media_scratch_dir = str(scratch)
    response = upload(env, fake_video(**overrides))
    assert response.status_code == 422, response.text
    assert response.json()["params"]["reason"] == reason
    assert response.json()["params"]["reasons"][0]["code"] == reason
    assert not assets(env) and not list(media_root.rglob("*.*")) and not list(scratch.iterdir())
    assert len(audits(env, "media.rejected")) == 1


@pytest.mark.parametrize(
    ("raw", "reason"),
    [
        (b"", "EMPTY_FILE"),
        (b"\xff\xd8image", "NOT_A_VIDEO"),
        (b"FAKEVIDEO1 invalid\n", "CORRUPT_VIDEO"),
    ],
)
def test_empty_and_image(env, raw, reason):
    response = upload(env, raw)
    assert response.status_code == 422 and response.json()["params"]["reason"] == reason
    assert not assets(env)


def test_image_endpoint_stays_image_only(env):
    response = env.call(
        env.owner, "POST", "/media", files={"file": ("video.mp4", fake_video(), "video/mp4")}
    )
    assert response.status_code == 422 and response.json()["code"] == "MEDIA_INVALID"


def test_size_counter_and_scratch_cleanup(env, tmp_path, media_root):
    cfg = env.owner.client.app.state.settings.model_copy(
        update={"media_max_video_bytes": 10, "media_scratch_dir": str(tmp_path)}
    )

    class Counted(io.BytesIO):
        def read(self, n=-1):
            assert n <= 11
            return super().read(n)

    source = Counted(b"x" * 1000)
    with pytest.raises(Exception, match="VIDEO_TOO_LARGE"):
        video_ingest.ingest_video(
            env.session,
            env.clock,
            cfg,
            LocalMediaStorage(media_root, env.clock),
            env.ctx(env.owner),
            source,
            "video",
            FakeVideoProber(),
        )
    assert source.tell() == 11
    assert not list(tmp_path.glob("pivoris-video-*"))
    assert not assets(env) and len(audits(env, "media.rejected")) == 1


def test_declared_size_and_quota_guard_before_body(env):
    cfg = env.owner.client.app.state.settings
    cfg.media_max_video_bytes = 10
    response = env.owner.client.post(
        env.base + "/media/video",
        headers={**env.owner.headers, "content-length": "100000"},
        content=b"not multipart",
    )
    assert response.status_code == 413 and response.json()["code"] == "VIDEO_TOO_LARGE"
    cfg.media_max_video_bytes = 300000000
    cfg.media_video_workspace_quota_bytes = 1
    response = upload(env)
    assert response.status_code == 409 and response.json()["code"] == "VIDEO_STORAGE_QUOTA_EXCEEDED"


def test_chunked_body_without_content_length_is_refused_before_reading(env):
    def body():
        yield b"--x"

    response = env.owner.client.post(
        env.base + "/media/video",
        headers={**env.owner.headers, "content-type": "multipart/form-data; boundary=x"},
        content=body(),
    )
    assert response.status_code == 413 and response.json()["code"] == "VIDEO_TOO_LARGE"
    assert not assets(env)


def test_quota_rechecked_with_real_bytes(env, monkeypatch, media_root):
    real = video_ingest.check_quota
    calls = []

    def check(db, settings, ctx, size):
        calls.append(size)
        if len(calls) > 1:
            settings = settings.model_copy(update={"media_video_workspace_quota_bytes": 1})
        real(db, settings, ctx, size)

    monkeypatch.setattr(video_ingest, "check_quota", check)
    assert upload(env).status_code == 409
    assert len(calls) == 2 and not assets(env) and not list(media_root.rglob("*.*"))


@pytest.mark.parametrize("point", ["probe", "thumbnail", "first_put", "second_put", "flush"])
def test_failure_and_no_transaction_during_io(env, media_root, monkeypatch, point):
    class Prober(FakeVideoProber):
        def probe(self, path):
            assert not env.session.in_transaction()
            if point == "probe":
                raise VideoProbeUnavailable("busy")
            return super().probe(path)

        def extract_frame(self, path, at_ms, max_width):
            assert not env.session.in_transaction()
            if point == "thumbnail":
                raise VideoProbeUnavailable("timeout")
            return super().extract_frame(path, at_ms, max_width)

    class Storage(LocalMediaStorage):
        puts = 0

        def put(self, key, data, content_type):
            assert not env.session.in_transaction()
            super().put(key, data, content_type)
            self.puts += 1
            if point == ("first_put" if self.puts == 1 else "second_put"):
                raise RuntimeError("injected failure")

        def delete(self, key):
            assert not env.session.in_transaction()
            super().delete(key)

    monkeypatch.setattr("app.content.router.get_video_prober", lambda settings: Prober())
    env.owner.client.app.dependency_overrides[get_storage] = lambda: Storage(media_root, env.clock)
    if point == "flush":
        original = env.session.flush

        def flush(*args, **kwargs):
            if any(isinstance(row, MediaAsset) for row in env.session.new):
                raise RuntimeError("injected failure")
            return original(*args, **kwargs)

        monkeypatch.setattr(env.session, "flush", flush)
    if point in ("probe", "thumbnail"):
        result = upload(env)
        assert result.status_code == 503 and result.json()["code"] == "VIDEO_PROBE_UNAVAILABLE"
    else:
        with pytest.raises(RuntimeError, match="injected failure"):
            upload(env)
    assert not assets(env) and not list(media_root.rglob("*.*"))
    assert not audits(env, "media.rejected")


@pytest.mark.parametrize("kind", ["video", "video_thumbnail"])
@pytest.mark.parametrize("content_type", ["feed_image", "story_image", "feed_carousel"])
def test_image_slots_refuse_non_images(env, kind, content_type):
    response = upload(env).json()
    selected = response["id"] if kind == "video" else response["thumbnail_media_asset_id"]
    body = {"content_type": content_type, "title": "Draft", "media_asset_id": selected}
    if content_type == "feed_carousel":
        body.pop("media_asset_id")
        body["media_asset_ids"] = [selected]
    result = env.call(env.owner, "POST", "/content-items", json=body)
    assert result.status_code == 422 and result.json()["code"] == "MEDIA_KIND_INVALID"
    draft = env.call(
        env.owner, "POST", "/content-items", json={"content_type": content_type, "title": "Draft"}
    ).json()
    patch = {
        "expected_version": 1,
        "media_asset_ids" if content_type == "feed_carousel" else "media_asset_id": [selected]
        if content_type == "feed_carousel"
        else selected,
    }
    result = env.call(env.owner, "PATCH", f"/content-items/{draft['id']}", json=patch)
    assert result.status_code == 422 and result.json()["code"] == "MEDIA_KIND_INVALID"


def test_retention_parent_before_thumbnail_and_crash_recovery(
    env, media_root, shared_session_factory, settings
):
    body = upload(env).json()
    cfg = settings.model_copy(update={"media_local_root": str(media_root)})
    storage = LocalMediaStorage(media_root, env.clock)
    assert (
        run_media_cleanup(shared_session_factory, storage, cfg, env.clock.now() + timedelta(days=6))
        == 0
    )
    assert (
        run_media_cleanup(shared_session_factory, storage, cfg, env.clock.now() + timedelta(days=8))
        == 2
    )
    env.session.expire_all()
    assert all(a.status == "deleted" for a in assets(env))
    assert not list(media_root.rglob("*.*"))
    assert body["thumbnail_media_asset_id"]


def test_thumbnail_follows_live_parent_and_recovers_after_crash(
    env, media_root, shared_session_factory, settings
):
    upload(env)
    storage = LocalMediaStorage(media_root, env.clock)
    real_delete = storage.delete
    calls = []

    def crash(key):
        calls.append(key)
        if len(calls) == 2:
            raise RuntimeError("killed between parent and thumbnail")
        real_delete(key)

    storage.delete = crash
    # Six-day-old parent keeps its own arbitrarily old thumbnail alive.
    for row in assets(env):
        if row.kind == "video_thumbnail":
            row.created_at = env.clock.now() - timedelta(days=30)
    env.session.commit()
    assert run_media_cleanup(shared_session_factory, storage, settings, env.clock.now()) == 0
    with pytest.raises(RuntimeError, match="killed"):
        run_media_cleanup(
            shared_session_factory, storage, settings, env.clock.now() + timedelta(days=8)
        )
    storage.delete = real_delete
    assert (
        run_media_cleanup(
            shared_session_factory, storage, settings, env.clock.now() + timedelta(days=8)
        )
        == 1
    )
    env.session.expire_all()
    assert all(row.status == "deleted" for row in assets(env))


def test_referenced_video_is_kept_without_inventing_reel_type(
    env, media_root, shared_session_factory, settings
):
    from app.content.models import ContentItem

    body = upload(env).json()
    # Deliberate DB-only FK reference; API image slots reject videos.
    env.session.add(
        ContentItem(
            workspace_id=env.workspace.id,
            content_type="feed_image",
            title="Retention fixture",
            status="draft",
            media_asset_id=body["id"],
            created_by_user_id=env.owner.user.id,
        )
    )
    env.session.commit()
    assert (
        run_media_cleanup(
            shared_session_factory,
            LocalMediaStorage(media_root, env.clock),
            settings,
            env.clock.now() + timedelta(days=100),
        )
        == 0
    )


def test_s3_fake_storage_upload_and_chunked_preview(env):
    from app.integrations.storage.s3 import S3MediaStorage

    objects = {}
    reads = []

    class Body(io.BytesIO):
        def read(self, size=-1):
            reads.append(size)
            return super().read(size)

    class Client:
        def put_object(self, *, Bucket, Key, Body, ContentType):
            objects[Key] = Body.read()

        def get_object(self, *, Bucket, Key):
            return {"Body": Body(objects[Key])}

        def delete_object(self, *, Bucket, Key):
            objects.pop(Key, None)

    env.owner.client.app.dependency_overrides[get_storage] = lambda: S3MediaStorage(
        bucket="private", client=Client()
    )
    body = upload(env).json()
    assert len(objects) == 2
    response = env.call(env.owner, "GET", f"/media/{body['id']}/content")
    assert response.content == fake_video() and reads and all(n == 65536 for n in reads)


def test_preview_storage_io_has_no_transaction_even_with_expiring_sessions(env, media_root):
    body = upload(env).json()

    class Storage(LocalMediaStorage):
        def open(self, key):
            assert not env.session.in_transaction()
            return super().open(key)

    env.owner.client.app.dependency_overrides[get_storage] = lambda: Storage(media_root, env.clock)
    env.session.expire_on_commit = True
    result = env.call(env.owner, "GET", f"/media/{body['id']}/content")
    assert result.status_code == 200 and result.content == fake_video()


def test_permissions_and_csrf(env):
    response = env.owner.client.post(env.base + "/media/video", files={"file": ("x", fake_video())})
    assert response.status_code == 403 and response.json()["code"] == "CSRF_FAILED"
    env.owner.client.cookies.clear()
    response = env.owner.client.post(env.base + "/media/video", files={"file": ("x", fake_video())})
    assert response.status_code == 401


def test_brand_logo_refuses_video_and_thumbnail(env):
    body = upload(env).json()
    for selected in (body["id"], body["thumbnail_media_asset_id"]):
        result = env.call(
            env.owner,
            "PUT",
            "/brand",
            json={
                "logo_media_asset_id": selected,
                "primary_color": "#112233",
                "accent_color": "#445566",
            },
        )
        assert result.status_code == 422 and result.json()["code"] == "MEDIA_KIND_INVALID"


def test_workspace_media_delete_can_remove_parent_and_thumbnail_together(env):
    from sqlalchemy import delete

    upload(env)
    env.session.execute(delete(MediaAsset).where(MediaAsset.workspace_id == env.workspace.id))
    env.session.flush()
    assert not assets(env)  # NO ACTION self-FK is checked at the end of the statement.


def test_upload_permission_denied_before_body(env, monkeypatch):
    # All current product roles have content.edit; exercise a role without it at the guard.
    from app.api import deps

    original = deps.has_permission
    monkeypatch.setattr(
        deps,
        "has_permission",
        lambda role, permission: (
            False if permission == "content.edit" else original(role, permission)
        ),
    )
    response = env.call(env.staff, "POST", "/media/video", content=b"not multipart")
    assert response.status_code == 403 and response.json()["code"] == "FORBIDDEN"


def test_broken_thumbnail_is_audited_as_corrupt_video(env, monkeypatch):
    class Prober(FakeVideoProber):
        def extract_frame(self, path, at_ms, max_width):
            return b"not an image"

    monkeypatch.setattr("app.content.router.get_video_prober", lambda settings: Prober())
    response = upload(env)
    assert response.status_code == 422 and response.json()["params"]["reason"] == "CORRUPT_VIDEO"
    assert not assets(env) and len(audits(env, "media.rejected")) == 1
