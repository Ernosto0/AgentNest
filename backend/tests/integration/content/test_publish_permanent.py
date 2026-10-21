"""AC-F6: permanent errors are not retried; the dead-job failsafe (plan.md G10)."""

import pytest

from app.content.models import MediaAsset
from app.operations import publish
from tests.helpers.publishing import Publishing


@pytest.mark.invariant("INV-13")
def test_ac_f6_media_rejected_when_creating_the_container_is_not_retried(pub: Publishing) -> None:
    item = pub.scheduled()
    pub.fail("create_container", "invalid_media", remaining=None)

    assert pub.process() == 1
    pub.clock.advance(hours=2)
    assert pub.process() == 0  # no retry job exists

    item = pub.reload(item)
    op = pub.operation(item)
    assert item.status == "failed" and item.last_error_code == "MEDIA_REJECTED"
    assert op is not None and (op.status, op.attempts, op.last_error_code) == (
        "failed",
        1,
        "MEDIA_REJECTED",
    )
    assert [j.status for j in pub.jobs("publish_content")] == ["succeeded"]
    assert pub.containers() == [] and pub.posts() == []
    assert pub.owner_note("content.failed").params["reason"] == "MEDIA_REJECTED"
    assert pub.account_now().status == "connected"  # nothing wrong with the account


def test_a_container_the_provider_failed_to_process_is_media_rejected(pub: Publishing) -> None:
    item = pub.scheduled()
    pub.fail("container_status", "invalid_media")
    outcome = pub.execute(item)
    assert (outcome.kind, outcome.error_code) == ("failed", "MEDIA_REJECTED")
    assert pub.reload(item).status == "failed"
    assert len(pub.containers()) == 1 and pub.posts() == []  # a container, never published
    assert "publish_container" not in pub.calls


def test_a_missing_permission_fails_the_item_and_clears_the_capability(pub: Publishing) -> None:
    item = pub.scheduled("story_image")
    pub.fail("create_container", "permission_missing")
    outcome = pub.execute(item)
    assert (outcome.kind, outcome.error_code) == ("failed", "CAPABILITY_MISSING")
    account = pub.account_now()
    assert account.capabilities["publish_story_image"] is False
    assert account.capabilities["publish_feed_image"] is True and account.status == "connected"
    assert pub.reload(item).last_error_code == "CAPABILITY_MISSING" and pub.posts() == []
    note = pub.owner_note("account.permission_missing")  # the connection managers are told
    assert (note.severity, note.params["capability"]) == ("attention", "publish_story_image")
    assert note.dedup_key == f"account:{account.id}:permission_missing:publish_story_image"


def test_an_image_the_provider_cannot_fetch_is_a_permanent_failure(pub: Publishing) -> None:
    item = pub.scheduled()
    asset = pub.session.get(MediaAsset, pub.reload(item).media_asset_id)
    assert asset is not None
    pub.storage.delete(asset.storage_key)  # the file is gone: the provider cannot fetch it
    outcome = pub.execute(item)
    assert (outcome.kind, outcome.error_code) == ("failed", "MEDIA_REJECTED")
    assert pub.posts() == []


def test_an_unexpected_error_before_anything_visible_is_retried_like_a_transient_one(
    pub: Publishing,
) -> None:
    item = pub.scheduled()

    def boom() -> None:
        raise RuntimeError("a bug in the adapter")

    pub.before["create_media_container"] = boom
    outcome = pub.execute(item)
    assert (outcome.kind, outcome.error_code) == ("retry", "PROVIDER_UNAVAILABLE")
    assert pub.reload(item).status == "retry_scheduled" and pub.posts() == []


# --- the failsafe ----------------------------------------------------------------


def test_a_publish_job_that_dies_before_anything_started_fails_the_item(
    pub: Publishing, monkeypatch: pytest.MonkeyPatch
) -> None:
    item = pub.scheduled()

    def explode(*args: object, **kwargs: object) -> None:
        raise RuntimeError("the executor itself broke")

    monkeypatch.setattr(publish, "execute_publish", explode)
    assert pub.process() == 1

    (job,) = pub.jobs("publish_content")
    assert (job.status, job.last_error_code) == ("dead", "INTERNAL_ERROR")
    row = pub.reload(item)
    assert row.status == "failed" and row.last_error_code == "INTERNAL_ERROR"
    assert pub.owner_note("content.failed").params["reason"] == "INTERNAL_ERROR"
    assert pub.posts() == []


def test_a_publish_job_that_dies_mid_attempt_leaves_the_outcome_to_reconciliation(
    pub: Publishing, monkeypatch: pytest.MonkeyPatch
) -> None:
    """After T1 the provider may already have been called: never fail the item for that."""
    item = pub.scheduled()
    with monkeypatch.context() as patch:

        def explode(*args: object, **kwargs: object) -> None:
            raise RuntimeError("the worker's code broke after T1")

        patch.setattr(publish, "_drive", explode)
        assert pub.process() == 1

    (job,) = pub.jobs("publish_content")
    assert job.status == "dead"
    row = pub.reload(item)
    op = pub.operation(item)
    assert row.status == "publishing" and op is not None and op.status == "outcome_unknown"
    assert pub.notifications("content.failed") == []
    (check,) = pub.jobs("reconcile_publish")
    assert check.status == "queued"

    pub.clock.advance(minutes=1)
    assert pub.process() == 1  # nothing was created: publishing again is safe

    assert pub.reload(item).status == "published"
    assert len(pub.posts()) == 1
