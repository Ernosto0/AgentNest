"""ADR-015: storage keys, path-traversal safety and the local backend."""

import io
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast
from urllib.parse import parse_qs, urlparse

import boto3
import pytest
from botocore.config import Config
from botocore.exceptions import ClientError
from botocore.response import StreamingBody
from botocore.stub import Stubber

from app.core.clock import FrozenClock
from app.core.config import Settings
from app.integrations.storage.base import (
    InvalidStorageKey,
    StorageObjectNotFound,
    build_key,
    validate_key,
)
from app.integrations.storage.local import LocalMediaStorage, parse_local_url
from app.integrations.storage.registry import get_media_storage
from app.integrations.storage.s3 import S3Client, S3MediaStorage

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


def test_a_relative_media_root_is_under_backend() -> None:
    settings = Settings(_env_file=None, media_local_root="./var/media")  # type: ignore[call-arg]
    assert settings.media_root.parts[-3:] == ("backend", "var", "media")


@pytest.fixture
def s3_client() -> Iterator[Any]:
    # Explicit synthetic credentials prevent credential-chain or metadata-service lookups.
    client = boto3.client(
        "s3",
        endpoint_url="https://objects.example.test",
        region_name="auto",
        aws_access_key_id="synthetic-access-id",
        aws_secret_access_key="synthetic-secret-key",
        config=Config(signature_version="s3v4"),
    )
    yield client
    client.close()


@pytest.fixture
def s3_storage(s3_client: Any) -> S3MediaStorage:
    return S3MediaStorage(bucket="private-media", client=cast(S3Client, s3_client))


def test_s3_put_open_and_idempotent_delete(s3_client: Any, s3_storage: S3MediaStorage) -> None:
    upload = io.BytesIO(b"jpeg-bytes")
    source = io.BytesIO(b"jpeg-bytes")
    body = StreamingBody(source, len(b"jpeg-bytes"))
    with Stubber(s3_client) as stub:
        stub.add_response(
            "put_object",
            {},
            {
                "Bucket": "private-media",
                "Key": KEY,
                "Body": upload,
                "ContentType": "image/jpeg",
            },
        )
        stub.add_response("get_object", {"Body": body}, {"Bucket": "private-media", "Key": KEY})
        for _ in range(2):
            stub.add_response("delete_object", {}, {"Bucket": "private-media", "Key": KEY})
        s3_storage.put(KEY, upload, "image/jpeg")
        with s3_storage.open(KEY) as stream:
            assert stream.read() == b"jpeg-bytes"
            stream.seek(0)
            assert stream.read(4) == b"jpeg"
        assert source.closed  # the HTTP response stream is never left open
        s3_storage.delete(KEY)
        s3_storage.delete(KEY)
        stub.assert_no_pending_responses()


@pytest.mark.parametrize(("code", "status"), [("NoSuchKey", 400), ("404", 404), ("NotFound", 404)])
def test_s3_missing_objects_match_the_storage_protocol(
    s3_client: Any, s3_storage: S3MediaStorage, code: str, status: int
) -> None:
    with Stubber(s3_client) as stub:
        stub.add_client_error("get_object", code, http_status_code=status)
        with pytest.raises(StorageObjectNotFound):
            s3_storage.open(KEY)
        stub.assert_no_pending_responses()


def test_s3_authorization_failure_is_not_misreported_as_a_missing_object(
    s3_client: Any,
    s3_storage: S3MediaStorage,
) -> None:
    with Stubber(s3_client) as stub:
        stub.add_client_error("get_object", "AccessDenied", http_status_code=403)
        with pytest.raises(ClientError, match="AccessDenied"):
            s3_storage.open(KEY)


def test_s3_presigning_uses_get_object_key_and_requested_ttl_without_network(
    s3_storage: S3MediaStorage,
) -> None:
    url = urlparse(s3_storage.public_fetch_url(KEY, 1234))
    assert url.hostname == "objects.example.test"
    assert url.path == f"/private-media/{KEY}"
    query = parse_qs(url.query)
    assert query["X-Amz-Expires"] == ["1234"]
    assert query["X-Amz-Algorithm"] == ["AWS4-HMAC-SHA256"]
    assert query["X-Amz-Credential"][0].startswith("synthetic-access-id/")
    assert query["X-Amz-Signature"][0]


@pytest.mark.parametrize("ttl", [0, -1, 604801])
def test_s3_rejects_invalid_presigning_ttl(s3_storage: S3MediaStorage, ttl: int) -> None:
    with pytest.raises(ValueError, match="TTL"):
        s3_storage.public_fetch_url(KEY, ttl)


@pytest.mark.parametrize("key", ["", "../escape.jpg", f"{KEY}\n", f"/{KEY}"])
def test_every_s3_method_validates_keys_before_calling_the_sdk(
    s3_client: Any,
    s3_storage: S3MediaStorage,
    key: str,
) -> None:
    # No expected calls: Stubber rejects any SDK call before validation.
    with Stubber(s3_client):
        with pytest.raises(InvalidStorageKey):
            s3_storage.put(key, io.BytesIO(b"jpeg"), "image/jpeg")
        with pytest.raises(InvalidStorageKey):
            s3_storage.open(key)
        with pytest.raises(InvalidStorageKey):
            s3_storage.delete(key)
        with pytest.raises(InvalidStorageKey):
            s3_storage.public_fetch_url(key, 60)


@pytest.mark.parametrize("endpoint", ["", "https://s3.example.test"])
def test_s3_registry_configures_sigv4_and_explicit_credentials(
    s3_client: Any,
    monkeypatch: pytest.MonkeyPatch,
    endpoint: str,
) -> None:
    calls: list[dict[str, Any]] = []

    def factory(service: str, **kwargs: Any) -> Any:
        assert service == "s3"
        calls.append(kwargs)
        return s3_client

    monkeypatch.setattr("app.integrations.storage.s3.boto3.client", factory)
    settings = Settings(
        _env_file=None,
        media_storage_backend="s3",
        s3_bucket="private-media",
        s3_region="eu-west-1",
        s3_endpoint_url=endpoint,
        s3_access_key_id="synthetic-access-id",
        s3_secret_access_key="synthetic-secret-key",
    )
    storage = get_media_storage(settings, FrozenClock())
    assert storage.backend == "s3"
    assert calls[0]["endpoint_url"] == (endpoint or None)
    assert calls[0]["region_name"] == "eu-west-1"
    assert calls[0]["aws_access_key_id"] == "synthetic-access-id"
    assert calls[0]["aws_secret_access_key"] == "synthetic-secret-key"
    assert calls[0]["config"].signature_version == "s3v4"
    assert calls[0]["config"].retries == {"max_attempts": 0}
