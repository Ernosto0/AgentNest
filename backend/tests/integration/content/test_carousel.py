"""Ordered media, immutable approvals, rendered evidence and interim executor safety."""

import uuid
from datetime import timedelta

import pytest
from sqlalchemy import select

from app.approvals import service as approvals
from app.approvals.models import Approval
from app.content import service
from app.content.media_cleanup import eligible, run_media_cleanup
from app.content.models import ContentItem, ContentItemMedia, MediaAsset
from app.content.subject import bound_payload_hash, on_decided
from app.content.validation import CAROUSEL_MAX_ITEMS, CAROUSEL_MIN_ITEMS
from app.core.errors import AppError
from app.jobs.models import Job
from app.notifications.models import Notification
from tests.factories import create_fact, money
from tests.helpers.content import connect_account, make_media
from tests.integration.content.test_schedule import EVENING
from tests.integration.content.test_template_image_flow import change


def create(env, ids=None, **fields):
    if ids is None:
        ids = [str(make_media(env).id) for _ in range(3)]
    response = env.call(
        env.owner,
        "POST",
        "/content-items",
        json={
            "content_type": "feed_carousel",
            "title": "Carousel",
            "caption": "Merhaba",
            "media_asset_ids": ids,
            **fields,
        },
    )
    return response


def patch(env, item, ids, version=None):
    return env.call(
        env.owner,
        "PATCH",
        f"/content-items/{item['id']}",
        json={"expected_version": version or item["version"], "media_asset_ids": ids},
    )


def submit(env, item, self_approve=True):
    return env.call(
        env.owner if self_approve else env.staff,
        "POST",
        f"/content-items/{item['id']}/submit",
        json={
            "expected_version": item["version"],
            "schedule": EVENING,
            "self_approve": self_approve,
        },
    )


def ids_of(item):
    return [m["media_asset_id"] for m in item["media_items"]]


def test_order_read_replace_and_noop(env):
    first = create(env).json()
    ids = ids_of(first)
    assert [m["position"] for m in first["media_items"]] == [0, 1, 2]
    assert first["media_asset_id"] is None and first["template_image"] is None
    same = patch(env, first, ids).json()
    assert same["version"] == 1
    reordered = patch(env, first, [ids[2], ids[0], ids[1]])
    assert reordered.status_code == 200, reordered.text
    assert ids_of(reordered.json()) == [ids[2], ids[0], ids[1]]
    assert reordered.json()["version"] == 2
    assert ids_of(env.call(env.owner, "GET", f"/content-items/{first['id']}").json()) == ids_of(
        reordered.json()
    )


@pytest.mark.parametrize("count", [0, 1, CAROUSEL_MIN_ITEMS, CAROUSEL_MAX_ITEMS])
def test_draft_limits_and_submit(env, count):
    connect_account(env)
    response = create(env, [str(make_media(env).id) for _ in range(count)])
    assert response.status_code == 201, response.text
    item = response.json()
    checked = env.call(env.owner, "POST", f"/content-items/{item['id']}/validate").json()
    result = submit(env, item)
    if count >= CAROUSEL_MIN_ITEMS:
        assert checked["errors"] == []
        assert result.status_code == 200, result.text
    else:
        code = "CONTENT_MEDIA_REQUIRED" if count == 0 else "CAROUSEL_TOO_FEW_ITEMS"
        assert checked["errors"][0]["code"] == code
        assert result.status_code == 422
        assert (
            env.call(env.owner, "GET", f"/content-items/{item['id']}").json()["status"] == "draft"
        )


def test_limits_duplicates_and_wrong_shapes_are_typed(env):
    many = [str(uuid.uuid4()) for _ in range(CAROUSEL_MAX_ITEMS + 1)]
    for response, code in [
        (create(env, many), "CAROUSEL_TOO_MANY_ITEMS"),
        (create(env, [many[0], many[0]]), "CAROUSEL_DUPLICATE_MEDIA"),
        (create(env, [], media_asset_id=many[0]), "CONTENT_MEDIA_SHAPE_INVALID"),
        (create(env, [], content_type="feed_image"), "CONTENT_MEDIA_SHAPE_INVALID"),
    ]:
        assert response.status_code == 422, response.text
        assert response.json()["code"] == code
    item = create(env).json()
    assert patch(env, item, many).json()["code"] == "CAROUSEL_TOO_MANY_ITEMS"
    assert patch(env, item, [ids_of(item)[0]] * 2).json()["code"] == "CAROUSEL_DUPLICATE_MEDIA"
    assert patch(env, item, None).status_code == 422


def test_mixed_ratios_block_submit(env):
    connect_account(env)
    item = create(
        env, [str(make_media(env).id), str(make_media(env, width=1080, height=566).id)]
    ).json()
    response = submit(env, item)
    assert response.status_code == 422
    assert "CAROUSEL_MIXED_ASPECT_RATIO" in str(response.json())
    assert env.call(env.owner, "GET", f"/content-items/{item['id']}").json()["status"] == "draft"


@pytest.mark.parametrize("self_approve", [True, False])
@pytest.mark.parametrize("mutation", ["reorder", "remove", "add"])
def test_media_edits_invalidate_approval(env, self_approve, mutation):
    connect_account(env)
    item = create(env).json()
    response = submit(env, item, self_approve)
    assert response.status_code == 200, response.text
    submitted = response.json()
    approval_id = uuid.UUID(submitted["approval_id"])
    ids = ids_of(item)
    replacement = (
        list(reversed(ids))
        if mutation == "reorder"
        else ids[:-1]
        if mutation == "remove"
        else [*ids, str(make_media(env).id)]
    )
    result = patch(env, item, replacement)
    assert result.status_code == 200, result.text
    assert result.json()["version"] == 2 and result.json()["status"] == "draft"
    env.session.expire_all()
    approval = env.session.get(Approval, approval_id)
    assert approval.subject_version == 1
    if self_approve:
        with pytest.raises(AppError, match="APPROVAL_STALE"):
            approvals.assert_executable(env.session, env.clock, env.ctx(env.owner), approval_id, 2)
        jobs = env.session.scalars(select(Job).where(Job.job_type == "publish_content")).all()
        assert jobs and all(j.status == "cancelled" for j in jobs)
    else:
        assert approval.status == "cancelled" and approval.cancel_reason == "SUBJECT_EDITED"


def test_direct_db_reorder_is_stale_and_new_submission_has_new_hash(env):
    connect_account(env)
    item = create(env).json()
    pending = submit(env, item, False).json()
    approval = env.session.get(Approval, uuid.UUID(pending["approval_id"]))
    old_hash = approval.payload_hash
    rows = env.session.scalars(
        select(ContentItemMedia)
        .where(ContentItemMedia.content_item_id == uuid.UUID(item["id"]))
        .order_by(ContentItemMedia.position)
    ).all()
    rows[0].position, rows[1].position = rows[1].position, rows[0].position
    env.session.flush()
    stored = env.session.get(ContentItem, uuid.UUID(item["id"]))
    assert bound_payload_hash(env.session, stored) != old_hash
    with env.session.begin_nested():
        approval.status = "approved"
        with pytest.raises(AppError, match="APPROVAL_STALE"):
            on_decided(env.session, env.clock, env.ctx(env.owner), approval)
        approval.status = "pending"
    edited = patch(env, item, list(reversed(ids_of(item)))).json()
    new = submit(env, edited, False)
    assert new.status_code == 200, new.text
    assert env.session.get(Approval, uuid.UUID(new.json()["approval_id"])).payload_hash != old_hash


@pytest.mark.parametrize("self_approve", [True, False])
def test_rendered_price_item_joins_fact_hold(env, self_approve):
    connect_account(env)
    fact = create_fact(
        env.session, env.workspace, "pricing.membership_monthly", money(), clock=env.clock
    )
    rendered = env.call(
        env.owner,
        "POST",
        "/content/template-images",
        json={"template": "price_card", "format": "feed", "fact_key": fact.key},
    )
    assert rendered.status_code == 201, rendered.text
    image = rendered.json()
    ordinary = str(make_media(env, width=image["width"], height=image["height"]).id)
    item = create(env, [ordinary, image["id"]]).json()
    unaffected = create(env).json()
    assert submit(env, unaffected).status_code == 200
    scheduled = submit(env, item, self_approve)
    assert scheduled.status_code == 200, scheduled.text
    change(env, fact)
    fresh = env.call(env.owner, "GET", f"/content-items/{item['id']}").json()
    assert fresh["status"] == ("on_hold" if self_approve else "draft")
    assert fresh["hold_reason"] == "FACT_CHANGED"
    assert fresh["template_image"] is None
    assert (
        env.call(env.owner, "GET", f"/content-items/{unaffected['id']}").json()["status"]
        == "scheduled"
    )
    if self_approve:
        assert env.session.scalar(
            select(Notification.id).where(Notification.type == "content.on_hold")
        )
        jobs = env.session.scalars(
            select(Job).where(Job.payload["content_id"].astext == item["id"])
        ).all()
        assert jobs and all(j.status == "cancelled" for j in jobs)
    checked = env.call(env.owner, "POST", f"/content-items/{item['id']}/validate").json()
    assert "TEMPLATE_IMAGE_STALE" in str(checked)


def test_cleanup_respects_carousel_and_published_retention(env, settings):
    referenced, orphan = make_media(env), make_media(env)
    referenced.created_at = orphan.created_at = env.clock.now() - timedelta(days=100)
    item = create(env, [str(referenced.id)]).json()
    env.session.flush()

    def candidates():
        return set(
            env.session.scalars(select(MediaAsset.id).where(eligible(settings, env.clock.now())))
        )

    assert orphan.id in candidates() and referenced.id not in candidates()
    stored = env.session.get(ContentItem, uuid.UUID(item["id"]))
    stored.status, stored.published_at = "published", env.clock.now()
    env.session.flush()
    assert referenced.id not in candidates()
    stored.published_at = env.clock.now() - timedelta(
        days=settings.retention_published_media_days + 1
    )
    env.session.flush()
    assert referenced.id in candidates()
    referenced.status = "deleted"
    env.session.flush()
    fresh = env.call(env.owner, "GET", f"/content-items/{item['id']}").json()
    assert fresh["media_deleted"] and fresh["media_items"][0]["media_deleted"]


def test_published_carousel_is_immutable(env):
    item = create(env).json()
    stored = env.session.get(ContentItem, uuid.UUID(item["id"]))
    stored.status = "published"
    env.session.flush()
    assert patch(env, item, list(reversed(ids_of(item)))).status_code == 409
    assert env.call(env.owner, "POST", f"/content-items/{item['id']}/cancel").status_code == 409


def test_generation_refuses_carousel(env):
    response = env.call(
        env.owner,
        "POST",
        "/content-items/generate",
        json={
            "content_type": "feed_carousel",
            "objective": "Carousel",
            "client_request_id": "no-carousel",
        },
    )
    assert response.status_code == 422


def test_direct_db_reorder_is_refused_by_executor(pub):
    images = [pub.media(), pub.media()]
    item, _ = service.create_draft(
        pub.session,
        pub.clock,
        pub.ctx,
        content_type="feed_carousel",
        title="Carousel",
        caption="Merhaba",
        media_asset_ids=[a.id for a in images],
    )
    pub.schedule(item)
    rows = pub.session.scalars(
        select(ContentItemMedia)
        .where(
            ContentItemMedia.workspace_id == item.workspace_id,
            ContentItemMedia.content_item_id == item.id,
        )
        .order_by(ContentItemMedia.position)
    ).all()
    rows[0].position, rows[1].position = rows[1].position, rows[0].position
    pub.session.commit()
    outcome = pub.execute(item)
    assert outcome.error_code == "APPROVAL_STALE"
    assert pub.reload(item).last_error_code == "APPROVAL_STALE"
    assert pub.calls == [] and pub.operation(item) is None


def test_old_approval_cannot_execute_after_reorder(pub):
    images = [pub.media(), pub.media()]
    item, _ = service.create_draft(
        pub.session,
        pub.clock,
        pub.ctx,
        content_type="feed_carousel",
        title="Carousel",
        caption="Merhaba",
        media_asset_ids=[a.id for a in images],
    )
    pub.schedule(item)
    service.update(
        pub.session,
        pub.clock,
        pub.ctx,
        item.id,
        expected_version=1,
        fields={"media_asset_ids": [a.id for a in reversed(images)]},
    )
    pub.execute(item, version=1)
    assert pub.reload(item).status == "draft" and item.version == 2
    assert pub.calls == [] and pub.operation(item, version=1) is None


def test_cleanup_removes_true_orphan_but_keeps_carousel_file(pub):
    referenced, orphan = pub.media(), pub.media()
    referenced.created_at = orphan.created_at = pub.clock.now() - timedelta(
        days=pub.settings.retention_media_orphan_days + 1
    )
    pub.session.commit()
    service.create_draft(
        pub.session,
        pub.clock,
        pub.ctx,
        content_type="feed_carousel",
        title="Carousel",
        media_asset_ids=[referenced.id],
    )
    assert run_media_cleanup(pub.factory, pub.storage, pub.settings, pub.clock.now()) == 1
    pub.session.expire_all()
    assert pub.session.get(MediaAsset, referenced.id).status == "ready"
    assert pub.session.get(MediaAsset, orphan.id).status == "deleted"
    with pub.storage.open(referenced.storage_key) as image:
        assert image.read()
    from app.integrations.storage.base import StorageObjectNotFound

    with pytest.raises(StorageObjectNotFound):
        pub.storage.open(orphan.storage_key)


def test_carousel_reapprove_binds_fresh_order_and_version(env):
    connect_account(env)
    item = create(env).json()
    scheduled = submit(env, item).json()
    stored = env.session.get(ContentItem, uuid.UUID(item["id"]))
    from app.content import transitions

    transitions.apply(
        env.session, env.clock, env.ctx(env.owner), stored, "hold", reason="ACCOUNT_UNAVAILABLE"
    )
    env.session.flush()
    response = env.call(
        env.owner,
        "POST",
        f"/content-items/{item['id']}/reapprove",
        json={"expected_version": 1, "schedule": EVENING},
    )
    assert response.status_code == 200, response.text
    fresh = response.json()
    assert fresh["version"] == 2 and fresh["status"] == "scheduled"
    assert ids_of(fresh) == ids_of(item)
    assert fresh["approval_id"] != scheduled["approval_id"]
    env.session.expire_all()
    stored = env.session.get(ContentItem, uuid.UUID(item["id"]))
    approval = env.session.get(Approval, uuid.UUID(fresh["approval_id"]))
    assert bound_payload_hash(env.session, stored) == approval.payload_hash
