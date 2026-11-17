"""Foreign content IDs cannot be re-rendered (INV-01)."""

import uuid


def test_rerender_foreign_item_and_unknown_are_404(two_workspaces):
    t = two_workspaces
    for id in [t.foreign_ids["content_id"], uuid.uuid4()]:
        response = t.a_client.post(
            f"/api/v1/workspaces/{t.a.id}/content-items/{id}/template-image/rerender",
            headers=t.a_headers,
            json={"expected_version": 1},
        )
        assert response.status_code == 404, response.text


def test_render_job_cannot_touch_foreign_draft(two_workspaces, shared_session_factory, clock):
    from sqlalchemy import select

    from app.content.models import ContentItem, MediaAsset
    from app.content.payload import RenderTemplateImagePayload
    from app.content.templates.jobs import render_template_image
    from app.content.templates.spec import PriceCard
    from app.jobs.registry import JobContext

    t = two_workspaces
    foreign = uuid.UUID(t.foreign_ids["content_id"])
    with shared_session_factory() as db:
        item = db.get(ContentItem, foreign)
        before = (item.version, item.media_asset_id)
        count = len(db.scalars(select(MediaAsset)).all())
    job = JobContext(
        uuid.uuid4(),
        "render_template_image",
        t.a.id,
        None,
        RenderTemplateImagePayload(
            content_id=foreign,
            version=before[0],
            template_input=PriceCard(
                template="price_card", format="story", fact_key="pricing.membership_monthly"
            ),
        ),
        1,
        3,
        shared_session_factory,
        clock,
        lambda: None,
    )
    render_template_image(job)
    with shared_session_factory() as db:
        item = db.get(ContentItem, foreign)
        assert (item.version, item.media_asset_id) == before
        assert len(db.scalars(select(MediaAsset)).all()) == count
