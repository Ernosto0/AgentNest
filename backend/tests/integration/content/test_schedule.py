"""P5-04: submitting content with an approver's self-approval (AC-D4) and the submit rules over
the API (G17, G13, deviation notes of api-design.md 2.7)."""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.approvals.models import Approval
from app.audit.models import AuditLog
from app.content.models import ContentItem
from app.content.payload import approval_payload, approval_payload_hash, publish_job_key
from app.core.clock import FrozenClock
from app.core.errors import AppError
from app.jobs.models import Job
from app.knowledge.models import FactReference
from tests.factories import create_fact, money
from tests.helpers.content import (
    connect_account,
    make_item,
    make_media,
    publish_job,
    submittable_item,
)
from tests.helpers.env import Env, Role, build_env

ITEMS = "/content-items"
EVENING = {"local_date": "2026-01-15", "local_time": "19:00"}  # 16:00Z; the clock is 12:00Z


def submit(
    env: Env,
    item: ContentItem,
    schedule: Any = EVENING,
    *,
    role: Role | None = None,
    self_approve: bool = False,
    version: int | None = None,
) -> Any:
    return env.call(
        role or env.owner,
        "POST",
        f"{ITEMS}/{item.id}/submit",
        json={
            "schedule": schedule,
            "self_approve": self_approve,
            "expected_version": version if version is not None else item.version,
        },
    )


def error_codes(response: Any) -> list[str]:
    assert response.status_code == 422, response.text
    assert response.json()["code"] == "CONTENT_VALIDATION_FAILED"
    return [e["code"] for e in response.json()["errors"]]


def jobs_for(env: Env, item: ContentItem) -> list[Job]:
    return list(
        env.session.scalars(select(Job).where(Job.job_type == "publish_content").order_by(Job.id))
    )


def audit(env: Env, action: str) -> list[AuditLog]:
    return list(env.session.scalars(select(AuditLog).where(AuditLog.action == action)))


# --- AC-D4 ----------------------------------------------------------------------------------


@pytest.mark.invariant("INV-16")
def test_ac_d4_an_owner_approving_and_scheduling_19_00_istanbul_gets_16_00_utc(env: Env) -> None:
    account = connect_account(env)
    item = submittable_item(env)

    response = submit(env, item, self_approve=True)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "scheduled" and body["version"] == 1
    scheduled_at = datetime(2026, 1, 15, 16, 0, tzinfo=UTC)
    assert datetime.fromisoformat(body["scheduled_at"]) == scheduled_at
    assert body["schedule_local"] == {
        "date": "2026-01-15",
        "time": "19:00",
        "timezone": "Europe/Istanbul",
    }
    assert body["social_account_id"] == str(account.id)  # set by submit (api-design 2.7)
    assert body["is_simulated"] is True  # copied from the mock account
    env.session.refresh(item)
    assert item.schedule_input is not None and item.schedule_input["local_time"] == "19:00"

    # An approved approval, bound to this version and to the exact payload.
    approval = env.session.get(Approval, item.approval_id)
    assert approval is not None
    assert (approval.status, approval.kind, approval.action) == (
        "approved",
        "authorization",
        "content.publish",
    )
    assert (approval.subject_type, approval.subject_id, approval.subject_version) == (
        "content_item",
        item.id,
        1,
    )
    assert approval.decided_by_user_id == env.owner.user.id and approval.decision_channel == "web"
    expected = approval_payload(
        item,
        version=1,
        social_account_id=account.id,
        media_sha256="a" * 64,
        scheduled_at=scheduled_at,
    )
    assert approval.payload_hash == approval_payload_hash(expected)
    assert approval.expires_at == scheduled_at
    assert approval.execute_before == scheduled_at + timedelta(minutes=1440)  # G16
    assert approval.is_simulated is True
    assert body["approval"]["status"] == "approved" and body["approval"]["subject_version"] == 1

    # One publish job at the scheduled instant, deduplicated per version.
    (job,) = jobs_for(env, item)
    assert job.run_at == scheduled_at and job.status == "queued"
    assert job.dedup_key == publish_job_key(item.id, 1)
    assert job.payload == {"content_id": str(item.id), "version": 1}
    assert job.workspace_id == env.workspace.id

    assert [a.metadata_["event"] for a in audit(env, "content.scheduled")] == ["schedule"]
    assert len(audit(env, "approval.approved")) == 1


def test_publish_now_is_the_current_instant_for_an_approver(env: Env) -> None:
    item = submittable_item(env)
    response = submit(env, item, "now", self_approve=True)
    assert response.status_code == 200, response.text
    assert datetime.fromisoformat(response.json()["scheduled_at"]) == env.clock.now()
    (job,) = jobs_for(env, item)
    assert job.run_at == env.clock.now()


def test_submit_sets_the_account_the_item_has_no_other_way_to_get(env: Env) -> None:
    item = submittable_item(env)
    assert item.social_account_id is None
    assert submit(env, item, self_approve=True).json()["social_account_id"] is not None


def test_a_manager_may_self_approve_too(env: Env) -> None:
    item = submittable_item(env)
    response = submit(env, item, role=env.manager, self_approve=True)
    assert response.status_code == 200 and response.json()["status"] == "scheduled"


@pytest.mark.invariant("INV-04")
def test_self_approve_without_the_permission_is_403_and_nothing_changes(env: Env) -> None:
    item = submittable_item(env)
    response = submit(env, item, role=env.staff, self_approve=True)
    assert response.status_code == 403 and response.json()["code"] == "FORBIDDEN"
    env.session.refresh(item)
    assert (item.status, item.approval_id) == ("draft", None)
    assert jobs_for(env, item) == []
    assert env.session.scalars(select(Approval)).all() == []


def test_without_self_approve_an_owner_goes_through_a_pending_approval_too(env: Env) -> None:
    item = submittable_item(env)
    response = submit(env, item, self_approve=False)
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "pending_approval"
    assert jobs_for(env, item) == []  # nothing is queued before someone approves


# --- the rules ------------------------------------------------------------------------------


def test_nothing_is_changed_when_the_submission_is_refused(env: Env) -> None:
    item = make_item(env, caption=None)  # no media, no caption, no account
    response = submit(env, item, self_approve=True)
    assert error_codes(response) == [
        "CONTENT_MEDIA_REQUIRED",
        "CAPTION_REQUIRED",
        "ACCOUNT_NOT_CONNECTED",
    ]
    env.session.refresh(item)
    assert item.status == "draft" and item.approval_id is None and item.scheduled_at is None
    assert jobs_for(env, item) == [] and env.session.scalars(select(Approval)).all() == []


def test_every_item_comes_with_a_localised_message(env: Env) -> None:
    item = make_item(env, caption=None)
    body = submit(env, item, self_approve=True).json()
    assert all(e["message"] for e in body["errors"])
    assert body["errors"][0]["field"] == "media_asset_id"
    assert body["params"] == {"warnings": []}


def test_no_connected_account_is_account_not_connected(env: Env) -> None:
    media = make_media(env)
    item = make_item(env, caption="Merhaba", media_asset_id=media.id)
    assert error_codes(submit(env, item, self_approve=True)) == ["ACCOUNT_NOT_CONNECTED"]


def test_an_account_that_needs_reauth_is_not_connected(env: Env) -> None:
    connect_account(env, status="needs_reauth")
    item = submittable_item(env)
    assert error_codes(submit(env, item, self_approve=True)) == ["ACCOUNT_NOT_CONNECTED"]


def test_a_missing_capability_is_reported(env: Env) -> None:
    connect_account(env, capabilities={"messaging": True, "publish_story_image": True})
    item = submittable_item(env)
    assert error_codes(submit(env, item, self_approve=True)) == ["CAPABILITY_MISSING"]


def test_a_feed_image_with_the_wrong_ratio_is_refused(env: Env) -> None:
    connect_account(env)
    item = make_item(
        env, caption="Merhaba", media_asset_id=make_media(env, width=1080, height=1920).id
    )
    assert error_codes(submit(env, item, self_approve=True)) == ["ASPECT_RATIO_OUT_OF_RANGE"]


def test_a_story_goes_through_with_a_warning_for_a_non_9_16_image(env: Env) -> None:
    connect_account(env)
    item = make_item(
        env,
        content_type="story_image",
        overlay=["Deneme dersi bizden"],
        media_asset_id=make_media(env, width=1080, height=1350).id,
    )
    body = submit(env, item, self_approve=True).json()
    assert body["status"] == "scheduled"
    assert [w["code"] for w in body["validation"]["warnings"]] == ["STORY_ASPECT_NOT_9_16"]
    assert body["validation"]["errors"] == []


def test_a_story_with_a_caption_is_refused(env: Env) -> None:
    connect_account(env)
    item = make_item(
        env,
        content_type="story_image",
        caption="Görünmeyecek",
        media_asset_id=make_media(env, width=1080, height=1920).id,
    )
    assert error_codes(submit(env, item, self_approve=True)) == ["CAPTION_NOT_ALLOWED"]


def verified_display(env: Env, key: str = "pricing.membership_monthly") -> str:
    from app.knowledge import service as knowledge_service

    (fact,) = [
        f
        for f in knowledge_service.usable_facts(env.session, env.clock, env.ctx(env.owner))
        if f.key == key
    ]
    return fact.display


@pytest.mark.invariant("INV-02")
def test_a_typed_price_equal_to_the_verified_one_is_grounded_and_submits(env: Env) -> None:
    fact = create_fact(env.session, env.workspace, "pricing.membership_monthly", money("6000"))
    connect_account(env)
    item = submittable_item(env, caption=f"Üyelik bu ay {verified_display(env)}")

    # The dry run first: the value is reported, grounded, and not an error.
    check = env.call(env.owner, "POST", f"{ITEMS}/{item.id}/validate").json()
    assert check["passed"] is True and check["errors"] == []
    (issue,) = check["issues"]
    assert issue["matches_verified"] is True and issue["fact_key"] == "pricing.membership_monthly"

    response = submit(env, item, self_approve=True)

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "scheduled"
    # The value is a reference of the item as submitted, so a price change will hold it (P5-07).
    refs = env.session.scalars(
        select(FactReference).where(FactReference.referrer_id == item.id)
    ).all()
    assert [r.fact_id for r in refs] == [fact.id]


@pytest.mark.invariant("INV-02")
def test_a_value_grounded_only_by_submit_time_is_still_a_reference(env: Env) -> None:
    """The caption was written before the price was verified: no reference yet. Submitting
    checks against today's facts and records it, so a later change reaches the scheduled post."""
    connect_account(env)
    item = submittable_item(env, caption="Üyelik bu ay 6.000 ₺ / ay")
    assert submit(env, item, self_approve=True).status_code == 422  # nothing verified yet

    fact = create_fact(env.session, env.workspace, "pricing.membership_monthly", money("6000"))
    assert submit(env, item, self_approve=True).status_code == 200
    refs = env.session.scalars(
        select(FactReference).where(FactReference.referrer_id == item.id)
    ).all()
    assert [r.fact_id for r in refs] == [fact.id]


@pytest.mark.invariant("INV-02")
def test_an_invented_price_blocks_submission(env: Env) -> None:
    create_fact(env.session, env.workspace, "pricing.membership_monthly", money("6000"))
    connect_account(env)
    item = submittable_item(env, caption="Üyelik bu ay sadece 5.000 ₺ / ay!")

    response = submit(env, item, self_approve=True)

    assert error_codes(response) == ["CLAIM_VALIDATION_FAILED"]
    (issue,) = response.json()["errors"][0]["params"]["issues"]
    assert issue["matches_verified"] is False and issue["fact_key"] is None
    assert issue["field"] == "caption"
    check = env.call(env.owner, "POST", f"{ITEMS}/{item.id}/validate").json()
    assert check["passed"] is False
    env.session.refresh(item)
    assert item.status == "draft"


@pytest.mark.invariant("INV-02")
def test_a_part_of_a_verified_price_is_not_the_price(env: Env) -> None:
    """``500 ₺`` is inside ``6.500 ₺``, but it is not that price."""
    create_fact(env.session, env.workspace, "pricing.membership_monthly", money("6500"))
    connect_account(env)
    item = submittable_item(env, caption="Üyelik bu ay 500 ₺ / ay")
    assert error_codes(submit(env, item, self_approve=True)) == ["CLAIM_VALIDATION_FAILED"]


@pytest.mark.invariant("INV-02")
def test_the_old_price_blocks_submission_after_the_fact_changed(env: Env) -> None:
    from app.knowledge import service as knowledge_service

    fact = create_fact(env.session, env.workspace, "pricing.membership_monthly", money("6000"))
    connect_account(env)
    item = submittable_item(env, caption=f"Üyelik bu ay {verified_display(env)}")
    assert env.call(env.owner, "POST", f"{ITEMS}/{item.id}/validate").json()["passed"] is True

    knowledge_service.update_fact(
        env.session,
        env.clock,
        env.ctx(env.owner),
        fact.id,
        expected_version=1,
        value={"amount": "7000.00", "currency": "TRY", "unit": "month"},
    )
    env.session.expire_all()

    response = submit(env, item, self_approve=True)

    assert error_codes(response) == ["CLAIM_VALIDATION_FAILED"]
    (issue,) = response.json()["errors"][0]["params"]["issues"]
    assert issue["matches_verified"] is False and issue["text"].startswith("6.000")


@pytest.mark.invariant("INV-02")
def test_an_unverified_value_in_an_overlay_suggestion_blocks_a_story(env: Env) -> None:
    connect_account(env)
    item = make_item(
        env,
        content_type="story_image",
        overlay=["Deneme dersi bizden", "%40 indirim!"],
        media_asset_id=make_media(env, width=1080, height=1920).id,
    )
    response = submit(env, item, self_approve=True)
    assert error_codes(response) == ["CLAIM_VALIDATION_FAILED"]
    fields = {i["field"] for i in response.json()["errors"][0]["params"]["issues"]}
    assert fields == {"overlay_text_suggestions.1"}


@pytest.mark.invariant("INV-02")
def test_an_unrendered_placeholder_would_be_published_literally_so_it_blocks(env: Env) -> None:
    connect_account(env)
    item = submittable_item(env, caption="Aylık üyelik {{fact:pricing.membership_monthly}}")
    response = submit(env, item, self_approve=True)
    assert error_codes(response) == ["CLAIM_VALIDATION_FAILED"]
    (issue,) = response.json()["errors"][0]["params"]["issues"]
    assert issue["code"] == "PLACEHOLDER_UNRENDERED"
    assert issue["fact_key"] == "pricing.membership_monthly"


def set_daily_limit(env: Env, limit: int) -> None:
    app = env.owner.client.app
    app.state.settings = app.state.settings.model_copy(update={"publish_daily_limit": limit})  # type: ignore[attr-defined]


def test_the_publish_quota_forecast_counts_the_posts_already_scheduled(env: Env) -> None:
    account = connect_account(env)
    set_daily_limit(env, 2)
    for hour in (10, 18):  # two posts already on the account within 24 h of the new one
        make_item(
            env,
            status="scheduled",
            social_account_id=account.id,
            scheduled_at=env.clock.now() + timedelta(hours=hour),
        )
    item = submittable_item(env)
    assert error_codes(submit(env, item, self_approve=True)) == ["PUBLISH_QUOTA_FORECAST_EXCEEDED"]
    # A limit of three leaves room for it.
    set_daily_limit(env, 3)
    assert submit(env, item, self_approve=True).status_code == 200


def test_posts_waiting_for_approval_do_not_use_the_quota(env: Env) -> None:
    account = connect_account(env)
    set_daily_limit(env, 1)
    make_item(
        env,
        status="pending_approval",
        social_account_id=account.id,
        scheduled_at=env.clock.now() + timedelta(hours=4),
    )
    item = submittable_item(env)
    assert submit(env, item, self_approve=True).status_code == 200


# --- the schedule ---------------------------------------------------------------------------


def test_a_time_in_the_past_and_a_time_too_far_ahead_are_refused(env: Env) -> None:
    connect_account(env)
    item = submittable_item(env)
    past = {"local_date": "2026-01-15", "local_time": "10:00"}
    assert error_codes(submit(env, item, past, self_approve=True)) == ["SCHEDULE_IN_PAST"]
    far = {"local_date": "2026-04-01", "local_time": "10:00"}
    assert error_codes(submit(env, item, far, self_approve=True)) == ["SCHEDULE_TOO_FAR"]


def env_on(
    db_session: Session,
    make_client: Callable[[], TestClient],
    clock: FrozenClock,
    *,
    days_ahead: int,
    timezone: str,
) -> Env:
    """A workspace in ``timezone`` whose users sign in ``days_ahead`` days after the usual start
    (a session does not outlive the clock jump if it is created first)."""
    clock.advance(days=days_ahead)
    env = build_env(db_session, make_client, clock)
    env.workspace.timezone = timezone
    db_session.flush()
    return env


@pytest.fixture
def lisbon_spring(
    db_session: Session, make_client: Callable[[], TestClient], clock: FrozenClock
) -> Env:
    return env_on(
        db_session, make_client, clock, days_ahead=410, timezone="Europe/Lisbon"
    )  # 2027-03-01


@pytest.fixture
def lisbon_autumn(
    db_session: Session, make_client: Callable[[], TestClient], clock: FrozenClock
) -> Env:
    return env_on(
        db_session, make_client, clock, days_ahead=280, timezone="Europe/Lisbon"
    )  # 2026-10-22


@pytest.fixture
def istanbul_spring(
    db_session: Session, make_client: Callable[[], TestClient], clock: FrozenClock
) -> Env:
    return env_on(db_session, make_client, clock, days_ahead=410, timezone="Europe/Istanbul")


@pytest.mark.invariant("INV-19")
def test_a_local_time_in_a_dst_gap_is_refused_in_lisbon(lisbon_spring: Env) -> None:
    env = lisbon_spring
    item = submittable_item(env)
    gap = {"local_date": "2027-03-28", "local_time": "01:30"}
    response = submit(env, item, gap, self_approve=True)
    assert error_codes(response) == ["SCHEDULE_TIME_NONEXISTENT"]
    assert response.json()["errors"][0]["params"]["timezone"] == "Europe/Lisbon"
    ok = {"local_date": "2027-03-28", "local_time": "02:00"}  # 01:00Z, the first minute after it
    body = submit(env, item, ok, self_approve=True).json()
    assert datetime.fromisoformat(body["scheduled_at"]) == datetime(2027, 3, 28, 1, 0, tzinfo=UTC)


@pytest.mark.invariant("INV-19")
def test_an_ambiguous_local_time_takes_the_earlier_instant_and_is_echoed(
    lisbon_autumn: Env,
) -> None:
    env = lisbon_autumn
    item = submittable_item(env)
    fold = {"local_date": "2026-10-25", "local_time": "01:30"}
    body = submit(env, item, fold, self_approve=True).json()
    assert datetime.fromisoformat(body["scheduled_at"]) == datetime(2026, 10, 25, 0, 30, tzinfo=UTC)
    assert body["schedule_local"] == {
        "date": "2026-10-25",
        "time": "01:30",
        "timezone": "Europe/Lisbon",
    }
    env.session.refresh(item)
    assert item.schedule_input is not None and item.schedule_input["ambiguous"] is True


@pytest.mark.invariant("INV-19")
def test_istanbul_follows_the_same_rules_without_a_gap(istanbul_spring: Env) -> None:
    env = istanbul_spring
    item = submittable_item(env)
    night = {"local_date": "2027-03-28", "local_time": "01:30"}  # a normal night in Istanbul
    body = submit(env, item, night, self_approve=True).json()
    assert datetime.fromisoformat(body["scheduled_at"]) == datetime(2027, 3, 27, 22, 30, tzinfo=UTC)


@pytest.mark.parametrize(
    "schedule",
    [
        {"local_date": "2026-01-15", "local_time": "25:00"},
        {"local_date": "2026-13-45", "local_time": "10:00"},
        {"local_date": "2026-01-15"},
        "tomorrow",
        "",
        None,
    ],
)
def test_a_malformed_schedule_is_a_plain_validation_error(env: Env, schedule: Any) -> None:
    item = submittable_item(env)
    response = submit(env, item, schedule, self_approve=True)
    assert response.status_code == 422 and response.json()["code"] == "VALIDATION_FAILED"


# --- state and versions ---------------------------------------------------------------------


def test_a_stale_expected_version_is_a_409(env: Env) -> None:
    item = submittable_item(env)
    response = submit(env, item, self_approve=True, version=7)
    assert response.status_code == 409 and response.json()["code"] == "VERSION_CONFLICT"
    assert response.json()["params"] == {"expected": 7, "current": 1}


@pytest.mark.parametrize(
    "status", ["pending_approval", "scheduled", "publishing", "published", "cancelled", "on_hold"]
)
def test_only_a_draft_can_be_submitted(env: Env, status: str) -> None:
    item = submittable_item(env, status=status)
    response = submit(env, item, self_approve=True)
    assert response.status_code == 409 and response.json()["code"] == "CONFLICT_STATE"


def test_an_expired_approval_returns_the_item_to_a_draft_that_can_be_resubmitted(env: Env) -> None:
    item = submittable_item(env)
    assert submit(env, item, role=env.staff).json()["status"] == "pending_approval"
    env.clock.advance(hours=5)  # past 16:00Z
    env.call(env.owner, "GET", "/approvals")  # lazy expiry
    env.session.refresh(item)
    assert item.status == "draft" and item.hold_reason == "APPROVAL_EXPIRED"
    assert item.scheduled_at is None
    again = {"local_date": "2026-01-16", "local_time": "19:00"}
    assert submit(env, item, again, self_approve=True).json()["status"] == "scheduled"


@pytest.mark.invariant("INV-16")
def test_ac_d6_editing_after_scheduling_voids_the_approval_and_the_job(env: Env) -> None:
    item = submittable_item(env)
    assert submit(env, item, self_approve=True).status_code == 200
    (job,) = jobs_for(env, item)
    approval_id = item.approval_id
    assert approval_id is not None

    edited = env.call(
        env.owner,
        "PATCH",
        f"{ITEMS}/{item.id}",
        json={"expected_version": 1, "caption": "Cumartesi görüşürüz"},
    )
    assert edited.json()["status"] == "draft" and edited.json()["version"] == 2
    env.session.refresh(job)
    assert job.status == "cancelled"
    from app.approvals import service as approvals_service

    with pytest.raises(AppError) as error:
        approvals_service.assert_executable(
            env.session, env.clock, env.ctx(env.owner), approval_id, 2
        )
    assert error.value.code == "APPROVAL_STALE"


def test_a_job_of_another_version_does_not_block_the_next_submission(env: Env) -> None:
    item = submittable_item(env)
    publish_job(env, item, status="cancelled")  # what an edit leaves behind for version 1
    assert submit(env, item, self_approve=True).status_code == 200


# --- the dry run ----------------------------------------------------------------------------


def dry_run(env: Env, item: ContentItem, body: Any = None, role: Role | None = None) -> Any:
    return env.call(role or env.owner, "POST", f"{ITEMS}/{item.id}/validate", json=body)


def test_the_dry_run_lists_every_submit_rule_and_changes_nothing(env: Env) -> None:
    item = make_item(env, caption=None)
    before = (item.status, item.version, item.validation, item.approval_id)
    body = dry_run(env, item, {"schedule": "now", "self_approve": True}).json()
    assert [e["code"] for e in body["errors"]] == [
        "CONTENT_MEDIA_REQUIRED",
        "CAPTION_REQUIRED",
        "ACCOUNT_NOT_CONNECTED",
    ]
    assert all(e["message"] for e in body["errors"]) and body["passed"] is True
    env.session.refresh(item)
    assert (item.status, item.version, item.validation, item.approval_id) == before
    assert env.session.scalars(select(Approval)).all() == []


def test_the_dry_run_without_a_schedule_skips_the_schedule_and_quota_rules(env: Env) -> None:
    item = submittable_item(env)
    assert dry_run(env, item).json()["errors"] == []
    staff_now = dry_run(env, item, {"schedule": "now"}, env.staff).json()
    assert [e["code"] for e in staff_now["errors"]] == ["SCHEDULE_TOO_SOON_FOR_APPROVAL"]
    owner_now = dry_run(env, item, {"schedule": "now", "self_approve": True}).json()
    assert owner_now["errors"] == []


def test_the_dry_run_reports_warnings_without_blocking(env: Env) -> None:
    connect_account(env)
    item = make_item(
        env,
        content_type="story_image",
        overlay=["x" * 50],
        media_asset_id=make_media(env, width=1080, height=1350).id,
    )
    body = dry_run(env, item, {"schedule": "now", "self_approve": True}).json()
    assert body["errors"] == []
    assert sorted(w["code"] for w in body["warnings"]) == [
        "OVERLAY_TOO_LONG",
        "STORY_ASPECT_NOT_9_16",
    ]
