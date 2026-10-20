"""P5-02: content items over the API: create, read, list tabs, edit (api-design.md 2.7)."""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import select

from app.audit.models import AuditLog
from app.content.models import ContentItem, MediaAsset
from app.knowledge import service as knowledge_service
from app.knowledge.models import FactReference
from tests.factories import create_fact, money, workspace_with_members
from tests.helpers.content import make_item
from tests.helpers.env import Env, Role
from tests.helpers.images import png_bytes

ITEMS = "/content-items"
CLEAN_VALIDATION = {"passed": True, "issues": [], "stale": False, "errors": [], "warnings": []}


def create(env: Env, role: Role | None = None, **body: Any) -> Any:
    payload = {"content_type": "feed_image", "title": "Cuma paylaşımı", **body}
    return env.call(role or env.owner, "POST", ITEMS, json=payload)


def patch(env: Env, item_id: str, version: int, role: Role | None = None, **body: Any) -> Any:
    return env.call(
        role or env.owner,
        "PATCH",
        f"{ITEMS}/{item_id}",
        json={"expected_version": version, **body},
    )


def references(env: Env, item_id: str) -> set[uuid.UUID]:
    return set(
        env.session.scalars(
            select(FactReference.fact_id).where(
                FactReference.referrer_type == "content_item",
                FactReference.referrer_id == uuid.UUID(item_id),
            )
        )
    )


def price_display(env: Env) -> str:
    (fact,) = [
        f
        for f in knowledge_service.usable_facts(env.session, env.clock, env.ctx(env.owner))
        if f.key == "pricing.membership_monthly"
    ]
    return fact.display


def audit_actions(env: Env, action: str) -> list[AuditLog]:
    return list(env.session.scalars(select(AuditLog).where(AuditLog.action == action)))


# --- create and read -----------------------------------------------------------------------


def test_create_makes_a_version_one_draft_and_audits_it(env: Env) -> None:
    response = create(env, caption="Yarın görüşürüz!")
    assert response.status_code == 201, response.text
    body = response.json()
    assert (body["status"], body["version"], body["content_type"]) == ("draft", 1, "feed_image")
    assert body["caption"] == "Yarın görüşürüz!"
    assert body["overlay_text_suggestions"] == []
    assert body["validation"] == {**CLEAN_VALIDATION}
    assert body["approval"] is None and body["operation"] is None
    assert body["schedule_local"] is None
    assert body["is_simulated"] is False
    assert body["created_by_user_id"] == str(env.owner.user.id)

    (entry,) = audit_actions(env, "content.created")
    assert str(entry.resource_id) == body["id"]
    assert entry.workspace_id == env.workspace.id


def test_every_role_can_create_and_read(env: Env) -> None:
    """``content.edit`` belongs to all roles (workflows.md E)."""
    for role in (env.owner, env.manager, env.staff):
        response = create(env, role, title=f"Taslak {role.name}")
        assert response.status_code == 201, (role.name, response.text)
        item_id = response.json()["id"]
        for reader in (env.owner, env.manager, env.staff):
            assert env.call(reader, "GET", f"{ITEMS}/{item_id}").status_code == 200


def test_a_story_keeps_its_overlay_suggestions_clean(env: Env) -> None:
    response = create(
        env,
        content_type="story_image",
        overlay_text_suggestions=["  Deneme dersi bizden  ", "", "   ", "Yerini ayır"],
    )
    assert response.status_code == 201
    assert response.json()["overlay_text_suggestions"] == ["Deneme dersi bizden", "Yerini ayır"]


def test_the_same_client_request_returns_the_same_item(env: Env) -> None:
    first = create(env, client_request_id="istek-1")
    again = create(env, client_request_id="istek-1", title="Başka bir başlık")
    assert (first.status_code, again.status_code) == (201, 200)
    assert again.json()["id"] == first.json()["id"]
    assert again.json()["title"] == "Cuma paylaşımı"  # the earlier item, unchanged
    # Another author with the same request id gets their own item.
    other = create(env, env.manager, client_request_id="istek-1")
    assert other.status_code == 201 and other.json()["id"] != first.json()["id"]
    assert env.session.query(ContentItem).count() == 2


@pytest.mark.parametrize(
    "body",
    [
        {"content_type": "video", "title": "x"},
        {"content_type": "feed_image", "title": "   "},
        {"content_type": "feed_image", "title": "x", "caption": "x" * 5001},
        {"content_type": "feed_image", "title": "x", "overlay_text_suggestions": ["a"] * 11},
        {"content_type": "feed_image"},
    ],
)
def test_invalid_bodies_are_rejected_without_creating_anything(
    env: Env, body: dict[str, Any]
) -> None:
    response = env.call(env.owner, "POST", ITEMS, json=body)
    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_FAILED"
    assert env.session.query(ContentItem).count() == 0


def test_the_status_cannot_be_set_by_the_client(env: Env) -> None:
    response = env.call(
        env.owner,
        "POST",
        ITEMS,
        json={"content_type": "feed_image", "title": "x", "status": "published", "version": 9},
    )
    assert response.status_code == 201
    assert (response.json()["status"], response.json()["version"]) == ("draft", 1)


def test_an_item_can_be_created_with_media_that_belongs_to_the_workspace(env: Env) -> None:
    uploaded = env.call(
        env.owner, "POST", "/media", files={"file": ("a.png", png_bytes(), "image/png")}
    )
    assert uploaded.status_code == 201, uploaded.text
    media_id = uploaded.json()["id"]
    response = create(env, media_asset_id=media_id)
    assert response.status_code == 201
    assert response.json()["media_asset_id"] == media_id


def test_media_of_another_workspace_is_not_found(env: Env) -> None:
    other, users = workspace_with_members(env.session, name="Başka")
    foreign = MediaAsset(
        workspace_id=other.id,
        storage_backend="local",
        storage_key=f"{other.id}/2026/01/{uuid.uuid4()}.jpg",
        mime_type="image/jpeg",
        byte_size=1,
        width=10,
        height=10,
        sha256="0" * 64,
        status="ready",
        created_by_user_id=users["owner"].id,
    )
    env.session.add(foreign)
    env.session.flush()

    assert create(env, media_asset_id=str(foreign.id)).status_code == 404
    own = create(env).json()
    assert patch(env, own["id"], 1, media_asset_id=str(foreign.id)).status_code == 404
    stored = env.session.get(ContentItem, uuid.UUID(own["id"]))
    assert stored is not None and stored.media_asset_id is None


# --- tabs ----------------------------------------------------------------------------------


def listed(env: Env, query: str = "", role: Role | None = None) -> list[dict[str, Any]]:
    response = env.call(role or env.staff, "GET", f"{ITEMS}{query}")
    assert response.status_code == 200, response.text
    return response.json()["items"]  # type: ignore[no-any-return]


def test_the_tabs_map_to_statuses_as_in_g15(env: Env) -> None:
    statuses = (
        "draft",
        "pending_approval",
        "scheduled",
        "publishing",
        "retry_scheduled",
        "published",
        "on_hold",
        "failed",
        "rejected",
        "cancelled",
    )
    for status in statuses:
        make_item(env, status=status, title=status)

    def titles(query: str) -> set[str]:
        return {i["title"] for i in listed(env, query)}

    assert titles("?tab=drafts") == {"draft", "pending_approval"}
    assert titles("?tab=scheduled") == {"scheduled", "publishing", "retry_scheduled"}
    assert titles("?tab=published") == {"published"}
    assert titles("?tab=problems") == {"on_hold", "failed", "rejected"}
    in_a_tab = set().union(
        *(titles(f"?tab={t}") for t in ("drafts", "scheduled", "published", "problems"))
    )
    assert in_a_tab == set(statuses) - {"cancelled"}  # cancelled items are in no tab
    assert titles("?status=cancelled") == {"cancelled"}  # but can be asked for by status
    assert titles("") == set(statuses)
    assert titles("?tab=problems&status=failed") == {"failed"}


def test_the_scheduled_tab_lists_what_goes_out_next_first(env: Env) -> None:
    now = env.clock.now()
    make_item(env, status="scheduled", title="sonra", scheduled_at=now + timedelta(days=2))
    make_item(env, status="scheduled", title="önce", scheduled_at=now + timedelta(hours=1))
    make_item(env, status="retry_scheduled", title="orta", scheduled_at=now + timedelta(hours=5))
    assert [i["title"] for i in listed(env, "?tab=scheduled")] == ["önce", "orta", "sonra"]


def test_a_bad_tab_or_limit_is_a_validation_error(env: Env) -> None:
    for query in ("?tab=archive", "?status=gone", "?limit=0", "?limit=101"):
        response = env.call(env.owner, "GET", f"{ITEMS}{query}")
        assert response.status_code == 422, query
        assert response.json()["code"] == "VALIDATION_FAILED"


def test_schedule_local_is_shown_in_the_workspace_timezone(env: Env) -> None:
    item = make_item(
        env, status="scheduled", scheduled_at=datetime(2026, 10, 21, 16, 0, tzinfo=UTC)
    )
    body = env.call(env.owner, "GET", f"{ITEMS}/{item.id}").json()
    assert body["schedule_local"] == {
        "date": "2026-10-21",
        "time": "19:00",
        "timezone": "Europe/Istanbul",
    }


# --- editing -------------------------------------------------------------------------------


def test_a_payload_edit_is_a_new_version(env: Env) -> None:
    item = create(env, caption="Merhaba").json()
    response = patch(env, item["id"], 1, caption="Merhaba, hafta sonu açığız")
    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["version"], body["status"]) == (2, "draft")
    assert body["caption"] == "Merhaba, hafta sonu açığız"
    (entry,) = audit_actions(env, "content.updated")
    assert entry.metadata_["version"] == 2


def test_a_stale_expected_version_is_a_version_conflict(env: Env) -> None:
    item = create(env, caption="Merhaba").json()
    assert patch(env, item["id"], 1, caption="Bir").status_code == 200
    response = patch(env, item["id"], 1, caption="İki")  # the client still has version 1
    assert response.status_code == 409
    assert response.json()["code"] == "VERSION_CONFLICT"
    assert response.json()["params"] == {"expected": 1, "current": 2}
    after = env.call(env.owner, "GET", f"{ITEMS}/{item['id']}").json()
    assert (after["version"], after["caption"]) == (2, "Bir")


def test_a_title_or_a_note_is_not_a_new_version(env: Env) -> None:
    item = create(env, caption="Merhaba").json()
    body = patch(env, item["id"], 1, title="Yeni başlık", visual_notes="Sıcak tonlar").json()
    assert (body["version"], body["title"], body["visual_notes"]) == (
        1,
        "Yeni başlık",
        "Sıcak tonlar",
    )


def test_an_edit_that_changes_nothing_is_not_a_new_version(env: Env) -> None:
    item = create(env, caption="Merhaba", overlay_text_suggestions=["A"]).json()
    body = patch(
        env, item["id"], 1, caption="Merhaba", overlay_text_suggestions=["A"], title=item["title"]
    ).json()
    assert body["version"] == 1
    assert audit_actions(env, "content.updated") == []


def test_a_field_sent_as_null_is_cleared_and_an_absent_field_is_kept(env: Env) -> None:
    item = create(env, caption="Merhaba", overlay_text_suggestions=["A"]).json()
    body = patch(env, item["id"], 1, caption=None).json()
    assert (body["caption"], body["overlay_text_suggestions"], body["version"]) == (None, ["A"], 2)
    for field in ("title", "overlay_text_suggestions"):
        response = patch(env, item["id"], 2, **{field: None})
        assert response.status_code == 422, field
        assert response.json()["code"] == "VALIDATION_FAILED"


@pytest.mark.invariant("INV-17")
def test_nothing_can_be_edited_while_publishing_or_after_cancel_or_publish(env: Env) -> None:
    """``published`` is immutable (INV-17); the others have no edit transition either."""
    for status in ("publishing", "retry_scheduled", "published", "cancelled"):
        item = make_item(env, status=status, caption="Eski")
        response = patch(env, str(item.id), 1, caption="Yeni")
        assert response.status_code == 409, status
        assert response.json()["code"] == "CONFLICT_STATE"
        titled = patch(env, str(item.id), 1, title="Yeni başlık")
        assert titled.status_code == 409, status  # not even an internal label
        env.session.refresh(item)
        assert (item.status, item.caption, item.version, item.title) == (
            status,
            "Eski",
            1,
            "Haftalık paylaşım",
        )


@pytest.mark.parametrize("status", ["rejected", "failed", "on_hold"])
def test_a_problem_item_returns_to_draft_when_it_is_edited(env: Env, status: str) -> None:
    item = make_item(
        env,
        status=status,
        caption="Eski",
        hold_reason="FACT_CHANGED" if status == "on_hold" else None,
        last_error_code="MEDIA_REJECTED" if status == "failed" else None,
        rejection_note="Fiyatı düzelt" if status == "rejected" else None,
    )
    body = patch(env, str(item.id), 1, caption="Düzeltildi").json()
    assert (body["status"], body["version"]) == ("draft", 2)
    assert (body["hold_reason"], body["last_error_code"], body["rejection_note"]) == (
        None,
        None,
        None,
    )


# --- claim validation and fact references (G6) -----------------------------------------------


def test_a_price_typed_into_a_caption_is_grounded_and_a_fact_reference(env: Env) -> None:
    fact = create_fact(env.session, env.workspace, "pricing.membership_monthly", money("6000"))
    shown = price_display(env)
    item = create(env, caption="Merhaba!").json()
    assert references(env, item["id"]) == set()

    body = patch(env, item["id"], 1, caption=f"Aylık üyelik {shown}").json()

    # The value is the verified price: reported, grounded (it does not fail the report) and
    # recorded as a reference so a later price change reaches this item.
    assert body["validation"]["passed"] is True
    (issue,) = [i for i in body["validation"]["issues"] if i["field"] == "caption"]
    assert issue["matches_verified"] is True and issue["fact_key"] == "pricing.membership_monthly"
    assert issue["text"] in shown
    assert references(env, item["id"]) == {fact.id}
    row = env.session.scalars(
        select(FactReference).where(FactReference.referrer_id == uuid.UUID(item["id"]))
    ).one()
    assert row.fact_version == 1 and row.workspace_id == env.workspace.id

    # Take the price out again: the report is clean and the reference is gone.
    clean = patch(env, item["id"], 2, caption="Aylık üyelik için bize yazın").json()
    assert clean["validation"] == CLEAN_VALIDATION
    assert references(env, item["id"]) == set()


def test_a_value_that_matches_no_verified_fact_is_an_issue_without_a_reference(env: Env) -> None:
    create_fact(env.session, env.workspace, "pricing.membership_monthly", money("6000"))
    body = create(env, caption="Sadece bugün 1.234 TL!").json()
    assert body["validation"]["passed"] is False
    assert all(i["matches_verified"] is False for i in body["validation"]["issues"])
    assert references(env, body["id"]) == set()


def test_overlay_suggestions_are_checked_too(env: Env) -> None:
    body = create(
        env,
        content_type="story_image",
        overlay_text_suggestions=["Deneme dersi bizden", "%40 indirim!"],
    ).json()
    fields = {i["field"] for i in body["validation"]["issues"]}
    assert fields == {"overlay_text_suggestions.1"}


def test_validate_is_a_dry_run(env: Env) -> None:
    item = make_item(env, status="scheduled", caption="Sadece 999 TL")
    before = item.validation
    response = env.call(env.owner, "POST", f"{ITEMS}/{item.id}/validate")
    assert response.status_code == 200, response.text
    assert response.json()["passed"] is False
    assert response.json()["issues"][0]["field"] == "caption"
    env.session.refresh(item)
    assert (item.status, item.version, item.validation) == ("scheduled", 1, before)
    assert audit_actions(env, "content.updated") == []
