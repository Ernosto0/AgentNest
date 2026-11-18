"""Reel API, validation, approval hashes, Range playback, retention, and refusals."""

import uuid
from datetime import timedelta

import pytest
from sqlalchemy import select

from app.approvals import service as approvals
from app.approvals.models import Approval
from app.content.media_cleanup import eligible, run_media_cleanup
from app.content.models import ContentItem
from app.content.subject import bound_payload_hash, on_decided
from app.core.errors import AppError
from app.notifications.models import Notification
from tests.factories import create_fact, money
from tests.helpers.content import connect_account, make_media, make_video
from tests.integration.content.test_schedule import EVENING
from tests.integration.content.test_template_image_flow import change


def _create_reel(env, video_id=None, **fields):
    vid = video_id or make_video(env).id
    return env.call(
        env.owner,
        "POST",
        "/content-items",
        json={
            "content_type": "reel",
            "title": "Reel Demo",
            "caption": "Merhaba reel",
            "media_asset_id": str(vid),
            **fields,
        },
    )


def test_create_patch_shape_errors_and_no_partial_update(env):
    vid = make_video(env).id
    cover = make_media(env).id
    img = make_media(env).id
    env.session.commit()

    # Default share_to_feed=True and video_duration_ms returned
    res = _create_reel(env, vid)
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["content_type"] == "reel"
    assert body["share_to_feed"] is True
    assert body["video_duration_ms"] == 10_000
    assert body["cover_media_asset_id"] is None
    assert body["thumb_offset_ms"] is None
    assert body["cover_media_deleted"] is False

    # Feed image given a video -> 422 MEDIA_KIND_INVALID
    bad_feed = env.call(
        env.owner,
        "POST",
        "/content-items",
        json={"content_type": "feed_image", "title": "Bad", "media_asset_id": str(vid)},
    )
    assert bad_feed.status_code == 422
    assert bad_feed.json()["code"] == "MEDIA_KIND_INVALID"

    # Reel given an image for media_asset_id -> 422 MEDIA_KIND_INVALID
    bad_reel = env.call(
        env.owner,
        "POST",
        "/content-items",
        json={"content_type": "reel", "title": "Bad", "media_asset_id": str(img)},
    )
    assert bad_reel.status_code == 422
    assert bad_reel.json()["code"] == "MEDIA_KIND_INVALID"

    # Reel given a video for cover_media_asset_id -> 422 MEDIA_KIND_INVALID
    bad_cover = _create_reel(env, vid, cover_media_asset_id=str(vid))
    assert bad_cover.status_code == 422
    assert bad_cover.json()["code"] == "MEDIA_KIND_INVALID"

    # Both cover + offset -> 422 CONTENT_MEDIA_SHAPE_INVALID
    both = _create_reel(env, vid, cover_media_asset_id=str(cover), thumb_offset_ms=500)
    assert both.status_code == 422
    assert both.json()["code"] == "CONTENT_MEDIA_SHAPE_INVALID"

    # Non-reel with reel fields -> 422 CONTENT_MEDIA_SHAPE_INVALID
    non_reel = env.call(
        env.owner,
        "POST",
        "/content-items",
        json={"content_type": "feed_image", "title": "Feed", "share_to_feed": True},
    )
    assert non_reel.status_code == 422
    assert non_reel.json()["code"] == "CONTENT_MEDIA_SHAPE_INVALID"

    # Foreign / unknown asset on PATCH -> 404, no partial update
    item_id = body["id"]
    foreign_patch = env.call(
        env.owner,
        "PATCH",
        f"/content-items/{item_id}",
        json={
            "expected_version": 1,
            "caption": "Should not save",
            "cover_media_asset_id": str(uuid.uuid4()),
        },
    )
    assert foreign_patch.status_code == 404
    current = env.call(env.owner, "GET", f"/content-items/{item_id}").json()
    assert current["version"] == 1
    assert current["caption"] == "Merhaba reel"
    assert current["cover_media_asset_id"] is None

    # Valid PATCH switching offset -> cover -> reset + share_to_feed
    p1 = env.call(
        env.owner,
        "PATCH",
        f"/content-items/{item_id}",
        json={"expected_version": 1, "thumb_offset_ms": 2500},
    )
    assert p1.status_code == 200
    assert p1.json()["version"] == 2
    assert p1.json()["thumb_offset_ms"] == 2500

    # Setting cover without clearing offset -> 422 CONTENT_MEDIA_SHAPE_INVALID
    p_conflict = env.call(
        env.owner,
        "PATCH",
        f"/content-items/{item_id}",
        json={"expected_version": 2, "cover_media_asset_id": str(cover)},
    )
    assert p_conflict.status_code == 422
    assert p_conflict.json()["code"] == "CONTENT_MEDIA_SHAPE_INVALID"

    p2 = env.call(
        env.owner,
        "PATCH",
        f"/content-items/{item_id}",
        json={
            "expected_version": 2,
            "thumb_offset_ms": None,
            "cover_media_asset_id": str(cover),
            "share_to_feed": False,
        },
    )
    assert p2.status_code == 200
    assert p2.json()["version"] == 3
    assert p2.json()["cover_media_asset_id"] == str(cover)
    assert p2.json()["share_to_feed"] is False


@pytest.mark.parametrize(
    "edit",
    [
        {"caption": "Edited reel caption"},
        {"share_to_feed": False},
        {"thumb_offset_ms": 1500},
    ],
)
def test_editing_reel_payload_after_submit_cancels_approval_and_bumps_version(env, edit):
    connect_account(env)
    vid = make_video(env).id
    env.session.commit()
    item = _create_reel(env, vid).json()
    sub = env.call(
        env.staff,
        "POST",
        f"/content-items/{item['id']}/submit",
        json={"expected_version": 1, "schedule": EVENING},
    )
    assert sub.status_code == 200, sub.text
    approval_id = uuid.UUID(sub.json()["approval_id"])

    patched = env.call(
        env.owner,
        "PATCH",
        f"/content-items/{item['id']}",
        json={"expected_version": 1, **edit},
    )
    assert patched.status_code == 200
    assert patched.json()["status"] == "draft"
    assert patched.json()["version"] == 2

    approval = env.session.get(Approval, approval_id)
    assert approval is not None and approval.status == "cancelled"
    assert approval.cancel_reason == "SUBJECT_EDITED"


def test_direct_db_mutation_breaks_reel_bound_payload_hash(env):
    connect_account(env)
    cover = make_media(env)
    vid = make_video(env)
    env.session.commit()
    created = _create_reel(env, vid.id, cover_media_asset_id=str(cover.id)).json()
    sub = env.call(
        env.staff,
        "POST",
        f"/content-items/{created['id']}/submit",
        json={"expected_version": 1, "schedule": EVENING},
    )
    assert sub.status_code == 200, sub.text
    env.session.commit()
    row = env.session.get(ContentItem, uuid.UUID(created["id"]))
    assert row is not None
    approval = env.session.get(Approval, row.approval_id)
    assert approval is not None
    assert bound_payload_hash(env.session, row) == approval.payload_hash

    row.share_to_feed = False
    env.session.flush()
    assert bound_payload_hash(env.session, row) != approval.payload_hash
    with pytest.raises(AppError, match="APPROVAL_STALE"):
        approvals.decide(
            env.session,
            env.clock,
            env.ctx(env.owner),
            approval.id,
            decision="approve",
            payload_hash=approval.payload_hash,
        )
    env.session.rollback()

    # Re-fetch and mutate cover directly
    row = env.session.get(ContentItem, uuid.UUID(created["id"]))
    assert row is not None
    approval = env.session.get(Approval, row.approval_id)
    assert approval is not None
    other_cover = make_media(env)
    row.cover_media_asset_id = other_cover.id
    env.session.flush()
    assert bound_payload_hash(env.session, row) != approval.payload_hash
    with pytest.raises(AppError, match="APPROVAL_STALE"):
        approvals.decide(
            env.session,
            env.clock,
            env.ctx(env.owner),
            approval.id,
            decision="approve",
            payload_hash=approval.payload_hash,
        )
    assert on_decided is not None


def test_cover_template_price_change_holds_reel(env):
    connect_account(env)
    fact = create_fact(
        env.session,
        env.workspace,
        "pricing.membership_monthly",
        money(1000),
        clock=env.clock,
    )
    vid = make_video(env)
    env.session.commit()
    rendered = env.call(
        env.owner,
        "POST",
        "/content/template-images",
        json={
            "template": "price_card",
            "format": "feed",
            "fact_key": fact.key,
        },
    )
    assert rendered.status_code == 201, rendered.text
    cover_id = rendered.json()["id"]
    item = _create_reel(env, vid.id, cover_media_asset_id=cover_id).json()
    sub = env.call(
        env.staff,
        "POST",
        f"/content-items/{item['id']}/submit",
        json={"expected_version": 1, "schedule": EVENING, "self_approve": False},
    )
    assert sub.status_code == 200, sub.text
    approval_row = env.session.get(Approval, uuid.UUID(sub.json()["approval_id"]))
    assert approval_row is not None
    approvals.decide(
        env.session,
        env.clock,
        env.ctx(env.owner),
        approval_row.id,
        decision="approve",
        payload_hash=approval_row.payload_hash,
    )
    env.session.commit()

    change(env, fact)
    row = env.session.get(ContentItem, uuid.UUID(item["id"]))
    assert row is not None and row.status == "on_hold" and row.hold_reason == "FACT_CHANGED"
    note = env.session.scalar(select(Notification).where(Notification.type == "content.on_hold"))
    assert note is not None


def test_reel_cover_and_video_retention(env, settings, media_root, shared_session_factory):
    from app.integrations.storage.registry import get_media_storage

    cfg = settings.model_copy(update={"media_local_root": str(media_root)})
    storage = get_media_storage(cfg, env.clock)
    vid = make_video(env)
    cover = make_media(env)
    orphan = make_media(env)
    vid.storage_key = f"{env.workspace.id}/2026/01/{uuid.uuid4()}.mp4"
    cover.storage_key = f"{env.workspace.id}/2026/01/{uuid.uuid4()}.jpg"
    orphan.storage_key = f"{env.workspace.id}/2026/01/{uuid.uuid4()}.jpg"
    vid.created_at = env.clock.now()
    cover.created_at = env.clock.now()
    orphan.created_at = env.clock.now()
    env.session.commit()
    item = _create_reel(env, vid.id, cover_media_asset_id=str(cover.id)).json()
    row = env.session.get(ContentItem, uuid.UUID(item["id"]))
    assert row is not None
    row.status = "published"
    row.published_at = env.clock.now()
    env.session.commit()

    cutoff_orphan = env.clock.now() + timedelta(days=cfg.retention_media_orphan_days + 1)
    due_ids = set(env.session.scalars(select(vid.__class__.id).where(eligible(cfg, cutoff_orphan))))
    assert orphan.id in due_ids
    assert vid.id not in due_ids
    assert cover.id not in due_ids

    row.published_at = env.clock.now() - timedelta(days=cfg.retention_published_media_days + 1)
    env.session.commit()
    run_media_cleanup(shared_session_factory, storage, cfg, env.clock.now())
    detail = env.call(env.owner, "GET", f"/content-items/{item['id']}").json()
    assert detail["media_deleted"] is True
    assert detail["cover_media_deleted"] is True


def test_range_playback_http_semantics(env, settings, media_root):
    payload = b"0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    upload = env.call(
        env.owner,
        "POST",
        "/media/video",
        files={"file": ("clip.mp4", b"FAKEVIDEO1 " + payload, "video/mp4")},
    )
    # Use storage directly with a ready asset row matching bytes so Range slices exact payload
    asset = make_video(env, sha256="d" * 64)
    asset.storage_key = f"{env.workspace.id}/2026/01/{uuid.uuid4()}.mp4"
    from app.integrations.storage.registry import get_media_storage

    cfg = settings.model_copy(update={"media_local_root": str(media_root)})
    storage = get_media_storage(cfg, env.clock)
    import io

    storage.put(asset.storage_key, io.BytesIO(payload), "video/mp4")
    asset.byte_size = len(payload)
    env.session.commit()
    assert upload.status_code in (201, 422)

    url = f"/media/{asset.id}/content"
    full = env.call(env.owner, "GET", url)
    assert full.status_code == 200
    assert full.headers["accept-ranges"] == "bytes"
    assert full.content == payload
    etag = full.headers["etag"]

    partial = env.owner.client.get(
        f"{env.base}{url}",
        headers={**env.owner.headers, "Range": "bytes=0-9"},
    )
    assert partial.status_code == 206
    assert partial.headers["accept-ranges"] == "bytes"
    assert partial.headers["content-range"] == f"bytes 0-9/{len(payload)}"
    assert partial.headers["content-length"] == "10"
    assert partial.content == b"0123456789"

    open_end = env.owner.client.get(
        f"{env.base}{url}",
        headers={**env.owner.headers, "Range": "bytes=26-", "If-Range": etag},
    )
    assert open_end.status_code == 206
    assert open_end.content == b"QRSTUVWXYZ"

    suffix = env.owner.client.get(
        f"{env.base}{url}",
        headers={**env.owner.headers, "Range": "bytes=-4"},
    )
    assert suffix.status_code == 206
    assert suffix.content == b"WXYZ"

    unsatisfiable = env.owner.client.get(
        f"{env.base}{url}",
        headers={**env.owner.headers, "Range": "bytes=999-1000"},
    )
    assert unsatisfiable.status_code == 416
    assert unsatisfiable.headers["content-range"] == f"bytes */{len(payload)}"

    multi = env.owner.client.get(
        f"{env.base}{url}",
        headers={**env.owner.headers, "Range": "bytes=0-1, 2-3"},
    )
    assert multi.status_code == 200 and multi.content == payload

    if_range_mismatch = env.owner.client.get(
        f"{env.base}{url}",
        headers={**env.owner.headers, "Range": "bytes=0-3", "If-Range": '"stale-etag"'},
    )
    assert if_range_mismatch.status_code == 200 and if_range_mismatch.content == payload


def test_reel_refused_in_generation_and_templates(env):
    gen = env.call(
        env.owner,
        "POST",
        "/content-items/generate",
        json={"content_type": "reel", "objective": "Promo", "client_request_id": "req-reel-1"},
    )
    assert gen.status_code == 422

    from app.agent.content import ToolInputError
    from app.content import generation

    with pytest.raises(AppError, match="CONTENT_MEDIA_SHAPE_INVALID"):
        generation.stage_request(
            env.session,
            env.clock,
            env.ctx(env.owner),
            content_type="reel",
            objective="Promo",
            notes=None,
            client_request_id="req-reel-2",
        )
    assert ToolInputError is not None
