"""Database constraints of ``content_items`` (migration 0009, data-model.md 3.6, INV-01)."""

import uuid
from datetime import timedelta

import pytest
from sqlalchemy.exc import IntegrityError

from app.approvals import service as approvals_service
from app.content.models import ContentItem, MediaAsset
from app.integrations.instagram.models import SocialAccount
from tests.factories import knowledge_ctx, workspace_with_members
from tests.helpers.content import make_item
from tests.helpers.env import Env


def foreign_media(env: Env) -> MediaAsset:
    other, users = workspace_with_members(env.session, name="Başka")
    media = MediaAsset(
        workspace_id=other.id,
        storage_backend="local",
        storage_key=f"{other.id}/2026/01/x.jpg",
        mime_type="image/jpeg",
        byte_size=1,
        width=1,
        height=1,
        sha256="0" * 64,
        status="ready",
        created_by_user_id=users["owner"].id,
    )
    env.session.add(media)
    env.session.flush()
    return media


@pytest.mark.invariant("INV-01")
def test_an_item_cannot_point_at_media_of_another_workspace(env: Env) -> None:
    media = foreign_media(env)
    with pytest.raises(IntegrityError), env.session.begin_nested():
        make_item(env, media_asset_id=media.id)


@pytest.mark.invariant("INV-01")
def test_an_item_cannot_point_at_an_account_of_another_workspace(env: Env) -> None:
    other, _users = workspace_with_members(env.session, name="Başka")
    account = SocialAccount(
        workspace_id=other.id,
        provider_kind="mock",
        external_account_id="mock-x",
        username="x",
        status="connected",
    )
    env.session.add(account)
    env.session.flush()
    with pytest.raises(IntegrityError), env.session.begin_nested():
        make_item(env, social_account_id=account.id)


@pytest.mark.invariant("INV-01")
def test_an_item_cannot_point_at_an_approval_of_another_workspace(env: Env) -> None:
    other, users = workspace_with_members(env.session, name="Başka")
    approval = approvals_service.request(
        env.session,
        env.clock,
        knowledge_ctx(other, users["owner"], "owner"),
        kind="authorization",
        action="content.publish",
        subject_type="content_item",
        subject_id=uuid.uuid4(),
        subject_version=1,
        payload={"x": 1},
        summary={},
        required_permission="content.approve",
        expires_at=env.clock.now() + timedelta(hours=1),
    )
    with pytest.raises(IntegrityError), env.session.begin_nested():
        make_item(env, approval_id=approval.id)


def test_status_content_type_and_version_are_constrained(env: Env) -> None:
    for columns in (
        {"status": "done"},
        {"content_type": "video"},
        {"version": 0},
    ):
        with pytest.raises(IntegrityError), env.session.begin_nested():
            make_item(env, **columns)


def test_a_client_request_id_is_unique_per_author_but_not_per_workspace(env: Env) -> None:
    make_item(env, client_request_id="istek")
    make_item(env, owner=env.manager, client_request_id="istek")  # another author: fine
    make_item(env)  # no request id: any number
    make_item(env)
    with pytest.raises(IntegrityError), env.session.begin_nested():
        make_item(env, client_request_id="istek")
    assert env.session.query(ContentItem).count() == 4
