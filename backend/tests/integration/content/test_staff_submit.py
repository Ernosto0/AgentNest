"""AC-D8: a staff member's submission is a pending authorisation that only an approver can decide;
staff cannot "publish now" (plan.md); the approval expires at ``scheduled_at``; the decided
callback (``content/subject.py``) schedules, rejects or returns the item to a draft."""

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import select

from app.approvals.models import Approval
from app.content.models import ContentItem
from app.content.payload import publish_job_key
from app.jobs.models import Job
from app.notifications.models import Notification
from tests.helpers.content import connect_account, make_item, submittable_item
from tests.helpers.env import Env, Role
from tests.integration.content.test_schedule import ITEMS, error_codes, submit

LATER = {"local_date": "2026-01-15", "local_time": "19:00"}  # 16:00Z; the clock is 12:00Z
SCHEDULED_AT = datetime(2026, 1, 15, 16, 0, tzinfo=UTC)


def staff_submit(env: Env, schedule: Any = LATER) -> tuple[ContentItem, Approval]:
    item = submittable_item(env)
    response = submit(env, item, schedule, role=env.staff)
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "pending_approval"
    env.session.refresh(item)
    approval = env.session.get(Approval, item.approval_id)
    assert approval is not None
    return item, approval


def decide(env: Env, role: Role, approval: Approval, decision: str = "approve", **body: Any) -> Any:
    return env.call(
        role,
        "POST",
        f"/approvals/{approval.id}/decision",
        json={"decision": decision, "payload_hash": approval.payload_hash, **body},
    )


def publish_jobs(env: Env) -> list[Job]:
    return list(env.session.scalars(select(Job).where(Job.job_type == "publish_content")))


# --- submitting -----------------------------------------------------------------------------


def test_ac_d8_staff_submission_creates_a_pending_authorisation(env: Env) -> None:
    item, approval = staff_submit(env)
    assert (approval.kind, approval.action, approval.status) == (
        "authorization",
        "content.publish",
        "pending",
    )
    assert approval.required_permission == "content.approve"
    assert (approval.requested_by_actor_type, approval.requested_by_actor_id) == (
        "user",
        str(env.staff.user.id),
    )
    assert approval.subject_version == 1 and approval.decided_by_user_id is None
    # Pending approvals expire when the post would have gone out.
    assert approval.expires_at == SCHEDULED_AT
    assert approval.execute_before == SCHEDULED_AT + timedelta(minutes=1440)
    assert item.scheduled_at == SCHEDULED_AT and item.social_account_id is not None
    assert publish_jobs(env) == []  # nothing runs before somebody approves
    # The approvers are told; the requester is not.
    recipients = {
        n.recipient_user_id
        for n in env.session.scalars(
            select(Notification).where(Notification.type == "approval.requested")
        )
    }
    assert recipients == {env.owner.user.id, env.manager.user.id}


def test_staff_see_where_their_submission_stands(env: Env) -> None:
    item, _approval = staff_submit(env)
    body = env.call(env.staff, "GET", f"{ITEMS}/{item.id}").json()
    assert body["status"] == "pending_approval"
    assert body["approval"]["status"] == "pending" and body["approval"]["subject_version"] == 1


@pytest.mark.invariant("INV-04")
def test_staff_cannot_publish_now(env: Env) -> None:
    item = submittable_item(env)
    now = submit(env, item, "now", role=env.staff)
    assert error_codes(now) == ["SCHEDULE_TOO_SOON_FOR_APPROVAL"]
    assert now.json()["errors"][0]["params"] == {"minutes": 15}
    self_approved = submit(env, item, "now", role=env.staff, self_approve=True)
    assert self_approved.status_code == 403 and self_approved.json()["code"] == "FORBIDDEN"
    env.session.refresh(item)
    assert item.status == "draft"


def test_staff_must_schedule_at_least_15_minutes_ahead(env: Env) -> None:
    item = submittable_item(env)
    too_soon = {"local_date": "2026-01-15", "local_time": "15:14"}  # 12:14Z, 14 min ahead
    assert error_codes(submit(env, item, too_soon, role=env.staff)) == [
        "SCHEDULE_TOO_SOON_FOR_APPROVAL"
    ]
    just_enough = {"local_date": "2026-01-15", "local_time": "15:15"}
    assert submit(env, item, just_enough, role=env.staff).status_code == 200


def test_a_past_time_is_in_the_past_even_for_staff(env: Env) -> None:
    item = submittable_item(env)
    past = {"local_date": "2026-01-15", "local_time": "10:00"}
    assert error_codes(submit(env, item, past, role=env.staff)) == ["SCHEDULE_IN_PAST"]


# --- deciding -------------------------------------------------------------------------------


@pytest.mark.invariant("INV-04")
def test_only_owner_and_manager_can_approve(env: Env) -> None:
    item, approval = staff_submit(env)
    forbidden = decide(env, env.staff, approval)
    assert forbidden.status_code == 403 and forbidden.json()["code"] == "FORBIDDEN"
    env.session.refresh(item)
    assert item.status == "pending_approval" and publish_jobs(env) == []

    approved = decide(env, env.manager, approval, note="tamam")
    assert approved.status_code == 200, approved.text
    env.session.refresh(item)
    env.session.refresh(approval)
    assert (item.status, approval.status) == ("scheduled", "approved")
    assert approval.decided_by_user_id == env.manager.user.id
    (job,) = publish_jobs(env)
    assert job.run_at == SCHEDULED_AT and job.status == "queued"
    assert job.dedup_key == publish_job_key(item.id, 1)
    assert job.payload == {"content_id": str(item.id), "version": 1}


def test_the_owner_can_approve_what_staff_submitted(env: Env) -> None:
    item, approval = staff_submit(env)
    assert decide(env, env.owner, approval).status_code == 200
    env.session.refresh(item)
    assert item.status == "scheduled"
    body = env.call(env.staff, "GET", f"{ITEMS}/{item.id}").json()
    assert body["approval"]["status"] == "approved"
    assert body["approval"]["decided_by_name"] == env.owner.user.display_name


def test_rejecting_keeps_the_note_and_schedules_nothing(env: Env) -> None:
    item, approval = staff_submit(env)
    response = decide(env, env.owner, approval, "reject", note="Fiyat yanlış")
    assert response.status_code == 200, response.text
    env.session.refresh(item)
    assert (item.status, item.rejection_note) == ("rejected", "Fiyat yanlış")
    assert publish_jobs(env) == []
    body = env.call(env.staff, "GET", f"{ITEMS}/{item.id}").json()
    assert body["rejection_note"] == "Fiyat yanlış" and body["approval"]["status"] == "rejected"


@pytest.mark.invariant("INV-16")
def test_a_stale_hash_is_a_409_and_changes_nothing(env: Env) -> None:
    item, approval = staff_submit(env)
    response = env.call(
        env.owner,
        "POST",
        f"/approvals/{approval.id}/decision",
        json={"decision": "approve", "payload_hash": "0" * 64},
    )
    assert response.status_code == 409 and response.json()["code"] == "APPROVAL_STALE"
    env.session.refresh(item)
    env.session.refresh(approval)
    assert (item.status, approval.status) == ("pending_approval", "pending")
    assert publish_jobs(env) == []


@pytest.mark.invariant("INV-16")
def test_the_payload_is_checked_again_when_the_decision_is_taken(env: Env) -> None:
    """Even with the right hash and version, an item whose content no longer matches the payload
    that was approved is not scheduled (and the decision is rolled back)."""
    item, approval = staff_submit(env)
    item.caption = "Başka bir metin"  # changed behind the service's back, version unchanged
    env.session.flush()
    response = decide(env, env.owner, approval)
    assert response.status_code == 409 and response.json()["code"] == "APPROVAL_STALE"
    env.session.refresh(item)
    assert item.status == "pending_approval" and publish_jobs(env) == []


@pytest.mark.invariant("INV-16")
def test_an_item_that_moved_on_makes_the_decision_stale(env: Env) -> None:
    item, approval = staff_submit(env)
    item.status = "draft"  # e.g. withdrawn; the approval was left pending by mistake
    env.session.flush()
    response = decide(env, env.owner, approval)
    assert response.status_code == 409 and response.json()["code"] == "APPROVAL_STALE"
    assert publish_jobs(env) == []


def test_editing_a_pending_item_cancels_its_approval(env: Env) -> None:
    item, approval = staff_submit(env)
    edited = env.call(
        env.staff,
        "PATCH",
        f"{ITEMS}/{item.id}",
        json={"expected_version": 1, "caption": "Cumartesi görüşürüz"},
    )
    assert edited.json()["status"] == "draft"
    response = decide(env, env.owner, approval)
    assert response.status_code == 409 and response.json()["code"] == "APPROVAL_ALREADY_DECIDED"


# --- expiry ---------------------------------------------------------------------------------


def test_a_pending_approval_expires_at_the_scheduled_instant_and_the_item_is_a_draft(
    env: Env,
) -> None:
    item, approval = staff_submit(env)
    env.clock.advance(hours=3, minutes=59)  # 15:59Z
    assert env.call(env.owner, "GET", f"/approvals/{approval.id}").json()["status"] == "pending"
    env.clock.advance(minutes=1)  # 16:00Z
    assert env.call(env.owner, "GET", f"/approvals/{approval.id}").json()["status"] == "expired"

    env.session.refresh(item)
    assert (item.status, item.hold_reason) == ("draft", "APPROVAL_EXPIRED")
    assert item.scheduled_at is None and item.version == 1
    # The requester is told (by the approvals service), the owner can no longer decide.
    told = env.session.scalars(
        select(Notification).where(
            Notification.type == "approval.expired",
            Notification.recipient_user_id == env.staff.user.id,
        )
    ).all()
    assert len(told) == 1
    late = decide(env, env.owner, approval)
    assert late.status_code == 409 and late.json()["code"] == "APPROVAL_EXPIRED"
    assert publish_jobs(env) == []


def test_deciding_after_the_instant_expires_the_approval_and_the_item(env: Env) -> None:
    item, approval = staff_submit(env)
    env.clock.advance(hours=5)
    response = decide(env, env.owner, approval)
    assert response.status_code == 409 and response.json()["code"] == "APPROVAL_EXPIRED"
    env.session.refresh(item)
    assert item.status == "draft" and item.hold_reason == "APPROVAL_EXPIRED"


# --- who can do what ------------------------------------------------------------------------


def test_staff_cannot_cancel_or_reapprove(env: Env) -> None:
    item = make_item(env, status="on_hold", hold_reason="FACT_CHANGED")
    for path, body in (
        ("cancel", None),
        ("reapprove", {"schedule": LATER, "expected_version": 1}),
    ):
        response = env.call(env.staff, "POST", f"{ITEMS}/{item.id}/{path}", json=body)
        assert response.status_code == 403, path


def test_an_account_is_needed_for_the_pending_path_too(env: Env) -> None:
    item = make_item(env, caption="Merhaba")
    connect_account(env, status="disconnected")
    assert error_codes(submit(env, item, role=env.staff)) == [
        "CONTENT_MEDIA_REQUIRED",
        "ACCOUNT_NOT_CONNECTED",
    ]
