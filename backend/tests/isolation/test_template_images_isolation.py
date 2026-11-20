"""Brand/template API isolation and forced RLS (INV-01)."""

import uuid

import pytest
from sqlalchemy import select, text, update
from sqlalchemy.exc import DBAPIError, IntegrityError

from app.content.models import WorkspaceBrandSettings
from app.core.db import clear_tenant_context, set_tenant_context
from tests.factories import workspace_with_members
from tests.isolation.test_delegation_suggestions_isolation import as_role

BRAND = {"primary_color": "#123456", "accent_color": "#abcdef", "logo_media_asset_id": None}
BODY = {"template": "price_card", "format": "feed", "fact_key": "pricing.membership_monthly"}


@pytest.mark.invariant("INV-01")
def test_foreign_workspace_and_foreign_assets(two_workspaces):
    t = two_workspaces
    base = f"/api/v1/workspaces/{t.b.id}"
    for method, path, body in [
        ("GET", "/brand", None),
        ("PUT", "/brand", BRAND),
        ("GET", "/content/templates", None),
        ("POST", "/content/template-images", BODY),
        ("POST", "/content/template-images/preview", BODY),
    ]:
        response = t.a_client.request(method, base + path, json=body, headers=t.a_headers)
        assert response.status_code == 404, response.text
    base = f"/api/v1/workspaces/{t.a.id}"
    response = t.a_client.put(
        base + "/brand",
        json={**BRAND, "logo_media_asset_id": t.foreign_ids["media_id"]},
        headers=t.a_headers,
    )
    assert response.status_code == 404
    response = t.a_client.post(base + "/content/template-images", json=BODY, headers=t.a_headers)
    assert response.status_code == 422
    assert response.json()["code"] == "TEMPLATE_FACT_NOT_USABLE"


def test_brand_forced_rls_policy(db_session):
    assert tuple(
        db_session.execute(
            text(
                "SELECT relrowsecurity, relforcerowsecurity FROM pg_class "
                "WHERE oid = 'workspace_brand_settings'::regclass"
            )
        ).one()
    ) == (True, True)
    assert (
        db_session.execute(
            text(
                "SELECT polname FROM pg_policy "
                "WHERE polrelid = 'workspace_brand_settings'::regclass"
            )
        ).scalar_one()
        == "tenant_isolation_policy"
    )


@pytest.mark.invariant("INV-01")
def test_brand_rls_fail_closed_and_same_tenant_crud(db_session):
    a, _ = workspace_with_members(db_session)
    b, _ = workspace_with_members(db_session)
    row_a = WorkspaceBrandSettings(workspace_id=a.id, **BRAND)
    row_b = WorkspaceBrandSettings(workspace_id=b.id, **BRAND)
    db_session.add_all([row_a, row_b])
    db_session.commit()
    a_id, b_id, wa, wb = row_a.id, row_b.id, a.id, b.id
    db_session.expunge_all()
    clear_tenant_context(db_session)
    with as_role(db_session, "pivoris_app"):
        assert not db_session.scalars(select(WorkspaceBrandSettings)).all()
    set_tenant_context(db_session, wa)
    with as_role(db_session, "pivoris_app"):
        assert [r.id for r in db_session.scalars(select(WorkspaceBrandSettings))] == [a_id]
        assert (
            db_session.execute(
                update(WorkspaceBrandSettings)
                .where(WorkspaceBrandSettings.id == b_id)
                .values(primary_color="#ffffff")
            ).rowcount
            == 0
        )
        row = db_session.get(WorkspaceBrandSettings, a_id)
        row.primary_color = "#ffffff"
        db_session.flush()
        with pytest.raises(DBAPIError), db_session.begin_nested():
            db_session.execute(
                update(WorkspaceBrandSettings)
                .where(WorkspaceBrandSettings.id == a_id)
                .values(workspace_id=wb)
            )
        with pytest.raises(DBAPIError), db_session.begin_nested():
            insert_brand(db_session, WorkspaceBrandSettings(workspace_id=wb, **BRAND))


def insert_brand(session, row):
    session.add(row)
    session.flush()


def test_brand_composite_fk_refuses_foreign_logo(db_session, two_workspaces):
    row = WorkspaceBrandSettings(
        workspace_id=two_workspaces.a.id,
        **{**BRAND, "logo_media_asset_id": uuid.UUID(two_workspaces.foreign_ids["media_id"])},
    )
    with pytest.raises(IntegrityError), db_session.begin_nested():
        insert_brand(db_session, row)
