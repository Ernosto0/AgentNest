"""P5-01: `POST /media` and `GET /media/{id}/content` (AC-D2, ADR-015, plan.md G12)."""

import hashlib
import io
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.audit.service import list_entries
from app.content.models import MediaAsset
from app.integrations.storage.base import KEY_RE
from tests.factories import login, workspace_with_members
from tests.helpers.env import Env, Role
from tests.helpers.images import jpeg_with_exif, png_bytes

UPLOAD = "/media"


def upload(
    env: Env,
    role: Role | None = None,
    data: bytes | None = None,
    filename: str = "kapak.png",
    content_type: str = "image/png",
    **kwargs: Any,
) -> Any:
    files = {"file": (filename, data if data is not None else png_bytes(), content_type)}
    return env.call(role or env.owner, "POST", UPLOAD, files=files, **kwargs)


def stored_files(root: Path) -> list[Path]:
    return [p for p in root.rglob("*") if p.is_file()] if root.exists() else []


def asset_count(session: Session) -> int:
    return session.scalar(select(func.count()).select_from(MediaAsset)) or 0


def test_a_png_becomes_a_ready_jpeg_without_exif(env: Env, media_root: Path) -> None:
    """AC-D2."""
    response = upload(env, data=png_bytes((120, 80)))
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "ready"
    assert body["mime_type"] == "image/jpeg"
    assert (body["width"], body["height"]) == (120, 80)
    assert body["rejection_code"] is None
    assert body["original_filename"] == "kapak.png"

    served = env.call(env.owner, "GET", f"/media/{body['id']}/content")
    assert served.status_code == 200
    image = Image.open(io.BytesIO(served.content))
    assert image.format == "JPEG" and image.mode == "RGB"
    assert len(image.getexif()) == 0
    assert body["byte_size"] == len(served.content)

    row = env.session.scalars(select(MediaAsset)).one()
    assert row.workspace_id == env.workspace.id
    assert row.created_by_user_id == env.owner.user.id
    assert row.sha256 == hashlib.sha256(served.content).hexdigest()
    assert row.storage_backend == "local" and row.status == "ready"
    assert [p.read_bytes() for p in stored_files(media_root)] == [served.content]


def test_exif_and_gps_in_a_jpeg_never_reach_the_stored_file(env: Env, media_root: Path) -> None:
    source = jpeg_with_exif((200, 100), orientation=6)
    response = upload(env, data=source, filename="IMG_0001.JPG", content_type="image/jpeg")
    assert response.status_code == 201, response.text
    body = response.json()
    assert (body["width"], body["height"]) == (100, 200)  # orientation applied
    (path,) = stored_files(media_root)
    stored = path.read_bytes()
    assert b"SecretCam" not in stored and b"Exif" not in stored
    assert len(Image.open(io.BytesIO(stored)).getexif()) == 0


def test_the_storage_key_never_comes_from_the_filename(env: Env, media_root: Path) -> None:
    evil = "../../../etc/passwd.png"
    response = upload(env, filename=evil)
    assert response.status_code == 201, response.text
    row = env.session.scalars(select(MediaAsset)).one()
    assert KEY_RE.fullmatch(row.storage_key)
    assert row.storage_key == f"{env.workspace.id}/2026/01/{row.id}.jpg"  # FrozenClock: Jan 2026
    assert "passwd" not in row.storage_key and ".." not in row.storage_key
    assert row.original_filename == "passwd.png"  # display only, sanitised
    (path,) = stored_files(media_root)
    assert path.resolve().is_relative_to(media_root.resolve())
    assert path.name == f"{row.id}.jpg"


def test_the_same_upload_twice_gives_two_assets_and_two_keys(env: Env) -> None:
    first = upload(env).json()
    second = upload(env).json()
    assert first["id"] != second["id"]
    keys = env.session.scalars(select(MediaAsset.storage_key)).all()
    assert len(set(keys)) == 2


def test_the_upload_is_audited_without_the_content(env: Env) -> None:
    media_id = upload(env).json()["id"]
    (entry,) = list_entries(env.session, workspace_id=env.workspace.id, action="media.uploaded")
    assert str(entry.resource_id) == media_id
    assert entry.resource_type == "media_asset"
    assert entry.is_simulated is False
    assert {"width", "height", "byte_size", "sha256"} <= set(entry.metadata_)


def test_a_text_file_is_rejected_whatever_its_name_and_type(env: Env, media_root: Path) -> None:
    """AC-D2: no row, no stored file, an audit entry."""
    response = upload(
        env, data=b"hello, I am not an image\n", filename="photo.jpg", content_type="image/jpeg"
    )
    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "MEDIA_INVALID"
    assert body["params"] == {"reason": "NOT_AN_IMAGE"}
    assert body["detail"]
    assert asset_count(env.session) == 0
    assert stored_files(media_root) == []
    (entry,) = list_entries(env.session, workspace_id=env.workspace.id, action="media.rejected")
    assert entry.metadata_["reason"] == "NOT_AN_IMAGE"
    assert entry.resource_id is None
    assert not list_entries(env.session, workspace_id=env.workspace.id, action="media.uploaded")


@pytest.mark.parametrize(
    ("kind", "reason"),
    [("empty", "EMPTY_FILE"), ("corrupt", "CORRUPT_IMAGE"), ("bomb", "TOO_MANY_PIXELS")],
)
def test_empty_corrupt_and_decompression_bomb_uploads_are_rejected(
    env: Env, media_root: Path, kind: str, reason: str
) -> None:
    data = {
        "empty": b"",
        "corrupt": png_bytes((300, 300))[:200],
        "bomb": png_bytes((7000, 7000), mode="L", color=0),
    }[kind]
    response = upload(env, data=data)
    assert response.status_code == 422, response.text
    assert response.json()["code"] == "MEDIA_INVALID"
    assert response.json()["params"]["reason"] == reason
    assert asset_count(env.session) == 0
    assert stored_files(media_root) == []
    (entry,) = list_entries(env.session, workspace_id=env.workspace.id, action="media.rejected")
    assert entry.metadata_["reason"] == reason


def test_an_oversize_upload_is_413_and_stores_nothing(
    build_app: Callable[..., FastAPI],
    make_client: Callable[[], TestClient],
    db_session: Session,
    clock: Any,
    media_root: Path,
) -> None:
    from tests.helpers.env import build_env

    small = build_app(media_local_root=str(media_root), media_max_image_bytes=1000)

    def small_client() -> TestClient:
        return TestClient(small)

    env = build_env(db_session, small_client, clock)
    data = png_bytes((200, 200), color="white")
    noisy = bytes(range(256)) * 8 + b"x"  # 2049 bytes
    assert len(noisy) > 1000

    response = upload(env, data=noisy)
    assert response.status_code == 413
    assert response.json()["code"] == "MEDIA_TOO_LARGE"
    assert response.json()["params"] == {"limit_bytes": 1000}
    assert asset_count(db_session) == 0 and stored_files(media_root) == []
    (entry,) = list_entries(db_session, workspace_id=env.workspace.id, action="media.rejected")
    assert entry.metadata_["reason"] == "TOO_LARGE"

    # Exactly at the limit is not "too large": it is judged as an image.
    at_limit = upload(env, data=b"\x00" * 1000)
    assert at_limit.status_code == 422
    assert at_limit.json()["code"] == "MEDIA_INVALID"
    # A small valid image still passes under the same limit.
    assert len(data) < 1000
    assert upload(env, data=data).status_code == 201


def test_a_missing_file_part_is_a_validation_error(env: Env) -> None:
    response = env.call(env.owner, "POST", UPLOAD, data={"other": "x"})
    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_FAILED"


def test_staff_may_upload_because_content_edit_is_for_everyone(env: Env) -> None:
    assert upload(env, role=env.staff).status_code == 201


def test_upload_needs_a_session_and_csrf(env: Env, make_client: Callable[[], TestClient]) -> None:
    files = {"file": ("a.png", png_bytes(), "image/png")}
    anonymous = make_client().post(f"{env.base}{UPLOAD}", files=files)
    assert anonymous.status_code == 401
    no_csrf = env.owner.client.post(f"{env.base}{UPLOAD}", files=files)
    assert no_csrf.status_code == 403 and no_csrf.json()["code"] == "CSRF_FAILED"
    assert asset_count(env.session) == 0


def test_content_headers(env: Env) -> None:
    media_id = upload(env).json()["id"]
    response = env.call(env.staff, "GET", f"/media/{media_id}/content")
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/jpeg"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["cache-control"].startswith("private")
    assert "public" not in response.headers["cache-control"]
    assert response.headers["content-disposition"] == "inline"
    assert int(response.headers["content-length"]) == len(response.content)
    assert response.content[:3] == b"\xff\xd8\xff"


def test_content_requires_authentication(env: Env, make_client: Callable[[], TestClient]) -> None:
    media_id = upload(env).json()["id"]
    response = make_client().get(f"{env.base}/media/{media_id}/content")
    assert response.status_code == 401


def test_foreign_and_unknown_media_ids_are_404(
    env: Env,
    make_client: Callable[[], TestClient],
    db_session: Session,
    build_app: Callable[..., FastAPI],
) -> None:
    """INV-01: another workspace's member gets 404, never 403, and never the bytes."""
    media_id = upload(env).json()["id"]
    other, users = workspace_with_members(db_session, name="Başka Salon", slug="baska")
    outsider_client = make_client()
    outsider = Role(
        "owner", users["owner"], outsider_client, login(outsider_client, users["owner"])
    )
    # Their own workspace, the foreign media id:
    response = outsider.client.get(f"/api/v1/workspaces/{other.id}/media/{media_id}/content")
    assert response.status_code == 404 and response.json()["code"] == "NOT_FOUND"
    # The owner's workspace is not theirs either:
    response = outsider.client.get(
        f"/api/v1/workspaces/{env.workspace.id}/media/{media_id}/content"
    )
    assert response.status_code == 404
    response = outsider.client.post(
        f"/api/v1/workspaces/{env.workspace.id}{UPLOAD}",
        files={"file": ("a.png", png_bytes(), "image/png")},
        headers=outsider.headers,
    )
    assert response.status_code == 404
    assert asset_count(db_session) == 1
    # And an unknown id in the right workspace:
    unknown = env.call(env.owner, "GET", "/media/00000000-0000-0000-0000-000000000000/content")
    assert unknown.status_code == 404


def test_a_deleted_asset_or_a_missing_object_is_404(env: Env, media_root: Path) -> None:
    first = upload(env).json()["id"]
    second = upload(env).json()["id"]
    row = env.session.scalars(select(MediaAsset).where(MediaAsset.id == first)).one()
    row.status = "deleted"
    env.session.flush()
    assert env.call(env.owner, "GET", f"/media/{first}/content").status_code == 404
    for path in stored_files(media_root):
        path.unlink()
    assert env.call(env.owner, "GET", f"/media/{second}/content").status_code == 404


def test_the_media_asset_response_has_no_storage_details(env: Env) -> None:
    body = upload(env).json()
    assert set(body) == {
        "id",
        "status",
        "width",
        "height",
        "mime_type",
        "byte_size",
        "original_filename",
        "rejection_code",
        "created_at",
    }
    assert not re.search(r"storage|sha256|\.jpg", str(body))
