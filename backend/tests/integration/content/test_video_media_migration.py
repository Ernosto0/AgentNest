"""0082 defaults, null-safe checks, downgrade guard and round trip."""

import uuid

import pytest
from alembic import command
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from tests.integration.agent.test_migration import prior_schema

__all__ = ["prior_schema"]


def test_video_migration_roundtrip(prior_schema):
    config, engine = prior_schema
    command.upgrade(config, "0081")
    ws, image = uuid.uuid4(), uuid.uuid4()
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
                "INSERT INTO media_assets (id,workspace_id,storage_backend,storage_key,"
                "mime_type,byte_size,width,height,sha256,status) VALUES "
                "(:i,:w,'local',:key,'image/jpeg',1,100,100,:sha,'ready')"
            ),
            {"i": image, "w": ws, "key": image.hex, "sha": "a" * 64},
        )
    command.upgrade(config, "0082")
    with engine.connect() as db:
        assert db.scalar(text("SELECT kind FROM media_assets WHERE id=:i"), {"i": image}) == "image"
    for change in ("kind='video'", "duration_ms=3000", "thumbnail_media_asset_id=id"):
        with pytest.raises(IntegrityError), engine.begin() as db:
            db.execute(text(f"UPDATE media_assets SET {change} WHERE id=:i"), {"i": image})  # noqa: S608 - fixed check cases
    with engine.begin() as db:
        db.execute(text("UPDATE media_assets SET kind='video_thumbnail' WHERE id=:i"), {"i": image})
    with pytest.raises(RuntimeError, match="non-image"):
        command.downgrade(config, "0081")
    with engine.begin() as db:
        db.execute(text("UPDATE media_assets SET kind='image' WHERE id=:i"), {"i": image})
    command.downgrade(config, "0081")
    with engine.connect() as db:
        assert (
            db.scalar(
                text(
                    "SELECT count(*) FROM information_schema.columns "
                    "WHERE table_schema=current_schema() AND table_name='media_assets' "
                    "AND column_name='kind'"
                )
            )
            == 0
        )
    command.upgrade(config, "0082")
    with engine.connect() as db:
        assert db.scalar(text("SELECT kind FROM media_assets WHERE id=:i"), {"i": image}) == "image"
