"""Content item builders for tests that need an item in a given status before submission exists."""

import uuid
from datetime import timedelta
from typing import Any

from app.approvals import service as approvals_service
from app.approvals.models import Approval
from app.content.models import ContentItem, MediaAsset
from app.content.payload import publish_job_key
from app.integrations.instagram.models import SocialAccount
from app.jobs.models import Job
from tests.helpers.env import Env, Role

MOCK_CAPABILITIES = {"messaging": True, "publish_feed_image": True, "publish_story_image": True}


def make_item(
    env: Env,
    *,
    status: str = "draft",
    content_type: str = "feed_image",
    title: str = "Haftalık paylaşım",
    caption: str | None = None,
    overlay: list[str] | None = None,
    version: int = 1,
    owner: Role | None = None,
    **columns: Any,
) -> ContentItem:
    """Insert an item directly in ``status`` (the paths to most statuses arrive in later tasks)."""
    now = env.clock.now()
    item = ContentItem(
        workspace_id=env.workspace.id,
        content_type=content_type,
        status=status,
        version=version,
        title=title,
        caption=caption,
        overlay_text_suggestions=overlay or [],
        validation={"passed": True, "issues": [], "stale": False},
        created_by_user_id=(owner or env.owner).user.id,
        created_at=now,
        updated_at=now,
        **columns,
    )
    env.session.add(item)
    env.session.flush()
    return item


def request_approval(env: Env, item: ContentItem, *, requester: Role | None = None) -> Approval:
    """A pending ``content.publish`` approval bound to the item's current version."""
    approval = approvals_service.request(
        env.session,
        env.clock,
        env.ctx(requester or env.staff),
        kind="authorization",
        action="content.publish",
        subject_type="content_item",
        subject_id=item.id,
        subject_version=item.version,
        payload={"content_id": str(item.id), "version": item.version},
        summary={"title": item.title},
        required_permission="content.approve",
        expires_at=env.clock.now() + timedelta(hours=2),
    )
    item.approval_id = approval.id
    env.session.flush()
    return approval


def publish_job(env: Env, item: ContentItem, *, status: str = "queued") -> Job:
    """The waiting ``publish_content`` job of the item's current version."""
    job = Job(
        workspace_id=env.workspace.id,
        job_type="publish_content",
        payload={"content_id": str(item.id), "version": item.version},
        status=status,
        run_at=env.clock.now() + timedelta(hours=1),
        max_attempts=5,
        dedup_key=publish_job_key(item.id, item.version),
    )
    env.session.add(job)
    env.session.flush()
    return job


def connect_account(env: Env, **overrides: Any) -> SocialAccount:
    """The workspace's connected simulated account (all publishing capabilities)."""
    values: dict[str, Any] = {
        "workspace_id": env.workspace.id,
        "platform": "instagram",
        "provider_kind": "mock",
        "external_account_id": "mock-golkent",
        "username": "golkent.demo",
        "status": "connected",
        "capabilities": dict(MOCK_CAPABILITIES),
        "connected_at": env.clock.now(),
    }
    account = SocialAccount(**{**values, **overrides})
    env.session.add(account)
    env.session.flush()
    return account


def make_media(
    env: Env,
    *,
    width: int = 1080,
    height: int = 1350,
    status: str = "ready",
    sha256: str | None = None,
) -> MediaAsset:
    """A ready JPEG asset row (the bytes are not needed until the publish executor)."""
    key = f"{env.workspace.id}/2026/01/{uuid.uuid4().hex}.jpg"
    asset = MediaAsset(
        workspace_id=env.workspace.id,
        storage_backend="local",
        storage_key=key,
        mime_type="image/jpeg",
        byte_size=1000,
        width=width,
        height=height,
        sha256=sha256 or "a" * 64,
        status=status,
        created_by_user_id=env.owner.user.id,
    )
    env.session.add(asset)
    env.session.flush()
    return asset


def submittable_item(env: Env, **overrides: Any) -> ContentItem:
    """A valid feed draft (caption and image) with a connected account in the workspace."""
    if not env.session.query(SocialAccount).filter_by(workspace_id=env.workspace.id).count():
        connect_account(env)
    media = overrides.pop("media", None) or make_media(env)
    values: dict[str, Any] = {
        "caption": "Cuma günü görüşürüz",
        "media_asset_id": media.id,
        **overrides,
    }
    return make_item(env, **values)
