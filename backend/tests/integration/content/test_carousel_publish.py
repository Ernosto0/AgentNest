"""Offline carousel ledger evidence, including partial retries and ambiguous outcomes."""

from datetime import timedelta

import pytest

from app.integrations.instagram.base import ContainerStatus
from app.integrations.instagram.errors import ProviderOutcomeUnknown
from app.operations import publish
from tests.helpers.publishing import Crash


def retry(pub, item, outcome):
    assert outcome.kind == "retry"
    pub.clock.advance(seconds=outcome.retry_after_seconds)
    return pub.execute(item)


def assert_published(pub, item, count=4):
    assert pub.reload(item).status == "published"
    op = pub.operation(item)
    assert op.status == "succeeded"
    assert len(pub.posts()) == 1
    containers = pub.containers()
    assert len(containers) == count
    parent = next(c for c in containers if c.container_id == op.provider_ref["container_id"])
    assert parent.media_type == "CAROUSEL"
    assert parent.children == [c["container_id"] for c in op.provider_ref["children"]]
    assert len(parent.children) == 3
    assert (
        pub.provider.get_publishing_quota(publish.account_ref(pub.account, pub.settings)).used == 1
    )


def test_happy_path_order_and_quota(pub):
    item = pub.carousel()
    assert pub.execute(item).kind == "published"
    assert_published(pub, item)
    assert (
        pub.calls[:9]
        == ["get_publishing_quota"] + ["create_media_container", "get_container_status"] * 4
    )
    assert pub.calls.count("publish_container") == 1
    from app.content.carousel import ordered_assets
    from app.integrations.storage.local import parse_local_url

    plan = ordered_assets(pub.session, pub.ctx, item)
    stored = pub.operation(item).provider_ref["children"]
    assert [c["media_asset_id"] for c in stored] == [str(a.id) for a in plan]
    containers = {c.container_id: c for c in pub.containers()}
    assert [parse_local_url(containers[c["container_id"]].media_url)[0] for c in stored] == [
        a.storage_key for a in plan
    ]


@pytest.mark.parametrize(
    ("step", "skip"),
    [
        ("create_carousel_item", 0),
        ("create_carousel_item", 1),
        ("create_carousel_item", 2),
        ("create_carousel_container", 0),
        ("container_status", 0),
        ("container_status", 3),
        ("publish", 0),
    ],
)
@pytest.mark.parametrize("mode", ["transient", "rate_limited"])
def test_partial_failure_resumes_committed_ids(pub, step, skip, mode):
    item = pub.carousel()
    pub.fail(step, mode, skip_first=skip)
    outcome = pub.execute(item)
    stored = {c.container_id for c in pub.containers()}
    assert retry(pub, item, outcome).kind == "published"
    assert stored <= {c.container_id for c in pub.containers()}
    assert_published(pub, item)


@pytest.mark.parametrize("step", ["create_carousel_item", "create_carousel_container"])
def test_lost_creation_answer_only_orphans_unpublished_container(pub, step):
    item = pub.carousel()
    pub.fail(step, "timeout_after_success")
    assert retry(pub, item, pub.execute(item)).kind == "published"
    assert_published(pub, item, count=5)


def test_ambiguous_publish_reconciles_without_second_publish(pub):
    item = pub.carousel()
    pub.fail("publish", "timeout_after_success")
    assert pub.execute(item).kind == "unknown"
    op = pub.operation(item)
    assert op.status == "outcome_unknown"
    assert pub.reconcile(op).kind == "published"
    assert pub.calls.count("publish_container") == 1
    assert_published(pub, item)


def test_ambiguous_without_effect_reads_finished_before_publishing(pub):
    item = pub.carousel()

    def lost():
        raise ProviderOutcomeUnknown()

    pub.before["publish_container"] = lost
    assert pub.execute(item).kind == "unknown"
    assert pub.posts() == []
    assert pub.reconcile(pub.operation(item)).kind == "published"
    assert_published(pub, item)


@pytest.mark.parametrize("step", ["create_carousel_item", "container_status"])
def test_invalid_child_stops_before_parent(pub, step):
    item = pub.carousel()
    pub.fail(step, "invalid_media", skip_first=1)
    assert pub.execute(item).error_code == "MEDIA_REJECTED"
    assert pub.reload(item).status == "failed"
    assert all(c.media_type == "IMAGE" for c in pub.containers())
    assert pub.posts() == []


@pytest.mark.parametrize("after", [1, 2, 3, 4])
def test_crash_after_each_committed_id_resumes(pub, after):
    item = pub.carousel()
    original = pub.provider.get_container_status
    reads = 0

    def status(*args):
        nonlocal reads
        reads += 1
        if reads == after:
            raise Crash()
        return original(*args)

    pub.provider.get_container_status = status
    with pytest.raises(Crash):
        pub.execute(item)
    stored = {c.container_id for c in pub.containers()}
    with pub.factory() as db:
        ctx, row, op, _ = publish._locked(db, _prepared_for_test(pub, item))
        publish.mark_unknown(db, pub.clock, ctx, row, op)
        db.commit()
    assert pub.reconcile(pub.operation(item)).kind == "published"
    assert stored <= {c.container_id for c in pub.containers()}
    assert_published(pub, item)


def _prepared_for_test(pub, item):
    op = pub.operation(item)
    return publish._Prepared(
        pub.workspace.id,
        item.id,
        op.id,
        publish.account_ref(pub.account, pub.settings),
        "mock",
        "feed_carousel",
        item.caption,
        "",
        None,
    )


@pytest.mark.parametrize("expired", ["child", "parent"])
def test_only_expired_container_is_recreated(pub, expired):
    item = pub.carousel()
    pub.fail("create_carousel_container" if expired == "child" else "publish", "transient")
    first = pub.execute(item)
    containers = pub.containers()
    target = (
        containers[0]
        if expired == "child"
        else next(c for c in containers if c.media_type == "CAROUSEL")
    )
    target.expires_at = pub.clock.now() - timedelta(seconds=1)
    pub.session.commit()
    assert retry(pub, item, first).kind == "published"
    assert_published(pub, item, count=5)


def test_shared_child_poll_budget_timeout_resumes(pub, monkeypatch):
    item = pub.carousel()
    original = pub.provider.get_container_status
    monkeypatch.setattr(
        pub.provider, "get_container_status", lambda *_: ContainerStatus("IN_PROGRESS")
    )
    assert pub.execute(item).kind == "unknown"
    assert sum(pub.sleeps) == publish.POLL_TIMEOUT.total_seconds()
    monkeypatch.setattr(pub.provider, "get_container_status", original)
    assert pub.reconcile(pub.operation(item)).kind == "published"
    assert_published(pub, item)


@pytest.mark.parametrize("state", ["deleted", "uploaded", "rejected"])
def test_media_deleted_before_due_refused(pub, state):
    item = pub.carousel()
    from app.content.carousel import ordered_assets

    asset = ordered_assets(pub.session, pub.ctx, item)[0]
    asset.status = state
    pub.session.commit()
    assert pub.execute(item).error_code == "MEDIA_REJECTED"
    assert pub.calls == []


def test_quota_preflight_counts_carousel_once(make_pub):
    pub = make_pub(publish_daily_limit=1)
    first = pub.carousel()
    assert pub.execute(first).kind == "published"
    pub.clock.advance(hours=20)
    second = pub.carousel()
    pub.calls.clear()
    assert pub.execute(second).kind == "rescheduled"
    assert pub.calls == ["get_publishing_quota"]
    assert len(pub.containers()) == 4 and len(pub.posts()) == 1


def test_recreation_cap_is_total_across_children(pub, monkeypatch):
    item = pub.carousel()
    monkeypatch.setattr(pub.provider, "get_container_status", lambda *_: ContainerStatus("EXPIRED"))
    assert pub.execute(item).kind == "retry"
    assert len(pub.containers()) == publish.MAX_CONTAINER_RECREATIONS + 1
    assert pub.posts() == []


def test_children_share_budget_but_parent_gets_fresh_budget(make_pub):
    pub = make_pub(sim_container_delay_seconds=80)
    item = pub.carousel()
    assert pub.execute(item).kind == "published"
    assert sum(pub.sleeps) == 320
    assert_published(pub, item)


def test_later_child_does_not_get_its_own_five_minutes(make_pub):
    pub = make_pub(sim_container_delay_seconds=200)
    item = pub.carousel()
    assert pub.execute(item).kind == "unknown"
    assert sum(pub.sleeps) == 300 and len(pub.containers()) == 2
    assert pub.reconcile(pub.operation(item)).kind == "published"
    assert_published(pub, item)


def test_missing_stored_child_is_the_only_child_recreated(pub):
    from sqlalchemy import delete

    from app.integrations.instagram.models import SimContainer

    item = pub.carousel()
    pub.fail("create_carousel_container", "transient")
    first = pub.execute(item)
    stored = pub.operation(item).provider_ref["children"]
    pub.session.execute(
        delete(SimContainer).where(SimContainer.container_id == stored[1]["container_id"])
    )
    pub.session.commit()
    assert retry(pub, item, first).kind == "published"
    final = pub.operation(item).provider_ref["children"]
    assert stored[0] == final[0] and stored[2] == final[2] and stored[1] != final[1]
    assert_published(pub, item)


def test_published_child_is_rejected_without_a_parent(pub, monkeypatch):
    item = pub.carousel()
    monkeypatch.setattr(
        pub.provider,
        "get_container_status",
        lambda *_: ContainerStatus("PUBLISHED", media_id="impossible-child-media"),
    )
    assert pub.execute(item).error_code == "PROVIDER_REJECTED"
    assert len(pub.containers()) == 1 and pub.posts() == []
