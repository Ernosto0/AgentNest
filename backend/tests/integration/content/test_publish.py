"""P5-06: the publish executor (workflows.md section E step 6, plan.md G1, G8, G9, G14).

AC-D5 and the due-time rules. Every test counts what the simulated Instagram really holds
(``pub.posts()``): INV-06 is about posts, not about rows of ours."""

from datetime import date, timedelta
from typing import Any

import pytest

from app.approvals.models import Approval
from app.content.payload import publish_job_key
from app.content.service import ScheduleRequest
from app.operations import publish
from tests.helpers.env import Env
from tests.helpers.publishing import Publishing

ITEMS = "/content-items"
EVENING = ScheduleRequest(local_date=date(2026, 1, 15), local_time="19:00")


# --- AC-D5 ----------------------------------------------------------------------------------


@pytest.mark.invariant("INV-06")
def test_ac_d5_advancing_the_clock_past_scheduled_at_publishes_the_item_once(
    pub: Publishing,
) -> None:
    item = pub.schedule(pub.draft(), EVENING)  # 19:00 Istanbul = 16:00Z; the clock is 12:00Z
    assert item.scheduled_at == pub.at(16)

    assert pub.process() == 0  # not due yet
    assert pub.posts() == []

    pub.advance_to(pub.at(16))
    assert pub.process() == 1

    item = pub.reload(item)
    (post,) = pub.posts()
    assert item.status == "published"
    assert item.external_media_id == post.media_id and post.media_id.startswith("mock-media-")
    assert (
        item.external_permalink
        == post.permalink
        == f"https://instagram.example/sim/{post.media_id}"
    )
    assert item.published_at == pub.clock.now() == post.published_at
    assert item.last_error_code is None and item.hold_reason is None
    op = pub.operation(item)
    assert op is not None
    assert (op.status, op.attempts, op.operation_type) == ("succeeded", 1, "publish_content")
    assert op.idempotency_key == publish_job_key(item.id, 1)
    assert op.is_simulated is True and op.completed_at == pub.clock.now()
    assert op.provider_ref["container_id"] == post.container_id
    assert op.result["media_id"] == post.media_id
    assert pub.account_now().consecutive_failures == 0
    assert [j.status for j in pub.jobs("publish_content")] == ["succeeded"]

    note = pub.owner_note("content.published")
    assert note.recipient_user_id == pub.owner.id and note.severity == "info"
    assert note.is_simulated is True and "Cuma" not in str(note.params)  # never the caption
    assert [e.metadata_["event"] for e in pub.audits("content.published")] == ["succeed"]
    assert len(pub.audits("content.publishing")) == 1


@pytest.mark.invariant("INV-06")
def test_a_story_is_published_without_a_caption(pub: Publishing) -> None:
    item = pub.scheduled("story_image")
    pub.execute(item)
    assert pub.reload(item).status == "published"
    (container,) = pub.containers()
    assert container.media_type == "STORIES" and container.caption is None
    assert len(pub.posts()) == 1


@pytest.mark.invariant("INV-06")
def test_a_feed_post_is_published_with_its_caption(pub: Publishing) -> None:
    item = pub.scheduled()
    pub.execute(item)
    (container,) = pub.containers()
    assert container.media_type == "IMAGE" and container.caption == "Cuma günü görüşürüz"
    assert len(pub.posts()) == 1


@pytest.mark.invariant("INV-06")
def test_running_the_same_publish_again_publishes_nothing_more(pub: Publishing) -> None:
    item = pub.scheduled()
    assert pub.execute(item).kind == "published"
    pub.calls.clear()
    for _ in range(3):  # a duplicated or re-delivered job
        outcome = pub.execute(item)
        assert outcome.kind == "skipped" and outcome.detail == "already_published:published"
    assert pub.calls == []  # not even a quota read
    assert len(pub.posts()) == 1 and len(pub.containers()) == 1


# --- polling (G9) ------------------------------------------------------------------------------


@pytest.mark.invariant("INV-05")
def test_polling_uses_the_injected_sleeper_and_clock_with_no_transaction_open(
    make_pub: Any,
) -> None:
    pub: Publishing = make_pub(sim_container_delay_seconds=25)
    item = pub.scheduled()
    beats: list[int] = []

    outcome = pub.execute(item, heartbeats=beats)

    assert outcome.kind == "published"
    assert pub.sleeps == [10, 10, 10]  # IN_PROGRESS at 0, 10, 20 s; FINISHED at 30 s
    assert len(beats) == 3  # one heartbeat after each wait
    assert pub.calls == [
        "get_publishing_quota",
        "create_media_container",
        "get_container_status",
        "get_container_status",
        "get_container_status",
        "get_container_status",
        "publish_container",
        "get_media",
    ]
    # Every provider call, sleep and heartbeat asserted `open_transactions() == 0` itself.
    assert len(pub.posts()) == 1


@pytest.mark.invariant("INV-05")
def test_polling_that_never_finishes_hands_over_to_reconciliation(make_pub: Any) -> None:
    pub: Publishing = make_pub(sim_container_delay_seconds=3600)
    item = pub.scheduled()

    outcome = pub.execute(item)

    assert outcome.kind == "unknown"
    assert len(pub.sleeps) == 30 and sum(pub.sleeps) == 300  # 5 minutes, every 10 s
    item = pub.reload(item)
    op = pub.operation(item)
    assert op is not None and item.status == "publishing" and op.status == "outcome_unknown"
    (job,) = pub.jobs("reconcile_publish")
    assert job.status == "queued" and job.run_at == pub.clock.now() + timedelta(minutes=1)
    assert pub.posts() == []  # nothing was published, and nothing will be until it is FINISHED


# --- due-time checks ---------------------------------------------------------------


@pytest.mark.invariant("INV-04")
def test_an_item_that_is_no_longer_scheduled_is_not_published(pub: Publishing, env: Env) -> None:
    item = pub.scheduled()
    assert env.call(env.owner, "POST", f"{ITEMS}/{item.id}/cancel").status_code == 200
    outcome = pub.execute(item)
    assert outcome.kind == "skipped" and outcome.detail == "not_due:cancelled"
    assert pub.calls == [] and pub.posts() == []


@pytest.mark.invariant("INV-16")
def test_a_job_of_an_old_version_publishes_nothing_after_an_edit(pub: Publishing, env: Env) -> None:
    item = pub.scheduled()
    edit = env.call(
        env.owner, "PATCH", f"{ITEMS}/{item.id}", json={"expected_version": 1, "caption": "Yeni"}
    )
    assert edit.status_code == 200 and edit.json()["status"] == "draft"
    approval = pub.session.get(Approval, pub.reload(item).approval_id)
    assert approval is not None and approval.status == "approved"  # stays approved, bound to v1

    outcome = pub.execute(item, version=1)  # a job that was already running when the edit came

    assert outcome.kind == "skipped" and outcome.detail == "not_due:draft"
    assert pub.calls == [] and pub.posts() == []
    assert pub.reload(item).status == "draft"


@pytest.mark.invariant("INV-16")
def test_a_job_of_an_old_version_publishes_nothing_while_a_newer_version_is_scheduled(
    pub: Publishing, env: Env
) -> None:
    """T1 compares the version itself: the item is ``scheduled`` again (as version 2), so the
    status alone would let the stale version-1 job through (AC-D6, INV-16)."""
    item = pub.scheduled()
    edit = env.call(
        env.owner, "PATCH", f"{ITEMS}/{item.id}", json={"expected_version": 1, "caption": "Yeni"}
    )
    assert edit.status_code == 200 and edit.json()["version"] == 2
    resubmitted = pub.schedule(pub.reload(item))
    assert (resubmitted.status, resubmitted.version) == ("scheduled", 2)
    pub.calls.clear()

    stale = pub.execute(item, version=1)

    assert stale.kind == "skipped" and stale.detail == "not_due:scheduled"
    assert pub.calls == [] and pub.posts() == [] and pub.containers() == []
    assert pub.operation(item, version=1) is None  # the stale run left no ledger row
    assert pub.reload(item).status == "scheduled"  # version 2 is untouched and still due

    assert pub.execute(pub.reload(item)).kind == "published"  # the current version goes out
    op = pub.operation(item, version=2)
    assert op is not None and op.status == "succeeded"
    assert len(pub.posts()) == 1


@pytest.mark.invariant("INV-16")
def test_an_approval_whose_payload_no_longer_matches_is_refused(pub: Publishing) -> None:
    item = pub.scheduled()
    row = pub.reload(item)
    row.caption = "Aylık üyelik indirimli"  # changed behind the version's back
    pub.session.commit()

    outcome = pub.execute(item)

    assert (outcome.kind, outcome.error_code) == ("failed", "APPROVAL_STALE")
    assert "create_media_container" not in pub.calls
    assert pub.reload(item).status == "failed" and pub.posts() == []


def test_a_deadline_that_has_passed_fails_the_item_without_publishing(pub: Publishing) -> None:
    item = pub.scheduled()
    pub.clock.advance(minutes=361)  # publish_max_delay_minutes is 360

    outcome = pub.execute(item)

    assert (outcome.kind, outcome.error_code) == ("failed", "PUBLISH_DEADLINE_PASSED")
    item = pub.reload(item)
    assert item.status == "failed" and item.last_error_code == "PUBLISH_DEADLINE_PASSED"
    assert pub.calls == ["get_publishing_quota"]  # a read; no container, no operation
    assert pub.operation(item) is None
    assert pub.posts() == []
    note = pub.owner_note("content.failed")
    assert note.params["reason"] == "PUBLISH_DEADLINE_PASSED"
    # scheduled -> publishing -> failed, both audited (the table has no scheduled -> failed)
    assert [e.metadata_["from"] for e in pub.audits("content.failed")] == ["publishing"]
    assert len(pub.audits("content.publishing")) == 1


def test_an_account_that_needs_reauth_at_due_time_puts_the_item_on_hold(pub: Publishing) -> None:
    item = pub.scheduled()
    account = pub.account_now()
    account.status = "needs_reauth"
    pub.session.commit()

    outcome = pub.execute(item)

    assert (outcome.kind, outcome.error_code) == ("held", "ACCOUNT_UNAVAILABLE")
    item = pub.reload(item)
    assert (item.status, item.hold_reason) == ("on_hold", "ACCOUNT_UNAVAILABLE")
    assert pub.calls == [] and pub.posts() == []
    note = pub.owner_note("content.on_hold")
    assert note.params["reason"] == "ACCOUNT_UNAVAILABLE"


def test_a_missing_capability_at_due_time_puts_the_item_on_hold(pub: Publishing) -> None:
    item = pub.scheduled("story_image")
    account = pub.account_now()
    account.capabilities = {**account.capabilities, "publish_story_image": False}
    pub.session.commit()
    assert pub.execute(item).kind == "held"
    assert pub.reload(item).status == "on_hold" and pub.posts() == []


@pytest.mark.invariant("INV-13")
def test_auth_revoked_at_due_time_puts_the_item_on_hold_and_flags_the_account(
    pub: Publishing,
) -> None:
    item = pub.scheduled()
    pub.fail("create_container", "auth_revoked")

    outcome = pub.execute(item)

    assert (outcome.kind, outcome.error_code) == ("held", "ACCOUNT_NEEDS_REAUTH")
    item = pub.reload(item)
    assert (item.status, item.hold_reason) == ("on_hold", "ACCOUNT_UNAVAILABLE")
    op = pub.operation(item)
    assert op is not None and (op.status, op.last_error_code) == ("failed", "ACCOUNT_NEEDS_REAUTH")
    assert pub.account_now().status == "needs_reauth"
    assert pub.owner_note("content.on_hold").params["reason"] == "ACCOUNT_UNAVAILABLE"
    assert pub.owner_note("account.needs_reauth").severity == "critical"
    assert pub.posts() == []
    assert len(pub.audits("content.on_hold")) == 1


def test_after_reconnecting_the_owner_reapproves_and_it_publishes_once(
    pub: Publishing, env: Env
) -> None:
    item = pub.scheduled()
    pub.fail("create_container", "auth_revoked")
    pub.execute(item)
    account = pub.account_now()
    account.status = "connected"  # the reconnection (the reconnect route is tested elsewhere)
    pub.session.commit()
    # `on_hold` is not resumed by itself (workflows G.2): the owner re-approves for a new instant.
    response = env.call(
        env.owner,
        "POST",
        f"{ITEMS}/{item.id}/reapprove",
        json={"schedule": "now", "expected_version": 1},
    )
    assert response.status_code == 200, response.text
    assert response.json()["version"] == 2

    pub.process()  # the job of v1 finds a newer version and does nothing; the job of v2 publishes
    item = pub.reload(item)
    assert item.status == "published" and item.version == 2
    assert pub.operation(item, 1).status == "failed"  # type: ignore[union-attr]
    assert pub.operation(item, 2).status == "succeeded"  # type: ignore[union-attr]
    assert len(pub.posts()) == 1


# --- the ledger -----------------------------------------------------------------------------------


@pytest.mark.invariant("INV-05")
def test_an_operation_that_already_succeeded_repairs_the_item_without_publishing(
    pub: Publishing,
) -> None:
    item = pub.scheduled()
    pub.execute(item)
    published = pub.reload(item)
    op = pub.operation(item)
    assert op is not None
    # A state a crash could never produce today (T3 is one transaction), but the ledger rules.
    published.status = "scheduled"
    published.published_at = published.external_media_id = published.external_permalink = None
    pub.session.commit()
    pub.calls.clear()

    outcome = pub.execute(item)

    assert (outcome.kind, outcome.detail) == ("published", "repaired")
    repaired = pub.reload(item)
    assert repaired.status == "published" and repaired.external_media_id == op.result["media_id"]
    assert "publish_container" not in pub.calls and len(pub.posts()) == 1


def test_cancelling_while_the_item_is_publishing_is_a_409_and_it_still_publishes_once(
    make_pub: Any, env: Env
) -> None:
    pub: Publishing = make_pub(sim_container_delay_seconds=15)
    item = pub.scheduled()
    refused: list[Any] = []

    def cancel_midway() -> None:
        refused.append(env.call(env.owner, "POST", f"{ITEMS}/{item.id}/cancel"))

    pub.before["publish_container"] = cancel_midway
    pub.execute(item)

    (response,) = refused
    assert response.status_code == 409 and response.json()["code"] == "CONFLICT_STATE"
    assert pub.reload(item).status == "published"
    assert len(pub.posts()) == 1


def test_the_hooks_show_the_operation_of_the_current_version_in_the_api(
    pub: Publishing, env: Env
) -> None:
    item = pub.scheduled()
    assert env.call(env.owner, "GET", f"{ITEMS}/{item.id}").json()["operation"] is None
    pub.fail("publish", "transient")
    pub.execute(item)
    pub.session.expire_all()
    body = env.call(env.owner, "GET", f"{ITEMS}/{item.id}").json()
    assert body["status"] == "retry_scheduled"
    assert body["operation"]["status"] == "retry_wait" and body["operation"]["attempts"] == 1
    assert body["operation"]["last_error_code"] == "PROVIDER_UNAVAILABLE"
    assert body["operation"]["next_attempt_at"] is not None


# --- quota (G8) ---------------------------------------------------------------------


@pytest.mark.invariant("INV-11")
def test_an_exhausted_quota_reschedules_the_item_for_when_the_oldest_post_leaves_the_window(
    make_pub: Any,
) -> None:
    pub: Publishing = make_pub(publish_daily_limit=1)
    first = pub.scheduled()
    second = pub.draft()
    pub.execute(first)
    first_published_at = pub.clock.now()
    pub.clock.advance(hours=20)  # 4 h to go: inside the 6 h deadline of the next one
    pub.schedule(second)
    second = pub.reload(second)
    pub.calls.clear()

    outcome = pub.execute(second)

    retry_at = first_published_at + timedelta(hours=24)
    assert (outcome.kind, outcome.error_code, outcome.run_at) == (
        "rescheduled",
        "PUBLISH_QUOTA_EXHAUSTED",
        retry_at,
    )
    second = pub.reload(second)
    op = pub.operation(second)
    assert second.status == "retry_scheduled" and op is not None
    assert (op.status, op.attempts, op.next_attempt_at) == ("retry_wait", 0, retry_at)
    assert pub.calls == ["get_publishing_quota"] and len(pub.posts()) == 1  # nothing was tried

    pub.advance_to(retry_at)
    assert pub.execute(second).kind == "published"
    assert pub.reload(second).status == "published"
    assert len(pub.posts()) == 2


def test_a_quota_that_frees_up_after_the_deadline_fails_the_item(make_pub: Any) -> None:
    pub: Publishing = make_pub(publish_daily_limit=1)
    first = pub.scheduled()
    second = pub.scheduled()
    pub.execute(first)
    outcome = pub.execute(second)  # the next slot is 24 h away, the deadline 6 h
    assert (outcome.kind, outcome.error_code) == ("failed", "PUBLISH_DEADLINE_PASSED")
    assert pub.reload(second).status == "failed" and len(pub.posts()) == 1


def test_the_quota_deferral_through_the_job_does_not_spend_an_attempt(make_pub: Any) -> None:
    pub: Publishing = make_pub(publish_daily_limit=1)
    pub.scheduled()
    assert pub.process() == 1  # the first post goes out
    pub.clock.advance(hours=20)
    second = pub.schedule(pub.draft())
    assert pub.process() == 1
    (job,) = [j for j in pub.jobs("publish_content") if j.payload["content_id"] == str(second.id)]
    assert job.status == "queued" and job.attempts == 0  # RescheduleJob gave the attempt back
    assert job.run_at == pub.posts()[0].published_at + timedelta(hours=24)
    assert pub.reload(second).status == "retry_scheduled" and len(pub.posts()) == 1


def test_the_publish_module_exposes_the_documented_numbers() -> None:
    assert publish.PUBLISH_BACKOFF[:4] == (60, 300, 900, 1800)
    assert publish.PUBLISH_MAX_ATTEMPTS == 5
    assert publish.POLL_INTERVAL_SECONDS == 10 and publish.POLL_TIMEOUT.total_seconds() == 300
