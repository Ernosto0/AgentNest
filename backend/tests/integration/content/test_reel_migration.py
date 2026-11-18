"""Migration 0083 round trip, constraints, composite FK, and capability backfill."""

import uuid

import pytest
from alembic import command
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from tests.integration.agent.test_migration import prior_schema

__all__ = ["prior_schema"]


def test_reel_migration_round_trip_checks_fk_and_downgrade_guard(prior_schema):
    config, engine = prior_schema
    command.upgrade(config, "0082")
    ws_a, ws_b, user, acc_true, acc_false, img_b, item = [uuid.uuid4() for _ in range(7)]
    with engine.begin() as db:
        for ws, slug in ((ws_a, ws_a.hex), (ws_b, ws_b.hex)):
            db.execute(
                text(
                    "INSERT INTO workspaces (id,name,slug,business_category,market,"
                    "default_locale,timezone,currency) VALUES (:w,'Shop',:slug,"
                    "'services','global','en','UTC','USD')"
                ),
                {"w": ws, "slug": slug},
            )
        db.execute(
            text(
                "INSERT INTO users (id,email,password_hash,display_name) VALUES "
                "(:u,:email,'unused','Owner')"
            ),
            {"u": user, "email": user.hex + "@example.com"},
        )
        db.execute(
            text(
                "INSERT INTO social_accounts (id,workspace_id,provider_kind,"
                "external_account_id,capabilities) VALUES "
                "(:a1,:w1,'mock','reel1',CAST('{\"publish_feed_image\": true}' AS jsonb)), "
                "(:a2,:w2,'mock','reel2',CAST('{\"publish_feed_image\": false}' AS jsonb))"
            ),
            {"a1": acc_true, "w1": ws_a, "a2": acc_false, "w2": ws_b},
        )
        db.execute(
            text(
                "INSERT INTO media_assets (id,workspace_id,kind,status,storage_backend,"
                "storage_key,sha256,mime_type,byte_size,width,height) VALUES "
                "(:m,:w,'image','ready','local','k',:sha,'image/jpeg',100,1080,1920)"
            ),
            {"m": img_b, "w": ws_b, "sha": "a" * 64},
        )

    command.upgrade(config, "0083")
    with engine.begin() as db:
        assert (
            db.scalar(
                text("SELECT capabilities->>'publish_reel' FROM social_accounts WHERE id=:a"),
                {"a": acc_true},
            )
            == "true"
        )
        assert (
            db.scalar(
                text("SELECT capabilities->>'publish_reel' FROM social_accounts WHERE id=:a"),
                {"a": acc_false},
            )
            == "false"
        )
        # Valid reel row
        db.execute(
            text(
                "INSERT INTO content_items (id,workspace_id,content_type,status,"
                "title,share_to_feed,created_by_user_id) VALUES "
                "(:i,:w,'reel','draft','My Reel',true,:u)"
            ),
            {"i": item, "w": ws_a, "u": user},
        )

    # CHECKs reject invalid shapes
    with pytest.raises(IntegrityError), engine.begin() as db:
        db.execute(
            text(
                "INSERT INTO content_items (id,workspace_id,content_type,status,"
                "title,share_to_feed,created_by_user_id) VALUES "
                "(:i,:w,'feed_image','draft','Bad',true,:u)"
            ),
            {"i": uuid.uuid4(), "w": ws_a, "u": user},
        )
    with pytest.raises(IntegrityError), engine.begin() as db:
        db.execute(
            text(
                "INSERT INTO content_items (id,workspace_id,content_type,status,"
                "title,created_by_user_id) VALUES "
                "(:i,:w,'reel','draft','MissingShare',:u)"
            ),
            {"i": uuid.uuid4(), "w": ws_a, "u": user},
        )
    with pytest.raises(IntegrityError), engine.begin() as db:
        db.execute(
            text(
                "INSERT INTO content_items (id,workspace_id,content_type,status,"
                "title,thumb_offset_ms,share_to_feed,created_by_user_id) VALUES "
                "(:i,:w,'reel','draft','NegOffset',-1,true,:u)"
            ),
            {"i": uuid.uuid4(), "w": ws_a, "u": user},
        )
    # Composite FK refuses cover image from another workspace
    with pytest.raises(IntegrityError), engine.begin() as db:
        db.execute(
            text(
                "INSERT INTO content_items (id,workspace_id,content_type,status,"
                "title,cover_media_asset_id,share_to_feed,created_by_user_id) VALUES "
                "(:i,:w,'reel','draft','ForeignCover',:c,true,:u)"
            ),
            {"i": uuid.uuid4(), "w": ws_a, "c": img_b, "u": user},
        )

    # Downgrade refuses while a reel exists
    with pytest.raises(RuntimeError, match="Reel archival"):
        command.downgrade(config, "0082")

    with engine.begin() as db:
        db.execute(text("DELETE FROM content_items WHERE id=:i"), {"i": item})
    command.downgrade(config, "0082")
    with engine.connect() as db:
        assert (
            db.scalar(
                text(
                    "SELECT count(*) FROM information_schema.columns "
                    "WHERE table_schema=current_schema() AND table_name='content_items' "
                    "AND column_name IN ('cover_media_asset_id','thumb_offset_ms','share_to_feed')"
                )
            )
            == 0
        )
        assert (
            db.scalar(
                text("SELECT capabilities ? 'publish_reel' FROM social_accounts WHERE id=:a"),
                {"a": acc_true},
            )
            is False
        )
    command.upgrade(config, "0083")
    with engine.connect() as db:
        assert db.scalar(text("SELECT version_num FROM alembic_version")) == "0083"
