"""Public source API pages use real persisted foreign IDs and membership."""

import uuid

from app.comments.codec import CommentEvent
from app.comments.models import PublicMedia, PublicThread
from app.comments.service import apply
from tests.helpers.env import build_env
from tests.integration.agent.test_comments import event
from tests.integration.agent.test_delegation import _account


def seed(env):
    social, agent = _account(env)
    agent.controller_mode, agent.state = "agent", "active"
    for index in range(3):
        value = event(
            env.clock,
            id=f"root-{index}",
            root_id=f"root-{index}",
            media_id=f"post-{index}",
            media_verified=True,
        )
        apply(env.session, env.clock, social, CommentEvent.model_validate(value))
    env.session.commit()
    return social


def test_api_pagination_permissions_and_foreign_ids(db_session, make_client, clock):
    env = build_env(db_session, make_client, clock)
    social = seed(env)
    base = f"/accounts/{social.id}/comments"
    account_page = env.call(env.staff, "GET", base + "?limit=1").json()
    assert len(account_page["items"]) == 1 and account_page["next_cursor"]
    next_page = env.call(
        env.owner, "GET", base + "?limit=2&cursor=" + account_page["next_cursor"]
    ).json()
    assert len(next_page["items"]) == 2 and next_page["next_cursor"] is None
    comment_id = account_page["items"][0]["id"]
    assert env.call(env.staff, "GET", base + f"/{comment_id}").status_code == 200
    assert env.call(env.staff, "GET", base + f"/{comment_id}/thread").status_code == 200
    assert env.call(env.owner, "GET", base + "?limit=51").status_code == 422
    page = env.call(env.staff, "GET", base + "/media?limit=1")
    assert page.status_code == 200
    data = page.json()
    assert len(data["items"]) == 1 and data["next_cursor"]
    second = env.call(
        env.manager, "GET", base + "/media?limit=2&cursor=" + data["next_cursor"]
    ).json()
    assert len(second["items"]) == 2 and second["next_cursor"] is None
    assert env.call(env.owner, "GET", base + "/media?limit=51").status_code == 422
    media = data["items"][0]
    threads = env.call(env.owner, "GET", base + f"/media/{media['id']}/threads?limit=1").json()
    thread = threads["items"][0]
    comments = env.call(env.owner, "GET", base + f"/threads/{thread['id']}?limit=1").json()
    assert len(comments["items"]) == 1 and comments["next_cursor"] is None
    assert comments["items"][0]["is_simulated"]
    env.workspace.slug = uuid.uuid4().hex
    db_session.flush()
    other = build_env(db_session, make_client, clock)
    foreign_social = seed(other)
    from sqlalchemy import select

    foreign_media = db_session.scalar(
        select(PublicMedia).where(PublicMedia.social_account_id == foreign_social.id)
    )
    foreign_thread = db_session.scalar(
        select(PublicThread).where(PublicThread.social_account_id == foreign_social.id)
    )
    for path in (
        f"?media_id={foreign_media.id}",
        f"/media/{foreign_media.id}",
        f"/media/{foreign_media.id}/threads",
        f"/threads/{foreign_thread.id}",
    ):
        assert env.call(env.owner, "GET", base + path).status_code == 404
    assert (
        env.call(env.owner, "GET", f"/accounts/{foreign_social.id}/comments/media").status_code
        == 404
    )
    assert env.call(env.owner, "GET", base + f"/media/{uuid.uuid4()}").status_code == 404
    from app.integrations.instagram.models import SocialAccount

    sibling = SocialAccount(
        workspace_id=env.workspace.id,
        provider_kind="mock",
        external_account_id=uuid.uuid4().hex,
        status="disconnected",
    )
    db_session.add(sibling)
    db_session.flush()
    sibling_media = PublicMedia(
        workspace_id=env.workspace.id,
        social_account_id=sibling.id,
        external_id="same-workspace-foreign-post",
        updated_at=clock.now(),
        is_simulated=True,
    )
    db_session.add(sibling_media)
    db_session.commit()
    assert env.call(env.owner, "GET", base + f"?media_id={sibling_media.id}").status_code == 404
    assert env.call(env.owner, "GET", base + f"/media/{sibling_media.id}").status_code == 404
