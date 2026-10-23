"""ADR-015: storage keys, path-traversal safety and the local backend."""

import io
import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.core.clock import FrozenClock
from app.core.config import Settings
from app.integrations.storage.base import (
    InvalidStorageKey,
    MediaStorageUnavailable,
    StorageObjectNotFound,
    build_key,
    validate_key,
)
from app.integrations.storage.local import LocalMediaStorage, parse_local_url
from app.integrations.storage.registry import get_media_storage

WS = uuid.UUID("11111111-2222-3333-4444-555555555555")
MEDIA = uuid.UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
NOW = datetime(2026, 10, 5, 9, 30, tzinfo=UTC)
KEY = f"{WS}/2026/10/{MEDIA}.jpg"


@pytest.fixture
def storage(tmp_path: Path) -> LocalMediaStorage:
    return LocalMediaStorage(tmp_path / "media", FrozenClock(NOW))


def test_the_key_is_built_from_ids_and_the_upload_month() -> None:
    assert build_key(WS, MEDIA, NOW) == KEY
    assert validate_key(KEY) == KEY


def test_the_key_builder_takes_no_filename() -> None:
    with pytest.raises(InvalidStorageKey):
        build_key(WS, MEDIA, NOW, ext="../x")


@pytest.mark.parametrize(
    "key",
    [
        "",
        "../secret.jpg",
        f"../{WS}/2026/10/{MEDIA}.jpg",
        f"{WS}/2026/10/../../{MEDIA}.jpg",
        f"/{WS}/2026/10/{MEDIA}.jpg",
        f"{WS}/2026/13/{MEDIA}.jpg",
        f"{WS}/2026/10/{MEDIA}.jpg\n",
        f"{WS}/2026/10/{MEDIA}.exe",
        f"{WS}\\2026\\10\\{MEDIA}.jpg",
        f"{WS}/2026/10/my holiday photo.jpg",
        f"C:/{WS}/2026/10/{MEDIA}.jpg",
    ],
)
def test_keys_outside_the_pattern_are_refused(key: str, storage: LocalMediaStorage) -> None:
    with pytest.raises(InvalidStorageKey):
        validate_key(key)
    with pytest.raises(InvalidStorageKey):
        storage.open(key)
    with pytest.raises(InvalidStorageKey):
        storage.put(key, io.BytesIO(b"x"), "image/jpeg")
    with pytest.raises(InvalidStorageKey):
        storage.delete(key)
    with pytest.raises(InvalidStorageKey):
        storage.public_fetch_url(key, 60)


def test_put_open_and_delete_round_trip(storage: LocalMediaStorage, tmp_path: Path) -> None:
    storage.put(KEY, io.BytesIO(b"jpeg-bytes"), "image/jpeg")
    with storage.open(KEY) as stream:
        assert stream.read() == b"jpeg-bytes"
    assert (tmp_path / "media" / KEY).read_bytes() == b"jpeg-bytes"
    storage.delete(KEY)
    with pytest.raises(StorageObjectNotFound):
        storage.open(KEY)
    storage.delete(KEY)  # deleting a missing object is fine


def test_put_replaces_atomically_and_leaves_no_temporary_files(
    storage: LocalMediaStorage, tmp_path: Path
) -> None:
    storage.put(KEY, io.BytesIO(b"one"), "image/jpeg")
    storage.put(KEY, io.BytesIO(b"two"), "image/jpeg")
    with storage.open(KEY) as stream:
        assert stream.read() == b"two"
    folder = tmp_path / "media" / str(WS) / "2026" / "10"
    assert [p.name for p in folder.iterdir()] == [f"{MEDIA}.jpg"]


def test_a_failed_write_leaves_nothing_behind(storage: LocalMediaStorage, tmp_path: Path) -> None:
    class Broken(io.BytesIO):
        def read(self, size: int | None = -1) -> bytes:
            raise OSError("disk full")

    with pytest.raises(OSError, match="disk full"):
        storage.put(KEY, Broken(), "image/jpeg")
    folder = tmp_path / "media" / str(WS) / "2026" / "10"
    assert not list(folder.iterdir())


def test_the_local_fetch_url_is_an_opaque_reference_with_an_expiry(
    storage: LocalMediaStorage,
) -> None:
    url = storage.public_fetch_url(KEY, 3600)
    expires = int(NOW.timestamp()) + 3600
    assert url == f"localmedia:{KEY}?exp={expires}"
    assert parse_local_url(url) == (KEY, expires)
    with pytest.raises(ValueError, match="localmedia"):
        parse_local_url("https://example.com/x.jpg")


def test_the_registry_builds_the_configured_backend(tmp_path: Path) -> None:
    settings = Settings(_env_file=None, media_local_root=str(tmp_path))  # type: ignore[call-arg]
    assert get_media_storage(settings, FrozenClock()).backend == "local"
    s3 = Settings(
        _env_file=None,
        media_storage_backend="s3",
        s3_bucket="test-bucket",
        s3_access_key_id="synthetic-access-id",
        s3_secret_access_key="synthetic-secret-key",
    )  # type: ignore[call-arg]
    with pytest.raises(MediaStorageUnavailable, match="Phase 7"):
        get_media_storage(s3, FrozenClock())


def test_a_relative_media_root_is_under_backend() -> None:
    settings = Settings(_env_file=None, media_local_root="./var/media")  # type: ignore[call-arg]
    assert settings.media_root.parts[-3:] == ("backend", "var", "media")
