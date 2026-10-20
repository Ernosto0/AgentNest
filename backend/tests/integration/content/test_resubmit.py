"""Q4: a rejected or failed item can be sent again after *any* edit, a title or a note included.

The edit is a new version and a draft again (state-machines.md section 5): the old version's
approval, job and operation are spent, so the next submission needs a new approval and a new
``publish:{id}:v{n}`` key (INV-16). ``published`` stays immutable (INV-17)."""

import pytest
from sqlalchemy import select

from app.approvals.models import Approval
from app.audit.models import AuditLog
from app.content.models import ContentItem
from app.content.payload import publish_job_key
from app.jobs.models import Job
from tests.helpers.content import make_item, publish_job, submittable_item
from tests.helpers.env import Env
from tests.integration.content.test_content_items import ITEMS, patch
from tests.integration.content.test_schedule import submit
from tests.integration.content.test_staff_submit import LATER, decide, staff_submit


def approvals_of(env: Env, item: ContentItem) -> list[Approval]:
    return list(
        env.session.scalars(
            select(Approval).where(Approval.subject_id == item.id).order_by(Approval.created_at)
        )
    )


@pytest.mark.parametrize("field", ["title", "visual_notes"])
def test_a_rejected_item_edited_only_in_a_title_or_note_can_be_submitted_again(
    env: Env, field: str
) -> None:
    item, first = staff_submit(env)
    assert decide(env, env.owner, first, "reject", note="Başlığı düzelt").status_code == 200
    env.session.refresh(item)
    assert (item.status, item.version) == ("rejected", 1)

    edited = patch(env, str(item.id), 1, role=env.staff, **{field: "Düzeltilmiş"})

    assert edited.status_code == 200, edited.text
    body = edited.json()
    assert (body["status"], body["version"], body[field]) == ("draft", 2, "Düzeltilmiş")
    assert body["rejection_note"] is None
    # The caption did not change, and neither did what the approver saw.
    env.session.refresh(item)
    assert item.caption == "Cuma günü görüşürüz"

    again = submit(env, item, LATER, role=env.staff, version=2)

    assert again.status_code == 200, again.text
    assert again.json()["status"] == "pending_approval"
    old, new = approvals_of(env, item)
    assert (old.id, old.status, old.subject_version) == (first.id, "rejected", 1)
    assert (new.status, new.subject_version) == ("pending", 2)
    assert (
        new.id != old.id and new.payload_hash != old.payload_hash
    )  # the version is in the payload

    assert decide(env, env.owner, new).status_code == 200
    env.session.refresh(item)
    assert (item.status, item.version) == ("scheduled", 2)
    (job,) = env.session.scalars(select(Job).where(Job.job_type == "publish_content"))
    assert job.dedup_key == publish_job_key(item.id, 2)  # a new job key, never v1's


def test_a_title_only_edit_of_a_failed_item_starts_a_new_version(env: Env) -> None:
    item = submittable_item(env)
    assert submit(env, item, self_approve=True).status_code == 200
    env.session.refresh(item)
    old_job = env.session.scalars(select(Job).where(Job.job_type == "publish_content")).one()
    # The publish ran and failed for good (the executor is not what this test exercises).
    item.status = "failed"
    item.last_error_code = "MEDIA_REJECTED"
    old_job.status = "succeeded"
    env.session.commit()
    old_approval = env.session.get(Approval, item.approval_id)
    assert old_approval is not None and old_approval.status == "approved"

    body = patch(env, str(item.id), 1, title="Yeniden gönderilen").json()

    assert (body["status"], body["version"], body["title"]) == ("draft", 2, "Yeniden gönderilen")
    assert body["last_error_code"] is None and body["scheduled_at"] is None
    env.session.refresh(old_job)
    env.session.refresh(old_approval)
    assert old_job.status == "succeeded" and old_job.dedup_key == publish_job_key(item.id, 1)
    assert old_approval.status == "approved" and old_approval.subject_version == 1

    assert submit(env, item, self_approve=True, version=2).status_code == 200
    env.session.refresh(item)
    assert (item.status, item.version) == ("scheduled", 2)
    keys = {
        j.dedup_key
        for j in env.session.scalars(select(Job).where(Job.job_type == "publish_content"))
    }
    assert keys == {publish_job_key(item.id, 1), publish_job_key(item.id, 2)}
    # The new approval is bound to version 2; the old one authorises nothing for it.
    assert item.approval_id != old_approval.id
    new_approval = env.session.get(Approval, item.approval_id)
    assert new_approval is not None and new_approval.subject_version == 2


@pytest.mark.parametrize("status", ["rejected", "failed"])
def test_an_edit_that_changes_nothing_leaves_a_rejected_or_failed_item_alone(
    env: Env, status: str
) -> None:
    item = make_item(env, status=status, caption="Eski", last_error_code="MEDIA_REJECTED")
    body = patch(env, str(item.id), 1, title=item.title, caption="Eski").json()
    assert (body["status"], body["version"]) == (status, 1)


@pytest.mark.parametrize("status", ["rejected", "failed"])
def test_the_new_version_is_audited_and_the_old_job_is_not_touched(env: Env, status: str) -> None:
    item = make_item(env, status=status, caption="Eski")
    job = publish_job(env, item, status="succeeded")

    patch(env, str(item.id), 1, visual_notes="Yeni not")

    env.session.refresh(job)
    assert job.status == "succeeded"
    (entry,) = env.session.scalars(
        select(AuditLog).where(
            AuditLog.resource_id == item.id, AuditLog.action == "content.updated"
        )
    )
    assert (entry.metadata_["from"], entry.metadata_["event"], entry.metadata_["version"]) == (
        status,
        "edit",
        2,
    )


@pytest.mark.parametrize("status", ["draft", "on_hold", "pending_approval", "scheduled"])
def test_other_statuses_keep_saving_a_title_in_place(env: Env, status: str) -> None:
    """Only a rejected or failed item restarts on a title edit; the others are unchanged."""
    item = make_item(env, status=status, caption="Eski")
    body = patch(env, str(item.id), 1, title="Yeni başlık").json()
    assert (body["status"], body["version"], body["title"]) == (status, 1, "Yeni başlık")


@pytest.mark.invariant("INV-17")
def test_a_published_item_stays_immutable_even_for_a_title(env: Env) -> None:
    item = make_item(env, status="published", caption="Yayında")
    response = patch(env, str(item.id), 1, title="Başka")
    assert response.status_code == 409 and response.json()["code"] == "CONFLICT_STATE"
    got = env.call(env.owner, "GET", f"{ITEMS}/{item.id}").json()
    assert (got["status"], got["version"], got["title"]) == ("published", 1, "Haftalık paylaşım")
