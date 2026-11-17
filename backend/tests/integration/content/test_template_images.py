"""F-07 render refusals, provenance, preview, brand and media retention contracts."""

import io
from datetime import timedelta
from pathlib import Path

import pytest
from PIL import Image
from sqlalchemy import select

from app.content.media_cleanup import eligible
from app.content.models import MediaAsset
from app.content.templates.spec import RenderRecord
from app.core.config import Settings
from app.knowledge import service as knowledge
from tests.factories import create_candidate, create_fact, create_workspace, money
from tests.helpers.env import Env
from tests.helpers.images import png_bytes

KEY = "pricing.membership_monthly"
BODY = {"template": "price_card", "format": "story", "fact_key": KEY}
BRAND = {"primary_color": "#AABBCC", "accent_color": "#112233", "logo_media_asset_id": None}


def files(root: Path):
    return [p for p in root.rglob("*") if p.is_file()]


def test_preview_stores_nothing_and_create_records_fact_versions(env: Env, media_root: Path):
    fact = create_fact(env.session, env.workspace, KEY, money(), clock=env.clock)
    preview = env.call(env.owner, "POST", "/content/template-images/preview", json=BODY)
    assert preview.status_code == 200, preview.text
    assert preview.headers["content-type"] == "image/jpeg"
    assert not files(media_root)
    assert not env.session.scalars(select(MediaAsset)).all()
    response = env.call(env.owner, "POST", "/content/template-images", json=BODY)
    assert response.status_code == 201, response.text
    data = response.json()
    record = RenderRecord.model_validate(data["render_record"])
    assert record.fact_references() == ((fact.id, 1),)
    assert record.rendered_at == env.clock.now()
    assert record.inputs == {}
    assert record.language == "tr"
    assert record.renderer_version == "1"
    asset = env.session.get(MediaAsset, data["id"])
    assert asset.render_record == data["render_record"]
    (stored,) = files(media_root)
    image = Image.open(io.BytesIO(stored.read_bytes()))
    assert image.format == "JPEG" and image.mode == "RGB"
    assert image.size == (1080, 1920) and not image.getexif()
    assert stored.read_bytes() == preview.content
    knowledge.update_fact(
        env.session, env.clock, env.ctx(env.owner), fact.id, expected_version=1, value=money("7000")
    )
    rerender = env.call(env.owner, "POST", "/content/template-images", json=BODY)
    assert rerender.status_code == 201, rerender.text
    assert rerender.json()["render_record"]["facts"][0]["version"] == 2


@pytest.mark.parametrize("state", ["missing", "unverified", "contested", "expired", "archived"])
def test_unusable_fact_refuses_without_any_output(env: Env, media_root: Path, state):
    if state != "missing":
        fact = create_fact(
            env.session,
            env.workspace,
            KEY,
            money(),
            verified=state != "unverified",
            clock=env.clock,
        )
        if state == "contested":
            create_candidate(
                env.session, env.workspace, KEY, money("9000"), source_type="staff_proposal"
            )
        if state == "expired":
            fact.valid_until = env.clock.now().date() - timedelta(days=1)
        if state == "archived":
            fact.status = "archived"
        env.session.commit()
    for path in ("/content/template-images", "/content/template-images/preview"):
        response = env.call(env.owner, "POST", path, json=BODY)
        assert response.status_code == 422, response.text
        assert response.json()["code"] == "TEMPLATE_FACT_NOT_USABLE"
        assert response.json()["params"]["keys"] == [KEY]
    assert not env.session.scalars(select(MediaAsset)).all()
    assert not files(media_root)


def test_type_mismatch(env: Env):
    create_fact(env.session, env.workspace, "contact.phone", {"e164": "+905551234567"})
    response = env.call(
        env.owner, "POST", "/content/template-images", json={**BODY, "fact_key": "contact.phone"}
    )
    assert response.status_code == 422
    assert response.json()["code"] == "TEMPLATE_FACT_TYPE_MISMATCH"


@pytest.mark.parametrize(
    "text",
    [
        "Only 6000 TL",
        "Call +905551234567",
        "Visit https://example.com",
        "At 09:30",
        "Free",
        "Sale 50",
        "mail@example.com",
    ],
)
def test_unbacked_free_text_refused(env: Env, media_root: Path, text):
    response = env.call(
        env.owner,
        "POST",
        "/content/template-images",
        json={"template": "announcement", "format": "feed", "headline": text, "body": "Welcome"},
    )
    assert response.status_code == 422, response.text
    assert response.json()["code"] == "TEMPLATE_TEXT_UNGROUNDED"
    assert response.json()["params"]["fields"] == ["headline"]
    assert not files(media_root)


def test_placeholders_are_grounded_and_recorded_once_in_first_use_order(env: Env):
    first = create_fact(env.session, env.workspace, KEY, money())
    other = create_fact(
        env.session,
        env.workspace,
        "custom.session",
        money("900"),
        value_type="money",
        label={"tr": "Ders", "en": "Class"},
    )
    response = env.call(
        env.owner,
        "POST",
        "/content/template-images",
        json={
            "template": "announcement",
            "format": "feed",
            "language": "en",
            "headline": "Welcome",
            "body": "{{fact:custom.session}} and {{fact:pricing.membership_monthly}}",
            "date_line": "{{fact:custom.session}}",
        },
    )
    assert response.status_code == 201, response.text
    record = RenderRecord.model_validate(response.json()["render_record"])
    assert record.fact_references() == ((other.id, 1), (first.id, 1))
    assert record.inputs["headline"] == "Welcome"


def test_brand_defaults_update_validation_permissions_and_audit(env: Env):
    default = env.call(env.staff, "GET", "/brand")
    assert default.status_code == 200 and default.json()["is_default"]
    assert default.json()["logo_width"] is None
    response = env.call(env.manager, "PUT", "/brand", json=BRAND)
    assert response.status_code == 200, response.text
    assert response.json()["primary_color"] == "#aabbcc"
    assert not response.json()["is_default"]
    assert env.call(env.staff, "PUT", "/brand", json=BRAND).status_code == 403
    assert (
        env.call(env.owner, "PUT", "/brand", json={**BRAND, "primary_color": "red"}).status_code
        == 422
    )
    assert env.call(env.owner, "PUT", "/brand", json={**BRAND, "surprise": True}).status_code == 422
    from app.audit.models import AuditLog

    actions = env.session.scalars(select(AuditLog.action)).all()
    assert "brand.updated" in actions


def test_brand_logo_uses_upload_and_is_excluded_from_cleanup(env: Env, settings: Settings):
    upload = env.call(
        env.owner, "POST", "/media", files={"file": ("logo.png", png_bytes((120, 80)), "image/png")}
    )
    assert upload.status_code == 201
    asset = env.session.get(MediaAsset, upload.json()["id"])
    asset.created_at = env.clock.now() - timedelta(days=10)
    env.session.commit()
    saved = env.call(
        env.owner, "PUT", "/brand", json={**BRAND, "logo_media_asset_id": str(asset.id)}
    )
    assert saved.status_code == 200
    assert (saved.json()["logo_width"], saved.json()["logo_height"]) == (120, 80)
    assert not env.session.scalars(
        select(MediaAsset).where(eligible(settings, env.clock.now()))
    ).all()
    env.call(env.owner, "PUT", "/brand", json=BRAND)
    assert (
        env.session.scalars(select(MediaAsset).where(eligible(settings, env.clock.now()))).one().id
        == asset.id
    )
    asset.status = "deleted"
    env.session.commit()
    assert (
        env.call(
            env.owner, "PUT", "/brand", json={**BRAND, "logo_media_asset_id": str(asset.id)}
        ).status_code
        == 404
    )


def test_foreign_logo_and_fact_are_not_accessible(env: Env):
    other = create_workspace(env.session)
    create_fact(
        env.session, other, "custom.foreign", money(), value_type="money", label={"tr": "Yabancı"}
    )
    asset = MediaAsset(
        workspace_id=other.id,
        storage_backend="local",
        storage_key="foreign",
        mime_type="image/jpeg",
        width=10,
        height=10,
        byte_size=10,
        sha256="a" * 64,
        status="ready",
    )
    env.session.add(asset)
    env.session.commit()
    assert (
        env.call(
            env.owner, "PUT", "/brand", json={**BRAND, "logo_media_asset_id": str(asset.id)}
        ).status_code
        == 404
    )
    response = env.call(
        env.owner, "POST", "/content/template-images", json={**BODY, "fact_key": "custom.foreign"}
    )
    assert response.status_code == 422
    assert response.json()["code"] == "TEMPLATE_FACT_NOT_USABLE"


def test_catalog_is_bilingual_and_complete(env: Env):
    response = env.call(env.staff, "GET", "/content/templates")
    assert response.status_code == 200
    cards = response.json()
    assert len(cards) == 4
    assert all(set(card["labels"]) == {"tr", "en"} for card in cards)
    assert all(len(card["formats"]) == 2 for card in cards)


@pytest.mark.parametrize("template", ["hours_card", "services_list"])
def test_structured_cards_resolve_formatted_values_and_default_locale(env: Env, template):
    from app.content.templates.service import prepare
    from app.content.templates.spec import HoursCard, ServicesList
    from app.knowledge.formatting import format_weekly_hours

    env.workspace.default_locale = "en"
    env.session.commit()
    if template == "hours_card":
        value = {"mon": [["09:00", "18:00"]], "tue": [["09:00", "18:00"]]}
        fact = create_fact(env.session, env.workspace, "hours.weekly", value)
        body = HoursCard(template="hours_card", format="feed")
        card, record, _ = prepare(env.session, env.clock, env.ctx(env.owner), body)
        assert ", ".join(card.rows) == format_weekly_hours(fact.value, "en")
        assert record.fact_references() == ((fact.id, 1),)
    else:
        first = create_fact(env.session, env.workspace, KEY, money())
        other = create_fact(
            env.session,
            env.workspace,
            "custom.class",
            money("900"),
            value_type="money",
            label={"tr": "Ders", "en": "Class"},
        )
        body = ServicesList(
            template="services_list", format="feed", fact_keys=[KEY, "custom.class"]
        )
        card, record, _ = prepare(env.session, env.clock, env.ctx(env.owner), body)
        assert card.rows[1].startswith("Class — ")
        assert record.fact_references() == ((first.id, 1), (other.id, 1))
    assert record.language == "en"
    assert not env.session.in_transaction()


def test_placeholder_does_not_authorize_additional_literal_discount(env: Env):
    create_fact(
        env.session,
        env.workspace,
        "custom.url",
        {"url": "https://example.com"},
        value_type="url",
        label={"en": "Website"},
    )
    response = env.call(
        env.owner,
        "POST",
        "/content/template-images",
        json={
            "template": "announcement",
            "format": "feed",
            "headline": "Welcome",
            "body": "{{fact:custom.url}} https://example.com",
        },
    )
    assert response.status_code == 422
    assert response.json()["code"] == "TEMPLATE_TEXT_UNGROUNDED"
