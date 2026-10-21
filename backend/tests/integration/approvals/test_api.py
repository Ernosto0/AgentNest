"""Approvals and notifications over HTTP (api-design.md §2.5, §2.8)."""

import uuid
from datetime import timedelta

import pytest

from app.approvals.models import Approval
from tests.helpers.env import Env
from tests.integration.approvals.conftest import FakeSubject
from tests.integration.approvals.test_approvals import request_approval


def test_detail_shows_the_card_data_and_who_may_decide(env: Env, subject: FakeSubject) -> None:
    approval = request_approval(env, requester=env.staff)
    as_staff = env.call(env.staff, "GET", f"/approvals/{approval.id}").json()
    assert as_staff["id"] == str(approval.id)
    assert as_staff["kind"] == "confirmation" and as_staff["status"] == "pending"
    assert as_staff["summary"]["new_formatted"] == "7.000 ₺"
    assert as_staff["payload_hash"] == approval.payload_hash
    assert as_staff["subject"]["type"] == "owner_command" and as_staff["subject"]["version"] == 1
    assert as_staff["subject"]["status"] == "awaiting"
    assert as_staff["subject"]["link"] == {
        "target": "owner_command",
        "id": str(approval.subject_id),
    }
    assert as_staff["required_permission"] == "knowledge.verify"
    assert as_staff["can_decide"] is True  # the requester of a confirmation
    assert as_staff["is_simulated"] is False

    other_staff_view = env.call(env.owner, "GET", f"/approvals/{approval.id}").json()
    assert other_staff_view["can_decide"] is True  # holds knowledge.verify


def test_can_decide_is_false_without_the_permission_or_after_the_decision(
    env: Env, subject: FakeSubject
) -> None:
    approval = request_approval(env, kind="authorization", requester=env.owner)
    assert env.call(env.staff, "GET", f"/approvals/{approval.id}").json()["can_decide"] is False
    assert env.call(env.manager, "GET", f"/approvals/{approval.id}").json()["can_decide"] is True
    body = {"decision": "approve", "payload_hash": approval.payload_hash}
    env.call(env.manager, "POST", f"/approvals/{approval.id}/decision", json=body)
    assert env.call(env.manager, "GET", f"/approvals/{approval.id}").json()["can_decide"] is False


def test_the_decision_endpoint_approves_with_the_displayed_hash(
    env: Env, subject: FakeSubject
) -> None:
    approval = request_approval(env)
    response = env.call(
        env.owner,
        "POST",
        f"/approvals/{approval.id}/decision",
        json={"decision": "approve", "payload_hash": approval.payload_hash, "note": "ok"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "approved" and body["can_decide"] is False
    assert body["subject"]["status"] == "approved"  # the subject callback ran
    assert subject.decided == [("approved", approval.id)]


@pytest.mark.parametrize(
    ("hash_value", "code", "status"),
    [("0" * 64, "APPROVAL_STALE", 409)],
)
def test_the_decision_endpoint_reports_a_stale_hash_as_409(
    env: Env, subject: FakeSubject, hash_value: str, code: str, status: int
) -> None:
    approval = request_approval(env)
    response = env.call(
        env.owner,
        "POST",
        f"/approvals/{approval.id}/decision",
        json={"decision": "approve", "payload_hash": hash_value},
    )
    assert response.status_code == status and response.json()["code"] == code
    assert subject.decided == []


def test_a_malformed_hash_is_a_validation_error(env: Env, subject: FakeSubject) -> None:
    approval = request_approval(env)
    response = env.call(
        env.owner,
        "POST",
        f"/approvals/{approval.id}/decision",
        json={"decision": "approve", "payload_hash": "not-a-hash"},
    )
    assert response.status_code == 422 and response.json()["code"] == "VALIDATION_FAILED"


def test_only_approve_and_reject_exist_as_decisions(env: Env, subject: FakeSubject) -> None:
    """INV-04: free text such as "ok" or "evet" never approves anything."""
    approval = request_approval(env)
    for word in ("ok", "evet", "tamam", "yes", "approved"):
        response = env.call(
            env.owner,
            "POST",
            f"/approvals/{approval.id}/decision",
            json={"decision": word, "payload_hash": approval.payload_hash},
        )
        assert response.status_code == 422, word
    assert subject.decided == []


def test_a_second_decision_is_409_and_expired_is_409(env: Env, subject: FakeSubject) -> None:
    approval = request_approval(env)
    body = {"decision": "approve", "payload_hash": approval.payload_hash}
    assert (
        env.call(env.owner, "POST", f"/approvals/{approval.id}/decision", json=body).status_code
        == 200
    )
    again = env.call(env.owner, "POST", f"/approvals/{approval.id}/decision", json=body)
    assert (again.status_code, again.json()["code"]) == (409, "APPROVAL_ALREADY_DECIDED")

    late = request_approval(env)
    env.clock.advance(minutes=31)
    response = env.call(
        env.owner,
        "POST",
        f"/approvals/{late.id}/decision",
        json={"decision": "approve", "payload_hash": late.payload_hash},
    )
    assert (response.status_code, response.json()["code"]) == (409, "APPROVAL_EXPIRED")


def test_staff_gets_403_on_an_authorization_and_the_decision_does_not_happen(
    env: Env, subject: FakeSubject
) -> None:
    approval = request_approval(env, kind="authorization", requester=env.owner)
    response = env.call(
        env.staff,
        "POST",
        f"/approvals/{approval.id}/decision",
        json={"decision": "approve", "payload_hash": approval.payload_hash},
    )
    assert response.status_code == 403 and response.json()["code"] == "FORBIDDEN"
    env.session.refresh(approval)
    assert approval.status == "pending"


def test_the_decision_needs_a_session_and_the_csrf_header(env: Env, subject: FakeSubject) -> None:
    approval = request_approval(env)
    url = f"{env.base}/approvals/{approval.id}/decision"
    body = {"decision": "approve", "payload_hash": approval.payload_hash}
    no_csrf = env.owner.client.post(url, json=body)
    assert no_csrf.status_code == 403 and no_csrf.json()["code"] == "CSRF_FAILED"


def test_listing_filters_by_status_and_action_and_expires_lazily(
    env: Env, subject: FakeSubject
) -> None:
    pending = request_approval(env, expires_in=timedelta(minutes=30))
    soon = request_approval(env, expires_in=timedelta(minutes=5))
    env.clock.advance(minutes=10)  # `soon` is due, but no sweep job has run

    listed = env.call(env.owner, "GET", "/approvals?status=pending").json()["items"]
    assert [i["id"] for i in listed] == [str(pending.id)]  # never shows a stale "pending"
    expired = env.call(env.owner, "GET", "/approvals?status=expired").json()["items"]
    assert [i["id"] for i in expired] == [str(soon.id)]
    assert subject.decided == [("expired", soon.id)]

    by_action = env.call(env.owner, "GET", "/approvals?action=command.update_fact").json()["items"]
    assert len(by_action) == 2
    assert env.call(env.owner, "GET", "/approvals?action=reply.send").json()["items"] == []
    assert env.call(env.owner, "GET", "/approvals?status=bogus").status_code == 422


def test_unknown_and_foreign_ids_are_404(env: Env, subject: FakeSubject) -> None:
    assert env.call(env.owner, "GET", f"/approvals/{uuid.uuid4()}").status_code == 404
    body = {"decision": "approve", "payload_hash": "0" * 64}
    gone = env.call(env.owner, "POST", f"/approvals/{uuid.uuid4()}/decision", json=body)
    assert gone.status_code == 404


def test_the_approval_row_is_not_changed_by_reading(env: Env, subject: FakeSubject) -> None:
    approval = request_approval(env)
    before = (approval.status, approval.updated_at)
    env.call(env.owner, "GET", f"/approvals/{approval.id}")
    env.session.refresh(approval)
    assert (approval.status, approval.updated_at) == before
    assert env.session.get(Approval, approval.id) is not None


# --- notifications -------------------------------------------------------------------------


def test_notifications_list_read_and_read_all(env: Env, subject: FakeSubject) -> None:
    first = request_approval(env, kind="authorization", requester=env.staff)
    request_approval(env, kind="authorization", requester=env.staff)

    listing = env.call(env.owner, "GET", "/notifications").json()
    assert listing["unread_count"] == 2 and len(listing["items"]) == 2
    note = listing["items"][0]
    assert note["type"] == "approval.requested" and note["severity"] == "attention"
    assert note["subject_type"] == "approval" and note["read_at"] is None
    assert env.call(env.staff, "GET", "/notifications").json()["items"] == []  # not for staff

    one = next(n for n in listing["items"] if n["subject_id"] == str(first.id))
    read = env.call(env.owner, "POST", f"/notifications/{one['id']}/read")
    assert read.status_code == 200 and read.json()["read_at"] is not None
    assert env.call(env.owner, "GET", "/notifications?unread=true").json()["unread_count"] == 1
    # reading twice is harmless
    assert env.call(env.owner, "POST", f"/notifications/{one['id']}/read").status_code == 200

    assert env.call(env.owner, "POST", "/notifications/read-all").status_code == 204
    after = env.call(env.owner, "GET", "/notifications?unread=true").json()
    assert after["items"] == [] and after["unread_count"] == 0


def test_a_user_cannot_read_someone_elses_notification(env: Env, subject: FakeSubject) -> None:
    request_approval(env, kind="authorization", requester=env.staff)
    owner_note = env.call(env.owner, "GET", "/notifications").json()["items"][0]
    stolen = env.call(env.manager, "POST", f"/notifications/{owner_note['id']}/read")
    assert stolen.status_code == 404  # the manager has their own copy, not the owner's
    still = env.call(env.owner, "GET", "/notifications").json()["items"][0]
    assert still["read_at"] is None


def test_an_unread_notification_is_not_duplicated_but_a_read_one_may_repeat(
    env: Env, subject: FakeSubject
) -> None:
    from app.notifications import service as notifications

    ctx = env.ctx(env.owner)
    kwargs = {"recipient_user_id": env.owner.user.id, "type": "approval.expired", "dedup_key": "k"}
    assert notifications.notify(env.session, env.clock, ctx, **kwargs) is not None  # type: ignore[arg-type]
    assert notifications.notify(env.session, env.clock, ctx, **kwargs) is None  # type: ignore[arg-type]
    first = notifications.list_notifications(env.session, ctx, env.owner.user.id)[0]
    notifications.mark_read(env.session, env.clock, ctx, env.owner.user.id, first.id)
    assert notifications.notify(env.session, env.clock, ctx, **kwargs) is not None  # type: ignore[arg-type]
