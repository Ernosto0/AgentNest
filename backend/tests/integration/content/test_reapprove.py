"""Re-approving an item on hold (plan.md G2): a new version, a new approval, fresh keys, and the
full validation again."""

from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy import select

from app.approvals import service as approvals_service
from app.approvals.models import Approval
from app.content.models import ContentItem
from app.content.payload import approval_payload, approval_payload_hash, publish_job_key
from app.core.errors import AppError
from app.integrations.instagram.models import SocialAccount
from app.jobs.models import Job
from tests.factories import create_fact, money
from tests.helpers.content import (
    make_item,
    publish_job,
    request_approval,
    submittable_item,
)
from tests.helpers.env import Env, Role
from tests.integration.content.test_schedule import ITEMS, error_codes

LATER = {"local_date": "2026-01-15", "local_time": "19:00"}  # 16:00Z


def reapprove(
    env: Env, item: ContentItem, schedule: Any = LATER, *, role: Role | None = None
) -> Any:
    return env.call(
        role or env.owner,
        "POST",
        f"{ITEMS}/{item.id}/reapprove",
        json={"schedule": schedule, "expected_version": item.version},
    )


def held_item(env: Env, **overrides: Any) -> tuple[ContentItem, Job]:
    """What a fact change leaves behind: an on-hold version 1 whose job was cancelled."""
    values = {"status": "on_hold", "hold_reason": "FACT_CHANGED", **overrides}
    item = submittable_item(env, **values)
    job = publish_job(env, item, status="cancelled")
    return item, job


def test_reapproving_increments_the_version_and_uses_fresh_keys(env: Env) -> None:
    item, old_job = held_item(env)
    account_id = connect_account_id(env)

    response = reapprove(env, item)

    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["status"], body["version"]) == ("scheduled", 2)
    assert body["hold_reason"] is None
    assert datetime.fromisoformat(body["scheduled_at"]) == datetime(2026, 1, 15, 16, 0, tzinfo=UTC)
    # The approval is bound to version 2 and to the new payload.
    approval = env.session.get(Approval, item.approval_id)
    assert approval is not None
    assert (approval.status, approval.subject_version) == ("approved", 2)
    expected = approval_payload(
        item,
        version=2,
        social_account_id=account_id,
        media_sha256="a" * 64,
        scheduled_at=datetime(2026, 1, 15, 16, 0, tzinfo=UTC),
    )
    assert approval.payload_hash == approval_payload_hash(expected)
    # A job for version 2; the dead one for version 1 stays dead.
    jobs = {j.dedup_key: j for j in env.session.scalars(select(Job))}
    assert jobs[publish_job_key(item.id, 1)] is old_job and old_job.status == "cancelled"
    new = jobs[publish_job_key(item.id, 2)]
    assert new.status == "queued" and new.run_at == datetime(2026, 1, 15, 16, 0, tzinfo=UTC)
    assert new.payload == {"content_id": str(item.id), "version": 2}


def connect_account_id(env: Env) -> Any:
    return env.session.scalars(select(SocialAccount.id)).one()


@pytest.mark.invariant("INV-16")
def test_the_approval_of_the_old_version_authorises_nothing_for_the_new_one(env: Env) -> None:
    item, _job = held_item(env)
    old = request_approval(env, item)
    old.status = "approved"  # the version-1 approval that was granted before the hold
    env.session.flush()
    assert reapprove(env, item).status_code == 200
    with pytest.raises(AppError) as error:
        approvals_service.assert_executable(env.session, env.clock, env.ctx(env.owner), old.id, 2)
    assert error.value.code == "APPROVAL_STALE"


@pytest.mark.invariant("INV-02")
def test_a_caption_that_still_shows_an_old_price_must_be_edited_first(env: Env) -> None:
    create_fact(env.session, env.workspace, "pricing.membership_monthly", money("7000"))
    item, _job = held_item(env, caption="Aylık üyelik 6.000 ₺")
    response = reapprove(env, item)
    assert error_codes(response) == ["CLAIM_VALIDATION_FAILED"]
    env.session.refresh(item)
    assert (item.status, item.version) == ("on_hold", 1)


def test_the_schedule_rules_apply_again(env: Env) -> None:
    item, _job = held_item(env)
    old_time = {"local_date": "2026-01-15", "local_time": "10:00"}  # the original, now past
    assert error_codes(reapprove(env, item, old_time)) == ["SCHEDULE_IN_PAST"]


def test_reapproving_needs_the_approve_permission_and_an_item_on_hold(env: Env) -> None:
    item, _job = held_item(env)
    assert reapprove(env, item, role=env.staff).status_code == 403
    draft = make_item(env)
    conflict = reapprove(env, draft)
    assert conflict.status_code == 409 and conflict.json()["code"] == "CONFLICT_STATE"
    stale = env.call(
        env.owner,
        "POST",
        f"{ITEMS}/{item.id}/reapprove",
        json={"schedule": LATER, "expected_version": 5},
    )
    assert stale.status_code == 409 and stale.json()["code"] == "VERSION_CONFLICT"


def test_a_hold_for_an_unavailable_account_can_be_reapproved_once_it_is_back(env: Env) -> None:
    item, _job = held_item(env, hold_reason="ACCOUNT_UNAVAILABLE")
    account = env.session.scalars(select(SocialAccount)).one()
    account.status = "needs_reauth"
    env.session.flush()
    assert error_codes(reapprove(env, item)) == ["ACCOUNT_NOT_CONNECTED"]
    account.status = "connected"
    env.session.flush()
    assert reapprove(env, item).json()["status"] == "scheduled"
