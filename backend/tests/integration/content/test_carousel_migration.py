"""Migration 0080 round trip and evidence-preserving downgrade."""

import uuid

import pytest
from alembic import command
from sqlalchemy import text

from tests.integration.agent.test_migration import prior_schema

__all__ = ["prior_schema"]


def test_carousel_migration_round_trip_and_downgrade_guard(prior_schema):
    config, engine = prior_schema
    command.upgrade(config, "0061")
    ws, user, account, item = [uuid.uuid4() for _ in range(4)]
    with engine.begin() as db:
        db.execute(
            text(
                "INSERT INTO workspaces (id,name,slug,business_category,market,"
                "default_locale,timezone,currency) VALUES (:w,'Shop',:slug,"
                "'services','global','en','UTC','USD')"
            ),
            {"w": ws, "slug": ws.hex},
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
                "external_account_id,capabilities) VALUES (:a,:w,'mock',"
                "'carousel',CAST('{\"publish_feed_image\": true}' AS jsonb))"
            ),
            {"a": account, "w": ws},
        )
    command.upgrade(config, "0080")
    with engine.begin() as db:
        assert (
            db.scalar(
                text(
                    "SELECT capabilities->>'publish_feed_carousel' FROM social_accounts WHERE id=:a"
                ),
                {"a": account},
            )
            == "true"
        )
        db.execute(
            text(
                "INSERT INTO content_items (id,workspace_id,content_type,status,"
                "title,created_by_user_id) VALUES (:i,:w,'feed_carousel','draft','Carousel',:u)"
            ),
            {"i": item, "w": ws, "u": user},
        )
    with pytest.raises(RuntimeError, match="Carousel archival"):
        command.downgrade(config, "0061")
    with engine.begin() as db:
        db.execute(text("DELETE FROM content_items WHERE id=:i"), {"i": item})
    command.downgrade(config, "0061")
    with engine.connect() as db:
        assert db.scalar(text("SELECT to_regclass('content_item_media')")) is None
    command.upgrade(config, "0080")
    with engine.connect() as db:
        assert db.scalar(text("SELECT version_num FROM alembic_version")) == "0080"
        assert db.scalar(text("SELECT to_regclass('content_item_media')")) is not None


def test_carousel_simulator_migration_round_trip(prior_schema):
    config, engine = prior_schema
    command.upgrade(config, "0080")
    command.upgrade(config, "0081")
    with engine.connect() as db:
        assert (
            db.scalar(
                text(
                    "SELECT count(*) FROM information_schema.columns "
                    "WHERE table_schema=current_schema() AND table_name='sim_containers' "
                    "AND column_name IN ('children','is_carousel_item')"
                )
            )
            == 2
        )
        assert (
            db.scalar(
                text(
                    "SELECT is_nullable FROM information_schema.columns "
                    "WHERE table_schema=current_schema() AND table_name='sim_containers' "
                    "AND column_name='media_url'"
                )
            )
            == "YES"
        )
        assert (
            db.scalar(
                text(
                    "SELECT column_default FROM information_schema.columns "
                    "WHERE table_schema=current_schema() AND table_name='sim_failure_rules' "
                    "AND column_name='skip_first'"
                )
            )
            == "0"
        )
    command.downgrade(config, "0080")
    with engine.connect() as db:
        assert (
            db.scalar(
                text(
                    "SELECT count(*) FROM information_schema.columns "
                    "WHERE table_schema=current_schema() AND table_name='sim_containers' "
                    "AND column_name IN ('children','is_carousel_item')"
                )
            )
            == 0
        )
        assert (
            db.scalar(
                text(
                    "SELECT is_nullable FROM information_schema.columns "
                    "WHERE table_schema=current_schema() AND table_name='sim_containers' "
                    "AND column_name='media_url'"
                )
            )
            == "NO"
        )
    command.upgrade(config, "0081")
    with engine.connect() as db:
        assert db.scalar(text("SELECT version_num FROM alembic_version")) == "0081"
