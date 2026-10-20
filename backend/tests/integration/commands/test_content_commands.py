"""P5-03b: the content commands (workflows.md §B and §E, agent-runtime.md §3).

``content.create_draft`` (no confirmation), ``content.cancel_scheduled`` (confirmation approval
``command.cancel_content`` bound to ``{content_id, content_version}``), ``query.content_status``
and ``query.explain_failure``. The confirmation is decided like any other, through the approvals
API; execution runs as the human who decided, and a stale item is never cancelled.
"""

import json
from datetime import datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import select

from app.ai.models import AgentRun
from app.approvals.grants import record_policy_grant
from app.approvals.models import Approval
from app.audit.models import AuditLog
from app.content.models import ContentItem
from app.content.payload import generate_job_key, publish_job_key
from app.identity import repository as identity_repo
from app.integrations.instagram.models import SocialAccount
from app.jobs import queue
from app.jobs.models import Job
from app.jobs.worker import execute_job
from app.operations.models import Operation
from tests.factories import create_fact, workspace_with_members
from tests.helpers.content import connect_account, make_item, make_media, publish_job
from tests.integration.commands.conftest import CommandEnv
from tests.integration.commands.conftest import cmd as cmd  # noqa: F401  (fixture)
from tests.integration.commands.conftest import provider as provider  # noqa: F401  (fixture)

# The test clock is 2026-01-15 12:00 UTC = 15:00 in Istanbul (UTC+3): "tomorrow" is the 16th.
TOMORROW_EVENING = datetime(2026, 1, 16, 16, 0).replace(tzinfo=None)
CANCEL = "yarınki postu iptal et"
ITEMS = "/content-items"


def at(cmd: CommandEnv, *, days: int = 1, hour: int = 16) -> datetime:
    base = cmd.env.clock.now().replace(hour=hour, minute=0, second=0, microsecond=0)
    return base + timedelta(days=days)


def post(
    cmd: CommandEnv,
    title: str,
    *,
    status: str = "scheduled",
    kind: str = "feed_image",
    when: datetime | None = None,
    owner: Any = None,
    **columns: Any,
) -> ContentItem:
    """An item as the services leave it: an approved authorization and a queued publish job
    for the scheduled states."""
    env = cmd.env
    updated_at = columns.pop("updated_at", None)
    if env.session.scalars(select(SocialAccount)).first() is None:
        connect_account(env)
    account = env.session.scalars(select(SocialAccount)).one()
    scheduled = status in ("scheduled", "retry_scheduled", "pending_approval", "on_hold")
    item = make_item(
        env,
        status=status,
        content_type=kind,
        title=title,
        caption="Cuma günü görüşürüz" if kind == "feed_image" else None,
        owner=owner,
        media_asset_id=make_media(env).id,
        social_account_id=account.id,
        scheduled_at=(when or at(cmd)) if status != "draft" else None,
        is_simulated=True,
        **columns,
    )
    if updated_at is not None:
        item.updated_at = updated_at
    if scheduled and status != "pending_approval":
        approval = record_policy_grant(
            env.session,
            env.clock,
            env.ctx(env.owner),
            action="content.publish",
            subject_type="content_item",
            subject_id=item.id,
            subject_version=item.version,
            payload={"content_id": str(item.id), "version": item.version},
            summary={"title": item.title},
            required_permission="content.approve",
            expires_at=env.clock.now() + timedelta(days=2),
            self_approved=True,
        )
        item.approval_id = approval.id
    if status in ("scheduled", "retry_scheduled"):
        publish_job(env, item)
    env.session.commit()
    return item


def fresh(cmd: CommandEnv, model: Any, row_id: Any) -> Any:
    cmd.env.session.expire_all()
    return cmd.env.session.get(model, row_id)


def interpret_only(cmd: CommandEnv) -> None:
    """Run the one due job (the interpretation), and nothing it enqueues."""
    job = queue.claim_one(cmd.factory, cmd.env.clock, "test-worker", 60)
    assert job is not None and job.job_type == "interpret_command"
    execute_job(cmd.factory, cmd.env.clock, job, lease_seconds=60)


def jobs_of(cmd: CommandEnv, job_type: str) -> list[Job]:
    cmd.env.session.expire_all()
    return list(cmd.env.session.scalars(select(Job).where(Job.job_type == job_type)))


def audits(cmd: CommandEnv, action: str) -> list[AuditLog]:
    cmd.env.session.expire_all()
    return list(cmd.env.session.scalars(select(AuditLog).where(AuditLog.action == action)))


# --- content.create_draft -------------------------------------------------------------------


def test_the_demo_phrase_creates_a_draft_and_queues_its_generation(cmd: CommandEnv) -> None:
    owner = cmd.env.owner
    submitted = cmd.submit(owner, "Deneme dersi için bir story hazırla")
    interpret_only(cmd)

    command = cmd.get(owner, submitted["id"])
    assert command["status"] == "completed" and command["error_code"] is None
    assert command["command_type"] == "content.create_draft"
    assert command["approval"] is None and command["clarification"] is None  # no confirmation
    result = command["result"]
    assert result["message_key"] == "command.draft_created"
    assert result["params"] == {"title": "Deneme dersi", "content_type": "story_image"}

    item = cmd.env.session.scalars(select(ContentItem)).one()
    assert result["links"] == [{"target": "content", "id": str(item.id)}]
    assert (item.status, item.version, item.content_type) == ("draft", 1, "story_image")
    assert item.objective == "Deneme dersi" and item.created_by_user_id == owner.user.id
    assert item.client_request_id == f"command:{submitted['id']}"
    assert item.caption is None and item.social_account_id is None  # nothing to publish yet

    # The generation is queued, not run: the draft and the job came with the command's commit.
    run = fresh(cmd, AgentRun, item.agent_run_id)
    assert (run.task, run.status) == ("draft_content", "queued")
    (job,) = jobs_of(cmd, "generate_content")
    assert job.status == "queued" and job.dedup_key == generate_job_key(item.id)
    assert job.payload == {"content_id": str(item.id), "version": 1}
    assert [a.action for a in audits(cmd, "content.created")] == ["content.created"]
    (done,) = audits(cmd, "command.executed")
    assert done.metadata_["command_type"] == "content.create_draft"


def test_the_queued_generation_then_fills_the_draft(cmd: CommandEnv) -> None:
    create_fact(
        cmd.env.session,
        cmd.env.workspace,
        "promotion.trial_session",
        {"tr": "İlk deneme seansı ücretsiz.", "en": "The first trial session is free."},
        value_type="localized_text",
        label={"tr": "Deneme seansı", "en": "Trial session"},
        clock=cmd.env.clock,
    )
    cmd.env.session.commit()
    cmd.run(cmd.env.owner, "Deneme dersi için bir story hazırla")
    item = cmd.env.session.scalars(select(ContentItem)).one()
    assert fresh(cmd, AgentRun, item.agent_run_id).status == "succeeded"  # the worker ran it
    item = fresh(cmd, ContentItem, item.id)
    assert item.status == "draft" and item.version == 2 and item.overlay_text_suggestions


def test_an_english_user_gets_an_english_draft_request(cmd: CommandEnv) -> None:
    command = cmd.run(cmd.env.owner, "Write a post for summer memberships")
    assert command["status"] == "completed"
    item = cmd.env.session.scalars(select(ContentItem)).one()
    assert (item.content_type, item.objective) == ("feed_image", "summer memberships")


def test_staff_can_ask_for_a_draft_too(cmd: CommandEnv) -> None:
    command = cmd.run(cmd.env.staff, "Yaz kampanyası için bir post hazırla")
    assert command["status"] == "completed"
    item = cmd.env.session.scalars(select(ContentItem)).one()
    assert item.created_by_user_id == cmd.env.staff.user.id  # a draft needs content.edit only


def test_asking_for_a_draft_never_schedules_or_publishes(cmd: CommandEnv) -> None:
    cmd.run(cmd.env.owner, "Deneme dersi için bir story hazırla ve yayınla")  # publish: unsupported
    assert cmd.env.session.scalars(select(ContentItem)).all() == []
    assert jobs_of(cmd, "publish_content") == []


def test_a_model_proposal_with_no_objective_is_rejected_not_executed(cmd: CommandEnv) -> None:
    cmd.provider.queue(
        "interpret_command",
        {
            "interpretation": {
                "type": "content.create_draft",
                "content_type": "story_image",
                "objective": "   ",
                "notes": None,
            }
        },
    )
    command = cmd.run(cmd.env.owner, "bir story hazırla")
    assert command["status"] == "failed" and command["error_code"] == "VALIDATION_FAILED"
    assert command["result"]["message_key"] == "command.draft_unreadable"
    assert cmd.env.session.scalars(select(ContentItem)).all() == []


# --- content.cancel_scheduled ---------------------------------------------------------------


def ask_cancel(cmd: CommandEnv, who: Any = None, text: str = CANCEL) -> dict[str, Any]:
    return cmd.run(who or cmd.env.owner, text)


def test_cancel_by_command_asks_first_and_changes_nothing(cmd: CommandEnv) -> None:
    item = post(cmd, "Yarınki duyuru")
    command = ask_cancel(cmd)

    assert command["status"] == "awaiting_confirmation"
    assert command["command_type"] == "content.cancel_scheduled"
    card = command["approval"]
    assert card["kind"] == "confirmation" and card["action"] == "command.cancel_content"
    assert card["status"] == "pending" and card["can_decide"] is True
    assert card["summary"] == {
        "label": "Yarınki duyuru",
        "content_type": "feed_image",
        "status": "scheduled",
        "when": "16 Oca 19:00",
        "content_id": str(item.id),
    }
    stored = fresh(cmd, Approval, card["id"])
    assert stored.required_permission == "content.approve"  # who may decide it
    assert stored.subject_type == "owner_command" and stored.subject_version == 1
    item = fresh(cmd, ContentItem, item.id)
    assert (item.status, item.version) == ("scheduled", 1)  # nothing happened yet
    assert [j.status for j in jobs_of(cmd, "publish_content")] == ["queued"]


def test_confirming_cancels_the_post_its_job_and_its_waiting_operation(cmd: CommandEnv) -> None:
    owner, manager = cmd.env.owner, cmd.env.manager
    item = post(cmd, "Yarınki duyuru", status="retry_scheduled")
    waiting = Operation(
        workspace_id=cmd.env.workspace.id,
        operation_type="publish_content",
        idempotency_key=publish_job_key(item.id, item.version),
        subject_type="content_item",
        subject_id=item.id,
        social_account_id=item.social_account_id,
        provider_kind="mock",
        status="retry_wait",
        attempts=1,
        is_simulated=True,
    )
    cmd.env.session.add(waiting)
    cmd.env.session.commit()

    command = ask_cancel(cmd, manager)  # the manager asks ...
    response = cmd.decide(owner, command["approval"])  # ... the owner confirms
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "approved"

    done = cmd.get(manager, command["id"])
    assert done["status"] == "completed"
    assert done["result"] == {
        "message_key": "command.content_cancelled",
        "params": {"title": "Yarınki duyuru", "when": "16 Oca 19:00"},
        "links": [{"target": "content", "id": str(item.id)}],
    }
    assert fresh(cmd, ContentItem, item.id).status == "cancelled"
    assert [j.status for j in jobs_of(cmd, "publish_content")] == ["cancelled"]
    assert fresh(cmd, Operation, waiting.id).status == "cancelled"
    # Executed as the human who decided (INV-04): the audit trail says the owner.
    (cancelled,) = audits(cmd, "content.cancelled")
    assert cancelled.actor_id == str(owner.user.id) and cancelled.resource_id == item.id


def test_cancelling_a_post_that_waits_for_approval_cancels_that_approval_too(
    cmd: CommandEnv,
) -> None:
    from tests.helpers.content import request_approval

    item = post(cmd, "Onay bekleyen", status="pending_approval")
    pending = request_approval(cmd.env, item, requester=cmd.env.staff)
    cmd.env.session.commit()
    command = ask_cancel(cmd)
    assert cmd.decide(cmd.env.owner, command["approval"]).status_code == 200
    assert fresh(cmd, ContentItem, item.id).status == "cancelled"
    cancelled = fresh(cmd, Approval, pending.id)
    assert (cancelled.status, cancelled.cancel_reason) == ("cancelled", "SUBJECT_CANCELLED")


def test_an_edit_after_asking_makes_the_confirmation_stale_and_nothing_is_cancelled(
    cmd: CommandEnv,
) -> None:
    owner = cmd.env.owner
    item = post(cmd, "Yarınki duyuru")
    command = ask_cancel(cmd)
    edited = cmd.env.call(
        owner,
        "PATCH",
        f"{ITEMS}/{item.id}",
        json={"expected_version": 1, "caption": "Yeni metin"},
    )
    assert edited.status_code == 200 and edited.json()["version"] == 2

    response = cmd.decide(owner, command["approval"])
    assert response.status_code == 200  # the decision stands (like FACT_CHANGED_MEANWHILE) ...
    failed = cmd.get(owner, command["id"])
    assert failed["status"] == "failed" and failed["error_code"] == "VERSION_CONFLICT"
    assert failed["result"]["message_key"] == "command.content_changed_meanwhile"
    assert failed["result"]["links"] == [{"target": "content", "id": str(item.id)}]
    item = fresh(cmd, ContentItem, item.id)  # ... but the edited draft was not cancelled
    assert (item.status, item.version) == ("draft", 2)
    assert audits(cmd, "content.cancelled") == []
    assert fresh(cmd, Approval, command["approval"]["id"]).status == "approved"  # single use


def test_cancelled_by_someone_else_meanwhile_is_a_conflict_not_a_second_cancel(
    cmd: CommandEnv,
) -> None:
    owner = cmd.env.owner
    item = post(cmd, "Yarınki duyuru")
    command = ask_cancel(cmd)
    assert cmd.env.call(owner, "POST", f"{ITEMS}/{item.id}/cancel").status_code == 200
    assert cmd.decide(owner, command["approval"]).status_code == 200
    failed = cmd.get(owner, command["id"])
    assert failed["status"] == "failed" and failed["error_code"] == "CONFLICT_STATE"
    assert len(audits(cmd, "content.cancelled")) == 1  # only the first cancel


def test_a_post_that_started_publishing_meanwhile_is_not_cancelled(cmd: CommandEnv) -> None:
    owner = cmd.env.owner
    item = post(cmd, "Yarınki duyuru")
    command = ask_cancel(cmd)
    item = fresh(cmd, ContentItem, item.id)
    item.status = "publishing"  # the publish executor took it
    cmd.env.session.commit()
    assert cmd.decide(owner, command["approval"]).status_code == 200
    failed = cmd.get(owner, command["id"])
    assert failed["status"] == "failed" and failed["error_code"] == "CONFLICT_STATE"
    assert fresh(cmd, ContentItem, item.id).status == "publishing"
    assert [j.status for j in jobs_of(cmd, "publish_content")] == ["queued"]  # untouched


def test_staff_cannot_ask_to_cancel_content(cmd: CommandEnv) -> None:
    item = post(cmd, "Yarınki duyuru")
    command = ask_cancel(cmd, cmd.env.staff)
    assert command["status"] == "failed" and command["error_code"] == "FORBIDDEN"
    assert command["approval"] is None
    assert command["result"] == {
        "message_key": "command.forbidden",
        "params": {"permission": "content.approve"},
        "links": [],
    }
    assert fresh(cmd, ContentItem, item.id).status == "scheduled"


@pytest.mark.invariant("INV-04")
def test_the_permission_is_checked_against_the_human_who_confirms(cmd: CommandEnv) -> None:
    """The requester may confirm their own card (ADR-014), but execution is checked against the
    role of whoever decides *now*: a manager demoted since asking cannot cancel through it."""
    manager = cmd.env.manager
    item = post(cmd, "Yarınki duyuru")
    command = ask_cancel(cmd, manager)
    member, _ = identity_repo.get_membership(cmd.env.session, cmd.env.workspace.id, manager.user.id)  # type: ignore[misc]
    member.role = "staff"
    cmd.env.session.commit()

    response = cmd.decide(manager, command["approval"])
    assert response.status_code == 403 and response.json()["code"] == "FORBIDDEN"
    # Rolled back as a whole: the card is still open for an owner, the post untouched.
    assert fresh(cmd, Approval, command["approval"]["id"]).status == "pending"
    assert fresh(cmd, ContentItem, item.id).status == "scheduled"
    assert cmd.get(manager, command["id"])["status"] == "awaiting_confirmation"
    assert cmd.decide(cmd.env.owner, command["approval"]).status_code == 200
    assert fresh(cmd, ContentItem, item.id).status == "cancelled"


def test_rejecting_the_confirmation_cancels_the_command_not_the_post(cmd: CommandEnv) -> None:
    owner = cmd.env.owner
    item = post(cmd, "Yarınki duyuru")
    command = ask_cancel(cmd)
    assert cmd.decide(owner, command["approval"], "reject").status_code == 200
    assert cmd.get(owner, command["id"])["status"] == "cancelled"
    assert fresh(cmd, ContentItem, item.id).status == "scheduled"


def test_free_text_cannot_confirm_a_cancel(cmd: CommandEnv) -> None:
    item = post(cmd, "Yarınki duyuru")
    ask_cancel(cmd)
    for text in ("evet", "tamam", "onayla", "yes, cancel it"):
        assert cmd.run(cmd.env.owner, text)["status"] in ("unsupported", "awaiting_confirmation")
    assert fresh(cmd, ContentItem, item.id).status == "scheduled"


# --- references: alias, ambiguity, not found ------------------------------------------------


def test_two_matches_are_a_question_with_title_and_time(cmd: CommandEnv) -> None:
    owner = cmd.env.owner
    morning = post(cmd, "Sabah duyurusu", when=at(cmd, hour=7))
    evening = post(cmd, "Akşam duyurusu", when=at(cmd, hour=16))
    command = ask_cancel(cmd)

    assert command["status"] == "needs_clarification" and command["approval"] is None
    clarification = command["clarification"]
    assert clarification["question_key"] == "command.clarify.which_content"
    assert clarification["options"] == [
        {"id": "1", "label": "Sabah duyurusu · 16 Oca 10:00"},
        {"id": "2", "label": "Akşam duyurusu · 16 Oca 19:00"},
    ]
    assert "content_id" not in json.dumps(command)  # ids stay server-side
    assert fresh(cmd, ContentItem, morning.id).status == "scheduled"

    bad = cmd.env.call(
        owner, "POST", f"/commands/{command['id']}/clarification", json={"option_id": "3"}
    )
    assert bad.status_code == 422
    chosen = cmd.env.call(
        owner, "POST", f"/commands/{command['id']}/clarification", json={"option_id": "2"}
    )
    assert chosen.status_code == 202, chosen.text
    card = chosen.json()
    assert card["status"] == "awaiting_confirmation"
    assert card["approval"]["summary"]["content_id"] == str(evening.id)
    assert cmd.decide(owner, card["approval"]).status_code == 200
    assert fresh(cmd, ContentItem, evening.id).status == "cancelled"
    assert fresh(cmd, ContentItem, morning.id).status == "scheduled"  # the other one is untouched


def test_nothing_matching_is_reference_not_found_with_a_helpful_message(cmd: CommandEnv) -> None:
    post(cmd, "Haftaya", when=at(cmd, days=5))
    command = ask_cancel(cmd)
    assert command["status"] == "failed" and command["error_code"] == "REFERENCE_NOT_FOUND"
    assert command["result"] == {
        "message_key": "command.reference_not_found",
        "params": {"description": None},
        "links": [{"target": "content"}],
    }


def test_a_story_filter_does_not_match_a_feed_post(cmd: CommandEnv) -> None:
    post(cmd, "Yarınki post", kind="feed_image")
    command = ask_cancel(cmd, text="yarınki story'yi iptal et")
    assert command["status"] == "failed" and command["error_code"] == "REFERENCE_NOT_FOUND"


def test_the_model_can_point_at_the_catalog_by_alias(cmd: CommandEnv) -> None:
    first = post(cmd, "Birinci", when=at(cmd, hour=7))
    second = post(cmd, "İkinci", when=at(cmd, hour=16))
    cmd.provider.queue(
        "interpret_command",
        {
            "interpretation": {
                "type": "content.cancel_scheduled",
                "content_ref": {
                    "alias": "C2",
                    "description": None,
                    "local_date": None,
                    "content_type": None,
                },
            }
        },
    )
    command = cmd.run(cmd.env.owner, "ikincisini iptal et")
    assert command["status"] == "awaiting_confirmation"
    assert command["approval"]["summary"]["content_id"] == str(second.id)
    assert str(first.id) != command["approval"]["summary"]["content_id"]
    # The model saw titles and aliases, never an id.
    body = cmd.provider.calls[0].messages[0].content
    catalog = json.loads(body.split("<content_catalog>\n")[1].split("\n</content_catalog>")[0])
    assert [(c["ref_id"], c["title"], c["local_schedule"]) for c in catalog] == [
        ("C1", "Birinci", "2026-01-16T10:00+03:00"),
        ("C2", "İkinci", "2026-01-16T19:00+03:00"),
    ]
    assert str(first.id) not in body and str(second.id) not in body


def test_a_model_cannot_name_a_post_by_id_or_a_foreign_alias(cmd: CommandEnv) -> None:
    item = post(cmd, "Yarınki duyuru")
    cmd.provider.queue(
        "interpret_command",
        {
            "interpretation": {
                "type": "content.cancel_scheduled",
                "content_ref": {
                    "alias": str(item.id),
                    "description": None,
                    "local_date": None,
                    "content_type": None,
                },
            }
        },
    )
    command = cmd.run(cmd.env.owner, CANCEL)
    # not an alias: sent back for repair; the repair (the fake) then answers from the text
    assert command["status"] == "awaiting_confirmation"
    assert command["approval"]["summary"]["content_id"] == str(item.id)  # resolved by code
    assert cmd.env.session.scalars(select(AgentRun)).one().repair_attempts == 1
    assert fresh(cmd, ContentItem, item.id).status == "scheduled"


def test_the_catalog_holds_the_next_14_days_and_recent_failures_only(cmd: CommandEnv) -> None:
    soon = post(cmd, "Yakın", when=at(cmd, days=2))
    post(cmd, "Uzak", when=at(cmd, days=20))
    post(cmd, "İptal", status="cancelled", when=at(cmd, days=1))
    post(cmd, "Yayınlandı", status="published", when=at(cmd, days=-1))
    post(
        cmd,
        "Eski hata",
        status="failed",
        when=at(cmd, days=-30),
        last_error_code="MEDIA_REJECTED",
        updated_at=cmd.env.clock.now() - timedelta(days=30),
    )
    recent = post(
        cmd, "Yeni hata", status="failed", when=at(cmd, days=-1), last_error_code="MEDIA_REJECTED"
    )
    command = cmd.run(cmd.env.owner, "Aylık üyelik ne kadar?")
    assert command["status"] == "completed"
    body = cmd.provider.calls[0].messages[0].content
    catalog = json.loads(body.split("<content_catalog>\n")[1].split("\n</content_catalog>")[0])
    assert [(c["ref_id"], c["title"], c["status"]) for c in catalog] == [
        ("C1", "Yeni hata", "failed"),
        ("C2", "Yakın", "scheduled"),
    ]
    assert soon and recent


# --- query.content_status and query.explain_failure -----------------------------------------


def test_content_status_says_what_state_the_post_is_in(cmd: CommandEnv) -> None:
    item = post(cmd, "Yarınki duyuru")
    command = cmd.run(cmd.env.owner, "yarınki postun durumu ne")
    assert command["status"] == "completed"
    assert command["result"] == {
        "message_key": "command.content_status",
        "params": {
            "title": "Yarınki duyuru",
            "content_type": "feed_image",
            "status": "scheduled",  # scheduled is not published (INV-18)
            "when": "16 Oca 19:00",
            "is_simulated": True,  # INV-09
            "hold_reason": None,
            "error_code": None,
        },
        "links": [{"target": "content", "id": str(item.id)}],
    }


def test_content_status_is_open_to_every_role(cmd: CommandEnv) -> None:
    post(cmd, "Yarınki duyuru")
    command = cmd.run(cmd.env.staff, "yarınki postun durumu ne")
    assert command["status"] == "completed"


def test_explain_the_latest_failure_from_the_error_catalog(cmd: CommandEnv) -> None:
    post(
        cmd,
        "Eski",
        status="failed",
        last_error_code="MEDIA_REJECTED",
        updated_at=cmd.env.clock.now() - timedelta(days=2),
    )
    failed = post(
        cmd, "Haftalık program", status="failed", last_error_code="PUBLISH_DEADLINE_PASSED"
    )
    command = cmd.run(cmd.env.owner, "son hata neydi?")
    assert command["status"] == "completed"
    assert command["result"]["message_key"] == "command.content_failure"
    assert command["result"]["params"] == {
        "title": "Haftalık program",
        "status": "failed",
        "error_code": "PUBLISH_DEADLINE_PASSED",
        "what": "Gönderi zamanında yayınlanamadı.",
        "next": "Yeni bir zaman seçip yeniden zamanlayın.",
        "retryable": False,
        "is_simulated": True,
        "retry_at": None,
    }
    assert command["result"]["links"] == [{"target": "content", "id": str(failed.id)}]


def test_the_explanation_follows_the_users_language(cmd: CommandEnv) -> None:
    cmd.env.owner.user.ui_locale = "en"
    cmd.env.session.commit()
    post(cmd, "Weekly plan", status="failed", last_error_code="MEDIA_REJECTED")
    command = cmd.run(cmd.env.owner, "what was the last error")
    params = command["result"]["params"]
    assert params["what"] == "Instagram could not process the image."
    assert params["next"] == "Replace it with another image and schedule the post again."


def test_explain_a_post_on_hold_and_a_post_by_reference(cmd: CommandEnv) -> None:
    held = post(cmd, "Fiyatlı duyuru", status="on_hold", hold_reason="FACT_CHANGED")
    latest = cmd.run(cmd.env.owner, "son hata neydi?")
    params = latest["result"]["params"]
    assert (params["status"], params["error_code"]) == ("on_hold", "FACT_CHANGED")
    assert params["what"] == "Kullandığı işletme bilgisi değiştiği için beklemeye alındı."
    by_date = cmd.run(cmd.env.owner, "yarınki post neden başarısız oldu")
    assert by_date["result"]["links"] == [{"target": "content", "id": str(held.id)}]


def test_an_unknown_code_is_explained_generically_not_shown_raw(cmd: CommandEnv) -> None:
    post(cmd, "Garip", status="failed", last_error_code="SOMETHING_NEW")
    params = cmd.run(cmd.env.owner, "son hata neydi?")["result"]["params"]
    assert params["what"] == "Yayınlanırken bir şeyler ters gitti."
    assert params["retryable"] is None


def test_no_failure_is_an_answer_not_an_error(cmd: CommandEnv) -> None:
    post(cmd, "Yarınki duyuru")
    command = cmd.run(cmd.env.owner, "son hata neydi?")
    assert command["status"] == "completed" and command["error_code"] is None
    assert command["result"] == {
        "message_key": "command.no_failure",
        "params": {},
        "links": [{"target": "content"}],
    }


def test_a_post_that_is_fine_is_not_explained_as_a_failure(cmd: CommandEnv) -> None:
    cmd.provider.queue(
        "interpret_command",
        {
            "interpretation": {
                "type": "query.explain_failure",
                "content_ref": {
                    "alias": "C1",
                    "description": None,
                    "local_date": None,
                    "content_type": None,
                },
            }
        },
    )
    post(cmd, "Yarınki duyuru", status="failed", last_error_code="MEDIA_REJECTED")
    command = cmd.run(cmd.env.owner, "C1 neden olmadı")
    assert command["result"]["message_key"] == "command.content_failure"


# --- isolation (INV-01) ---------------------------------------------------------------------


def test_another_workspaces_content_is_invisible_to_the_catalog_and_the_resolver(
    cmd: CommandEnv,
) -> None:
    other, users = workspace_with_members(cmd.env.session, roles=("owner",), slug="other")
    account = connect_account_in(cmd, other)
    foreign = ContentItem(
        workspace_id=other.id,
        content_type="feed_image",
        status="scheduled",
        version=1,
        title="Yabancı gizli duyuru",
        caption="x",
        scheduled_at=at(cmd),
        social_account_id=account.id,
        created_by_user_id=users["owner"].id,
        created_at=cmd.env.clock.now(),
        updated_at=cmd.env.clock.now(),
    )
    cmd.env.session.add(foreign)
    cmd.env.session.commit()

    command = cmd.run(cmd.env.owner, CANCEL)
    assert command["status"] == "failed" and command["error_code"] == "REFERENCE_NOT_FOUND"
    assert "Yabancı" not in cmd.provider.calls[0].messages[0].content
    latest = cmd.run(cmd.env.owner, "son hata neydi?")
    assert latest["result"]["message_key"] == "command.no_failure"
    status = cmd.run(cmd.env.owner, "yarınki postun durumu ne")
    assert status["error_code"] == "REFERENCE_NOT_FOUND"
    assert fresh(cmd, ContentItem, foreign.id).status == "scheduled"


def connect_account_in(cmd: CommandEnv, workspace: Any) -> SocialAccount:
    account = SocialAccount(
        workspace_id=workspace.id,
        platform="instagram",
        provider_kind="mock",
        external_account_id="mock-other",
        username="other.demo",
        status="connected",
        capabilities={"publish_feed_image": True, "publish_story_image": True},
        connected_at=cmd.env.clock.now(),
    )
    cmd.env.session.add(account)
    cmd.env.session.flush()
    return account


def test_a_command_is_private_to_the_member_who_typed_it(cmd: CommandEnv) -> None:
    post(cmd, "Yarınki duyuru")
    command = ask_cancel(cmd)
    peek = cmd.env.call(cmd.env.staff, "GET", f"/commands/{command['id']}")
    assert peek.status_code == 404
