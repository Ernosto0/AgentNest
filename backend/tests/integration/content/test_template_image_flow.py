"""Template image evidence, price holds, re-render and explicit resubmission."""

import uuid

import pytest
from sqlalchemy import select

from app.approvals.models import Approval
from app.content.models import MediaAsset
from app.content.templates.service import prepare
from app.content.templates.spec import HoursCard
from app.knowledge import service as knowledge
from app.knowledge.models import FactReference
from tests.factories import create_fact, money
from tests.helpers.content import connect_account
from tests.helpers.env import Env
from tests.integration.content.test_schedule import EVENING

KEY = "pricing.membership_monthly"


def render(env, key=KEY):
    r = env.call(
        env.owner,
        "POST",
        "/content/template-images",
        json={"template": "price_card", "format": "story", "fact_key": key},
    )
    assert r.status_code == 201, r.text
    return r.json()


def draft(env, asset):
    r = env.call(
        env.owner,
        "POST",
        "/content-items",
        json={"title": "Price card", "content_type": "story_image", "media_asset_id": asset["id"]},
    )
    assert r.status_code == 201, r.text
    return r.json()


def refs(env, id):
    env.session.expire_all()
    return [
        (r.fact_id, r.fact_version)
        for r in env.session.scalars(
            select(FactReference).where(
                FactReference.referrer_id == uuid.UUID(id),
                FactReference.referrer_type == "content_item",
            )
        )
    ]


def change(env, fact, value="7000"):
    knowledge.update_fact(
        env.session,
        env.clock,
        env.ctx(env.owner),
        fact.id,
        expected_version=fact.current_version,
        value=money(value),
    )


def test_references_follow_media_not_caption(env: Env):
    first = create_fact(env.session, env.workspace, KEY, money(), clock=env.clock)
    other = create_fact(
        env.session,
        env.workspace,
        "pricing.other",
        money("900"),
        value_type="money",
        clock=env.clock,
    )
    item = draft(env, render(env))
    assert refs(env, item["id"]) == [(first.id, 1)]
    r = env.call(
        env.owner,
        "PATCH",
        f"/content-items/{item['id']}",
        json={"expected_version": 1, "caption": ""},
    )
    assert r.status_code == 200
    assert refs(env, item["id"]) == [(first.id, 1)]
    asset = render(env, other.key)
    r = env.call(
        env.owner,
        "PATCH",
        f"/content-items/{item['id']}",
        json={"expected_version": 1, "media_asset_id": asset["id"]},
    )
    assert r.status_code == 200, r.text
    assert refs(env, item["id"]) == [(other.id, 1)]
    r = env.call(
        env.owner,
        "PATCH",
        f"/content-items/{item['id']}",
        json={"expected_version": 2, "media_asset_id": None},
    )
    assert r.status_code == 200
    assert refs(env, item["id"]) == [] and r.json()["template_image"] is None


@pytest.mark.parametrize("self_approve", [True, False])
def test_price_change_holds_and_rerender_requires_new_approval(env: Env, self_approve):
    connect_account(env)
    fact = create_fact(env.session, env.workspace, KEY, money(), clock=env.clock)
    unrelated = create_fact(
        env.session,
        env.workspace,
        "pricing.other",
        money("800"),
        value_type="money",
        clock=env.clock,
    )
    item = draft(env, render(env))
    path = f"/content-items/{item['id']}"
    r = env.call(
        env.owner,
        "POST",
        path + "/submit",
        json={"expected_version": 1, "schedule": EVENING, "self_approve": self_approve},
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == ("scheduled" if self_approve else "pending_approval")
    old_approval = r.json()["approval_id"]
    change(env, unrelated, "900")
    assert env.call(env.owner, "GET", path).json()["status"] == r.json()["status"]
    change(env, fact)
    before = env.call(env.owner, "GET", path).json()
    assert before["status"] == ("on_hold" if self_approve else "draft")
    assert before["template_image"]["stale"]
    refused = env.call(
        env.owner,
        "POST",
        path + "/submit",
        json={"expected_version": 1, "schedule": EVENING, "self_approve": False},
    )
    # on_hold submits through reapprove; pending approval was reverted to draft.
    if not self_approve:
        assert refused.status_code == 422
        assert "TEMPLATE_IMAGE_STALE" in [e["code"] for e in refused.json()["errors"]]
    r = env.call(env.staff, "POST", path + "/template-image/rerender", json={"expected_version": 1})
    assert r.status_code == 200, r.text
    new = r.json()
    assert new["version"] == 2 and new["status"] == "draft"
    assert new["media_asset_id"] != item["media_asset_id"]
    assert not new["template_image"]["stale"]
    assert refs(env, item["id"]) == [(fact.id, 2)]
    env.session.expire_all()
    assert env.session.get(Approval, uuid.UUID(old_approval)).status == (
        "approved" if self_approve else "cancelled"
    )
    asset = env.session.get(MediaAsset, uuid.UUID(new["media_asset_id"]))
    assert asset.render_record["facts"][0]["version"] == 2
    fresh = env.call(
        env.staff,
        "POST",
        path + "/submit",
        json={"expected_version": 2, "schedule": EVENING, "self_approve": False},
    )
    assert fresh.status_code == 200, fresh.text
    assert (
        fresh.json()["status"] == "pending_approval" and fresh.json()["approval_id"] != old_approval
    )


def test_stale_draft_submit_and_rerender_conflicts(env: Env):
    connect_account(env)
    fact = create_fact(env.session, env.workspace, KEY, money(), clock=env.clock)
    item = draft(env, render(env))
    change(env, fact)
    path = f"/content-items/{item['id']}"
    r = env.call(
        env.owner,
        "POST",
        path + "/submit",
        json={"expected_version": 1, "schedule": EVENING, "self_approve": True},
    )
    assert r.status_code == 422 and r.json()["code"] == "CONTENT_VALIDATION_FAILED"
    assert "TEMPLATE_IMAGE_STALE" in [e["code"] for e in r.json()["errors"]]
    r = env.call(env.owner, "POST", path + "/template-image/rerender", json={"expected_version": 2})
    assert r.status_code == 409 and r.json()["code"] == "VERSION_CONFLICT"
    r = env.call(
        env.owner,
        "POST",
        f"/content-items/{uuid.uuid4()}/template-image/rerender",
        json={"expected_version": 1},
    )
    assert r.status_code == 404
    plain = draft(env, {"id": None})
    r = env.call(
        env.owner,
        "POST",
        f"/content-items/{plain['id']}/template-image/rerender",
        json={"expected_version": 1},
    )
    assert r.status_code == 409 and r.json()["code"] == "CONFLICT_STATE"


def test_hours_exception_comma_is_one_row(env: Env):
    value = {
        "mon": [["09:00", "17:00"]],
        "exceptions": [{"date": "2026-01-20", "closed": True, "note": {"tr": "Bakım, temizlik"}}],
    }
    create_fact(env.session, env.workspace, "hours.weekly", value, clock=env.clock)
    card, record, _ = prepare(
        env.session, env.clock, env.ctx(env.owner), HoursCard(template="hours_card", format="story")
    )
    assert sum("Bakım, temizlik" in row for row in card.rows) == 1
    assert record.to_input() == HoursCard(template="hours_card", format="story", language="tr")


def test_pending_approval_rerender_cancels_old_card_and_publish_job(env: Env):
    from app.jobs.models import Job
    from tests.helpers.content import publish_job

    connect_account(env)
    create_fact(env.session, env.workspace, KEY, money(), clock=env.clock)
    item = draft(env, render(env))
    path = f"/content-items/{item['id']}"
    response = env.call(
        env.staff,
        "POST",
        path + "/submit",
        json={"expected_version": 1, "schedule": EVENING, "self_approve": False},
    )
    assert response.status_code == 200, response.text
    card_id = uuid.UUID(response.json()["approval_id"])
    from app.content.models import ContentItem

    row = env.session.get(ContentItem, uuid.UUID(item["id"]))
    queued = publish_job(env, row)
    env.session.commit()
    before = len(env.session.scalars(select(Approval)).all())
    result = env.call(
        env.staff, "POST", path + "/template-image/rerender", json={"expected_version": 1}
    )
    assert result.status_code == 200, result.text
    assert result.json()["status"] == "draft" and result.json()["version"] == 2
    env.session.expire_all()
    card = env.session.get(Approval, card_id)
    assert card.status == "cancelled" and card.cancel_reason == "SUBJECT_EDITED"
    assert env.session.get(Job, queued.id).status == "cancelled"
    assert len(env.session.scalars(select(Approval)).all()) == before
    assert not env.session.scalars(
        select(Job).where(Job.status == "queued", Job.job_type == "publish_content")
    ).all()


def test_upload_has_no_render_references(env: Env):
    from tests.helpers.images import png_bytes

    response = env.call(
        env.owner, "POST", "/media", files={"file": ("upload.png", png_bytes(), "image/png")}
    )
    assert response.status_code == 201, response.text
    item = draft(env, response.json())
    assert item["template_image"] is None and refs(env, item["id"]) == []


def test_rendered_stale_version_wins_when_caption_is_current(env: Env):
    fact = create_fact(env.session, env.workspace, KEY, money(), clock=env.clock)
    asset = render(env)
    change(env, fact)
    response = env.call(
        env.owner,
        "POST",
        "/content-items",
        json={
            "title": "Price",
            "content_type": "feed_image",
            "caption": "7.000 ₺ / ay",
            "media_asset_id": asset["id"],
        },
    )
    assert response.status_code == 201, response.text
    item = response.json()
    assert refs(env, item["id"]) == [(fact.id, 1)] and item["template_image"]["stale"]


def test_rerender_refusal_changes_nothing_and_reapprove_blocks_stale(env: Env):
    from app.content.models import ContentItem
    from app.jobs.models import Job

    connect_account(env)
    fact = create_fact(env.session, env.workspace, KEY, money(), clock=env.clock)
    item = draft(env, render(env))
    path = f"/content-items/{item['id']}"
    response = env.call(
        env.owner,
        "POST",
        path + "/submit",
        json={"expected_version": 1, "schedule": EVENING, "self_approve": True},
    )
    assert response.status_code == 200, response.text
    change(env, fact)
    response = env.call(
        env.owner, "POST", path + "/reapprove", json={"expected_version": 1, "schedule": EVENING}
    )
    assert response.status_code == 422, response.text
    assert "TEMPLATE_IMAGE_STALE" in [e["code"] for e in response.json()["errors"]]
    fact.status = "unverified"
    env.session.commit()
    before_assets = len(env.session.scalars(select(MediaAsset)).all())
    response = env.call(
        env.owner, "POST", path + "/template-image/rerender", json={"expected_version": 1}
    )
    assert response.status_code == 422 and response.json()["code"] == "TEMPLATE_FACT_NOT_USABLE"
    env.session.expire_all()
    row = env.session.get(ContentItem, uuid.UUID(item["id"]))
    assert (
        row.status == "on_hold"
        and row.version == 1
        and str(row.media_asset_id) == item["media_asset_id"]
    )
    assert len(env.session.scalars(select(MediaAsset)).all()) == before_assets
    assert not env.session.scalars(
        select(Job).where(Job.job_type == "publish_content", Job.status == "queued")
    ).all()
