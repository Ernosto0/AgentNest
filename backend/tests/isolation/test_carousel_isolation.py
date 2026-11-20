"""Carousel routes, composite FKs and forced runtime RLS (INV-01)."""

import uuid

import pytest
from sqlalchemy import select, text, update
from sqlalchemy.exc import DBAPIError, IntegrityError

from app.content.models import ContentItem, ContentItemMedia, MediaAsset
from app.core.db import clear_tenant_context, set_tenant_context
from tests.isolation.test_delegation_suggestions_isolation import as_role


def test_publish_cannot_prepare_foreign_carousel_or_assets(
    two_workspaces, db_session, clock, settings, shared_session_factory
):
    from app.content.carousel import ordered_assets
    from app.operations.publish import execute_publish
    from tests.factories import knowledge_ctx

    t, db = two_workspaces, db_session
    foreign, _, _ = pair(db, t.b.id, t.b_owner.id, clock.now())
    db.commit()
    assert ordered_assets(db, knowledge_ctx(t.a, t.a_owner, "owner"), foreign) == ()
    outcome = execute_publish(
        shared_session_factory,
        clock,
        settings,
        t.a.id,
        foreign.id,
        foreign.version,
    )
    assert outcome.kind == "skipped" and outcome.detail == "item_missing"


def asset(db, ws):
    row = MediaAsset(
        workspace_id=ws,
        storage_backend="local",
        storage_key=str(uuid.uuid4()),
        mime_type="image/jpeg",
        byte_size=1,
        width=1080,
        height=1350,
        sha256="a" * 64,
        status="ready",
    )
    db.add(row)
    db.flush()
    return row


def child(db, workspace, item, media, now, position=0):
    row = ContentItemMedia(
        workspace_id=workspace,
        content_item_id=item,
        media_asset_id=media,
        position=position,
        created_at=now,
    )
    db.add(row)
    db.flush()
    return row


def pair(db, workspace, user, now):
    image = asset(db, workspace)
    item = ContentItem(
        workspace_id=workspace,
        content_type="feed_carousel",
        title="Carousel",
        status="draft",
        version=1,
        created_by_user_id=user,
        caption="Merhaba",
        overlay_text_suggestions=[],
        validation={},
    )
    db.add(item)
    db.flush()
    row = child(db, workspace, item.id, image.id, now)
    return item, image, row


def test_foreign_media_is_404_and_no_partial_create_or_patch(two_workspaces, db_session, clock):
    t, db = two_workspaces, db_session
    own = asset(db, t.a.id)
    foreign = t.foreign_ids["media_id"]
    db.flush()
    base = f"/api/v1/workspaces/{t.a.id}/content-items"
    valid = t.a_client.post(
        base,
        headers=t.a_headers,
        json={"content_type": "feed_carousel", "title": "Own", "media_asset_ids": [str(own.id)]},
    )
    assert valid.status_code == 201, valid.text
    item_id = valid.json()["id"]
    for ids in [[foreign], [str(own.id), foreign]]:
        response = t.a_client.post(
            base,
            headers=t.a_headers,
            json={"content_type": "feed_carousel", "title": "Foreign", "media_asset_ids": ids},
        )
        assert response.status_code == 404, response.text
        response = t.a_client.patch(
            base + "/" + item_id,
            headers=t.a_headers,
            json={"expected_version": 1, "media_asset_ids": ids},
        )
        assert response.status_code == 404, response.text
    own_item = t.a_client.get(base + "/" + item_id, headers=t.a_headers).json()
    assert own_item["version"] == 1
    assert [m["media_asset_id"] for m in own_item["media_items"]] == [str(own.id)]
    assert db.scalar(select(MediaAsset.id).where(MediaAsset.id == uuid.UUID(foreign)))
    assert len(db.scalars(select(ContentItemMedia)).all()) == 1


def test_foreign_carousel_routes_and_listing(two_workspaces, db_session, clock):
    t, db = two_workspaces, db_session
    item, image, row = pair(db, t.b.id, t.b_owner.id, clock.now())
    db.flush()
    for workspace in (t.a.id, t.b.id):
        base = f"/api/v1/workspaces/{workspace}/content-items/{item.id}"
        for method, suffix, body in [
            ("GET", "", None),
            ("PATCH", "", {"expected_version": 1, "media_asset_ids": []}),
            ("POST", "/validate", {}),
            ("POST", "/submit", {"expected_version": 1, "schedule": "now"}),
            ("POST", "/cancel", None),
            ("POST", "/reapprove", {"expected_version": 1, "schedule": "now"}),
        ]:
            response = t.a_client.request(method, base + suffix, headers=t.a_headers, json=body)
            assert response.status_code == 404, response.text
    listing = t.a_client.get(f"/api/v1/workspaces/{t.a.id}/content-items", headers=t.a_headers)
    assert str(image.id) not in listing.text and str(item.id) not in listing.text
    db.expire_all()
    assert db.get(ContentItemMedia, row.id).media_asset_id == image.id


def test_forced_rls_and_policy(db_session):
    assert tuple(
        db_session.execute(
            text(
                "SELECT relrowsecurity, relforcerowsecurity FROM pg_class WHERE "
                "oid = 'content_item_media'::regclass"
            )
        ).one()
    ) == (True, True)
    assert (
        db_session.scalar(
            text("SELECT polname FROM pg_policy WHERE polrelid = 'content_item_media'::regclass")
        )
        == "tenant_isolation_policy"
    )


def test_runtime_rls_is_fail_closed_and_prevents_cross_tenant_writes(
    two_workspaces, db_session, clock
):
    t, db = two_workspaces, db_session
    a, ma, ra = pair(db, t.a.id, t.a_owner.id, clock.now())
    b, mb, rb = pair(db, t.b.id, t.b_owner.id, clock.now())
    db.commit()
    aid, bid, wa, wb, bitem, bmedia = ra.id, rb.id, t.a.id, t.b.id, b.id, mb.id
    db.expunge_all()
    clear_tenant_context(db)
    with as_role(db, "pivoris_app"):
        assert db.scalars(select(ContentItemMedia)).all() == []
    set_tenant_context(db, wa)
    with as_role(db, "pivoris_app"):
        assert list(db.scalars(select(ContentItemMedia.id))) == [aid]
        assert (
            db.execute(
                update(ContentItemMedia).where(ContentItemMedia.id == bid).values(position=2)
            ).rowcount
            == 0
        )
        with pytest.raises(DBAPIError), db.begin_nested():
            db.execute(
                update(ContentItemMedia).where(ContentItemMedia.id == aid).values(workspace_id=wb)
            )
        with pytest.raises(DBAPIError), db.begin_nested():
            child(db, wb, bitem, bmedia, clock.now(), 1)


@pytest.mark.parametrize("foreign_parent", ["media", "content"])
def test_composite_fks_refuse_foreign_parent(two_workspaces, db_session, clock, foreign_parent):
    t, db = two_workspaces, db_session
    a, ma, _ = pair(db, t.a.id, t.a_owner.id, clock.now())
    b, mb, _ = pair(db, t.b.id, t.b_owner.id, clock.now())
    with pytest.raises(IntegrityError), db.begin_nested():
        child(
            db,
            t.a.id,
            b.id if foreign_parent == "content" else a.id,
            mb.id if foreign_parent == "media" else ma.id,
            clock.now(),
            1,
        )
