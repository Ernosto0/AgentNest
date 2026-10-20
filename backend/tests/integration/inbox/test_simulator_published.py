"""P5-05: the read-only dev endpoint that lists what the mock Instagram published."""

import io
import uuid
from pathlib import Path

import pytest

from app.integrations.instagram.base import AccountRef, ContainerSpec
from app.integrations.instagram.mock import MockInstagramProvider
from app.integrations.storage.base import build_key
from app.integrations.storage.local import LocalMediaStorage
from tests.contract.test_instagram_provider_contract import jpeg_bytes
from tests.factories import create_workspace
from tests.integration.inbox.conftest import APP_SECRET, InboxEnv
from tests.integration.inbox.test_simulator import dev, ws


def publish_one(inbox: InboxEnv, tmp_path: Path, caption: str | None) -> str:
    storage = LocalMediaStorage(tmp_path, inbox.clock)
    provider = MockInstagramProvider(
        inbox.factory, inbox.clock, APP_SECRET, storage=storage, container_delay_s=0
    )
    account = AccountRef(inbox.account.id, inbox.account.workspace_id, "mock-golkent")
    key = build_key(account.workspace_id, uuid.uuid4(), inbox.clock.now())
    storage.put(key, io.BytesIO(jpeg_bytes()), "image/jpeg")
    media_type = "STORIES" if caption is None else "IMAGE"
    spec = ContainerSpec(media_type, storage.public_fetch_url(key, 60), caption)  # type: ignore[arg-type]
    container_id = provider.create_media_container(account, spec)
    return provider.publish_container(account, container_id)


def test_the_listing_shows_each_published_post_once_and_newest_first(
    inbox: InboxEnv, tmp_path: Path
) -> None:
    assert dev(inbox, "GET", ws(inbox, "/simulator/published")).json() == {
        "items": [],
        "next_cursor": None,
    }
    first = publish_one(inbox, tmp_path, "Yeni sezon")
    inbox.clock.advance(minutes=5)
    second = publish_one(inbox, tmp_path, None)

    response = dev(inbox, "GET", ws(inbox, "/simulator/published"))

    assert response.status_code == 200, response.text
    items = response.json()["items"]
    assert [i["media_id"] for i in items] == [second, first]
    assert [(i["media_type"], i["caption"]) for i in items] == [
        ("STORIES", None),
        ("IMAGE", "Yeni sezon"),
    ]
    assert items[0]["permalink"] == f"https://instagram.example/sim/{second}"
    assert all(i["is_simulated"] is True for i in items)


def test_the_listing_is_owner_only_and_workspace_scoped(inbox: InboxEnv, tmp_path: Path) -> None:
    publish_one(inbox, tmp_path, "x")
    for role in ("manager", "staff"):
        assert dev(inbox, "GET", ws(inbox, "/simulator/published"), role=role).status_code == 403
    other = create_workspace(inbox.session, name="Other")
    assert dev(inbox, "GET", f"/workspaces/{other.id}/simulator/published").status_code == 404


def test_the_listing_is_read_only(inbox: InboxEnv) -> None:
    for method in ("POST", "PUT", "DELETE"):
        response = dev(inbox, method, ws(inbox, "/simulator/published"), json={})
        assert response.status_code == 405


@pytest.mark.parametrize("operation", ["create_container", "container_status", "publish"])
def test_the_publishing_operations_can_be_scripted_from_the_dev_panel(
    inbox: InboxEnv, operation: str
) -> None:
    response = dev(
        inbox,
        "POST",
        ws(inbox, "/failure-rules"),
        json={"operation": operation, "mode": "transient"},
    )
    assert response.status_code == 201
    assert response.json()["operation"] == operation
