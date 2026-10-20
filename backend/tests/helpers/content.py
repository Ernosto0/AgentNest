"""Content item builders for tests that need an item in a given status before submission exists."""

from datetime import timedelta
from typing import Any

from app.approvals import service as approvals_service
from app.approvals.models import Approval
from app.content.models import ContentItem
from app.content.payload import publish_job_key
from app.jobs.models import Job
from tests.helpers.env import Env, Role


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
