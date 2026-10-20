"""The canonical approval payload and its hash (plan.md G5, INV-16)."""

import uuid
from datetime import UTC, datetime, timedelta, timezone

from app.content.models import ContentItem
from app.content.payload import (
    PublishContentPayload,
    approval_payload,
    approval_payload_hash,
    approval_summary,
    publish_job_key,
)

CONTENT_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
ACCOUNT_ID = uuid.UUID("22222222-2222-2222-2222-222222222222")
MEDIA_ID = uuid.UUID("33333333-3333-3333-3333-333333333333")
AT = datetime(2026, 1, 15, 16, 0, tzinfo=UTC)


def item(**overrides: object) -> ContentItem:
    values: dict[str, object] = {
        "id": CONTENT_ID,
        "content_type": "story_image",
        "title": "Deneme dersi",
        "caption": None,
        "overlay_text_suggestions": ["Deneme dersi bizden", "Hemen yazın"],
        "media_asset_id": MEDIA_ID,
        **overrides,
    }
    return ContentItem(**values)


def payload(subject: ContentItem | None = None, **overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "version": 1,
        "social_account_id": ACCOUNT_ID,
        "media_sha256": "ab" * 32,
        "scheduled_at": AT,
        **overrides,
    }
    return approval_payload(subject or item(), **values)  # type: ignore[arg-type]


def test_the_payload_has_exactly_the_documented_keys() -> None:
    assert set(payload()) == {
        "content_id",
        "version",
        "content_type",
        "social_account_id",
        "caption",
        "overlay_text",
        "media_asset_id",
        "media_sha256",
        "scheduled_at",
    }


def test_overlay_text_is_the_list_of_suggestions_g5() -> None:
    assert payload()["overlay_text"] == ["Deneme dersi bizden", "Hemen yazın"]
    assert payload(item(overlay_text_suggestions=None))["overlay_text"] == []


def test_the_hash_is_stable_and_does_not_depend_on_key_order() -> None:
    first = payload()
    reordered = dict(reversed(list(first.items())))
    assert list(reordered) != list(first)
    assert approval_payload_hash(first) == approval_payload_hash(reordered)
    assert approval_payload_hash(first) == approval_payload_hash(payload())
    assert len(approval_payload_hash(first)) == 64


def test_the_same_instant_in_another_zone_hashes_the_same() -> None:
    istanbul = datetime(2026, 1, 15, 19, 0, tzinfo=timezone(timedelta(hours=3)))
    assert approval_payload_hash(payload()) == approval_payload_hash(payload(scheduled_at=istanbul))


def test_every_bound_field_changes_the_hash() -> None:
    base = approval_payload_hash(payload())
    changes = {
        "caption": payload(item(caption="Başka")),
        "overlay": payload(item(overlay_text_suggestions=["Başka"])),
        "media_asset": payload(item(media_asset_id=uuid.uuid4())),
        "content_type": payload(item(content_type="feed_image")),
        "version": payload(version=2),
        "account": payload(social_account_id=uuid.uuid4()),
        "media_sha256": payload(media_sha256="cd" * 32),
        "scheduled_at": payload(scheduled_at=AT + timedelta(minutes=1)),
        "content_id": payload(item(id=uuid.uuid4())),
    }
    hashes = {name: approval_payload_hash(p) for name, p in changes.items()}
    assert all(h != base for h in hashes.values()), hashes
    assert len(set(hashes.values())) == len(hashes)


def test_the_title_and_notes_are_not_bound() -> None:
    assert approval_payload_hash(payload(item(title="Yeni başlık"))) == approval_payload_hash(
        payload()
    )


def test_the_summary_shows_ids_title_and_instant_but_no_caption() -> None:
    summary = approval_summary(item(caption="gizli metin"), AT)
    assert summary == {
        "content_id": str(CONTENT_ID),
        "content_type": "story_image",
        "title": "Deneme dersi",
        "scheduled_at": AT.isoformat(),
    }


def test_the_job_payload_carries_ids_only_and_the_key_is_per_version() -> None:
    assert PublishContentPayload(content_id=CONTENT_ID, version=3).model_dump(mode="json") == {
        "content_id": str(CONTENT_ID),
        "version": 3,
    }
    assert publish_job_key(CONTENT_ID, 3) == f"publish:{CONTENT_ID}:v3"
    assert publish_job_key(CONTENT_ID, 3) != publish_job_key(CONTENT_ID, 4)
