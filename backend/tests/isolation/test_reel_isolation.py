"""Reel isolation: foreign IDs, poll job scoping, composite FK, and forced RLS (INV-01)."""

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.content.models import ContentItem, MediaAsset
from app.core.clock import FrozenClock
from app.core.db import clear_tenant_context, set_tenant_context
from app.integrations.instagram.models import SimContainer, SimFailureRule
from app.operations import publish
from app.operations.models import Operation
from tests.isolation.test_delegation_suggestions_isolation import as_role


def _video(db, ws, user):
    row = MediaAsset(
        workspace_id=ws,
        kind="video",
        duration_ms=10_000,
        video_codec="h264",
        audio_codec="aac",
        frame_rate=30,
        bitrate_bps=4_000_000,
        container="mp4",
        video_warnings=[],
        storage_backend="local",
        storage_key=f"{ws}/2026/01/{uuid.uuid4()}.mp4",
        mime_type="video/mp4",
        byte_size=128,
        width=1080,
        height=1920,
        sha256="e" * 64,
        status="ready",
        created_by_user_id=user,
    )
    db.add(row)
    db.flush()
    return row


def _image(db, ws, user):
    row = MediaAsset(
        workspace_id=ws,
        kind="image",
        storage_backend="local",
        storage_key=f"{ws}/2026/01/{uuid.uuid4()}.jpg",
        mime_type="image/jpeg",
        byte_size=128,
        width=1080,
        height=1920,
        sha256="f" * 64,
        status="ready",
        created_by_user_id=user,
    )
    db.add(row)
    db.flush()
    return row


def test_foreign_video_cover_and_content_routes_are_404(two_workspaces, db_session):
    t, db = two_workspaces, db_session
    own_vid = _video(db, t.a.id, t.a_owner.id)
    foreign_vid = _video(db, t.b.id, t.b_owner.id)
    foreign_cover = _image(db, t.b.id, t.b_owner.id)
    foreign_item = ContentItem(
        workspace_id=t.b.id,
        content_type="reel",
        status="draft",
        version=1,
        title="B Reel",
        caption="Merhaba",
        overlay_text_suggestions=[],
        media_asset_id=foreign_vid.id,
        share_to_feed=True,
        validation={},
        created_by_user_id=t.b_owner.id,
    )
    db.add(foreign_item)
    db.commit()

    base = f"/api/v1/workspaces/{t.a.id}/content-items"
    assert (
        t.a_client.post(
            base,
            headers=t.a_headers,
            json={"content_type": "reel", "title": "X", "media_asset_id": str(foreign_vid.id)},
        ).status_code
        == 404
    )
    assert (
        t.a_client.post(
            base,
            headers=t.a_headers,
            json={
                "content_type": "reel",
                "title": "X",
                "media_asset_id": str(own_vid.id),
                "cover_media_asset_id": str(foreign_cover.id),
            },
        ).status_code
        == 404
    )
    assert (
        t.a_client.get(
            f"/api/v1/workspaces/{t.a.id}/content-items/{foreign_item.id}",
            headers=t.a_headers,
        ).status_code
        == 404
    )
    assert (
        t.a_client.get(
            f"/api/v1/workspaces/{t.a.id}/media/{foreign_vid.id}/content",
            headers=t.a_headers,
        ).status_code
        == 404
    )


def test_poll_reel_ignores_foreign_operation_with_no_provider_call(
    two_workspaces, db_session, settings, shared_session_factory
):
    t, db = two_workspaces, db_session
    account_id = uuid.UUID(t.foreign_ids["account_id"])
    op = Operation(
        workspace_id=t.b.id,
        operation_type="publish_content",
        idempotency_key=f"publish:{uuid.uuid4()}:v1",
        subject_type="content_item",
        subject_id=uuid.uuid4(),
        social_account_id=account_id,
        provider_kind="mock",
        status="in_progress",
        provider_ref={"container_id": "c-b", "phase": "processing"},
        attempts=1,
        max_attempts=5,
        created_at=FrozenClock().now(),
    )
    db.add(op)
    db.commit()

    calls = 0

    class BoomProvider:
        def get_container_status(self, *args):
            nonlocal calls
            calls += 1
            raise AssertionError("should not call provider")

    outcome = publish.poll_reel(
        shared_session_factory,
        FrozenClock(),
        settings,
        t.a.id,
        op.id,
        provider=BoomProvider(),  # type: ignore[arg-type]
    )
    assert outcome.kind == "skipped" and calls == 0


def test_composite_fk_and_rls_on_reel_and_simulator_columns(two_workspaces, db_session):
    t, db = two_workspaces, db_session
    foreign_cover = _image(db, t.b.id, t.b_owner.id)
    acc_b_id = uuid.UUID(t.foreign_ids["account_id"])
    db.add(
        SimFailureRule(
            workspace_id=t.b.id,
            social_account_id=acc_b_id,
            operation="create_reel_container",
            mode="slow_processing",
            delay_s=30,
        )
    )
    db.add(
        SimContainer(
            workspace_id=t.b.id,
            social_account_id=acc_b_id,
            container_id="sim-b-reel",
            media_type="REELS",
            share_to_feed=True,
            ready_at=FrozenClock().now(),
            expires_at=FrozenClock().now(),
        )
    )
    db.commit()

    # Composite FK refuses cross-workspace cover_media_asset_id
    with pytest.raises(IntegrityError), db.begin_nested():
        db.add(
            ContentItem(
                workspace_id=t.a.id,
                content_type="reel",
                status="draft",
                version=1,
                title="Bad FK",
                cover_media_asset_id=foreign_cover.id,
                share_to_feed=True,
                overlay_text_suggestions=[],
                validation={},
                created_by_user_id=t.a_owner.id,
            )
        )

    # Forced runtime role fails closed on sim_failure_rules/sim_containers without tenant or with A
    with as_role(db, "agentnest_app"):
        clear_tenant_context(db)
        assert db.execute(text("SELECT count(*) FROM sim_containers")).scalar() == 0
        set_tenant_context(db, t.a.id)
        assert db.execute(text("SELECT count(*) FROM sim_containers")).scalar() == 0
        assert db.execute(text("SELECT count(*) FROM sim_failure_rules")).scalar() == 0
