"""Confirmation, state/version fencing and durable timers for D-04."""

from datetime import timedelta

import pytest
from sqlalchemy import select

from app.agent.models import AccountAgent
from app.agent.pause_jobs import ResumePayload, resume_due
from app.content.models import ContentItem
from app.jobs.registry import JobContext
from tests.helpers.content import connect_account
from tests.integration.commands.conftest import CommandEnv
from tests.integration.commands.test_content_commands import fresh, jobs_of, post

MOVE = "move tomorrow's story to 19:00"
PAUSE = "pause the assistant until tomorrow morning"


def agent(cmd: CommandEnv) -> AccountAgent:
    social = connect_account(cmd.env)
    account = cmd.env.session.scalar(
        select(AccountAgent).where(AccountAgent.social_account_id == social.id)
    )
    if account is None:
        account = AccountAgent(workspace_id=cmd.env.workspace.id, social_account_id=social.id)
        cmd.env.session.add(account)
    account.controller_mode, account.state = "agent", "active"
    cmd.env.session.commit()
    return account


@pytest.mark.parametrize("text", [MOVE, "yarınki story'yi 19:00'a taşı"])
def test_reschedule_confirms_old_new_local_time_and_replaces_version_job(
    cmd: CommandEnv, text: str
) -> None:
    item = post(cmd, "Story", kind="story_image", when=cmd.env.clock.now() + timedelta(days=1))
    before = item.scheduled_at
    command = cmd.run(cmd.env.owner, text)
    assert command["status"] == "awaiting_confirmation"
    assert fresh(cmd, ContentItem, item.id).scheduled_at == before
    summary = command["approval"]["summary"]
    assert "15:00" in summary["old_formatted"] and "19:00" in summary["new_formatted"]
    assert summary["timezone"] == "Europe/Istanbul"
    response = cmd.decide(cmd.env.owner, command["approval"])
    assert response.status_code == 200, response.text
    assert cmd.get(cmd.env.owner, command["id"])["status"] == "completed"
    item = fresh(cmd, ContentItem, item.id)
    assert item.version == 2 and item.status == "scheduled" and item.scheduled_at.hour == 16
    assert sorted(j.status for j in jobs_of(cmd, "publish_content")) == ["cancelled", "queued"]
    assert cmd.decide(cmd.env.owner, command["approval"]).status_code == 409


@pytest.mark.parametrize(
    "state", ["publishing", "published", "retry_scheduled", "cancelled", "draft"]
)
def test_reschedule_rejects_disallowed_states(cmd: CommandEnv, state: str) -> None:
    post(cmd, "Story", kind="story_image", status=state)
    command = cmd.run(cmd.env.owner, MOVE)
    assert command["status"] == "failed"
    assert command["approval"] is None


def test_reschedule_choice_keeps_time_and_stale_decision_cannot_apply(cmd: CommandEnv) -> None:
    one = post(cmd, "First", kind="story_image")
    post(cmd, "Second", kind="story_image")
    command = cmd.run(cmd.env.owner, MOVE)
    assert command["status"] == "needs_clarification"
    response = cmd.env.call(
        cmd.env.owner, "POST", f"/commands/{command['id']}/clarification", json={"option_id": "1"}
    )
    assert response.status_code == 202, response.text
    command = cmd.get(cmd.env.owner, command["id"])
    assert command["status"] == "awaiting_confirmation"
    # Whichever item was selected, an edit invalidates its version binding.
    for item in cmd.env.session.scalars(select(ContentItem)).all():
        item.version += 1
    cmd.env.session.commit()
    assert cmd.decide(cmd.env.owner, command["approval"]).status_code == 200
    assert cmd.get(cmd.env.owner, command["id"])["error_code"] == "VERSION_CONFLICT"
    assert fresh(cmd, ContentItem, one.id).scheduled_at.hour == 16


def test_reschedule_past_and_staff_are_refused(cmd: CommandEnv) -> None:
    post(cmd, "Story", kind="story_image")
    assert cmd.run(cmd.env.staff, MOVE)["error_code"] == "FORBIDDEN"
    command = cmd.run(cmd.env.owner, "move story C1 to 2026-01-14 19:00")
    assert command["error_code"] == "SCHEDULE_IN_PAST"


@pytest.mark.parametrize("text", [PAUSE, "asistanı yarın sabaha kadar duraklat"])
def test_pause_needs_confirmation_and_resumes_durably(cmd: CommandEnv, text: str) -> None:
    account = agent(cmd)
    command = cmd.run(cmd.env.owner, text)
    assert command["status"] == "awaiting_confirmation"
    assert "09:00" in command["approval"]["summary"]["resume_at"]
    assert fresh(cmd, AccountAgent, account.id).state == "active"
    assert jobs_of(cmd, "agent_resume_due") == []
    assert cmd.decide(cmd.env.owner, command["approval"]).status_code == 200
    assert fresh(cmd, AccountAgent, account.id).state == "paused"
    (timer,) = jobs_of(cmd, "agent_resume_due")
    assert timer.run_at.hour == 6  # 09:00 Istanbul
    cmd.env.clock.advance(timedelta(days=1))
    cmd.process()
    assert fresh(cmd, AccountAgent, account.id).state == "active"
    run_timer(cmd, timer)
    assert fresh(cmd, AccountAgent, account.id).config_version == 3


def run_timer(cmd: CommandEnv, timer) -> None:
    resume_due(
        JobContext(
            job_id=timer.id,
            job_type=timer.job_type,
            workspace_id=timer.workspace_id,
            correlation_id=None,
            payload=ResumePayload.model_validate(timer.payload),
            attempt=1,
            max_attempts=3,
            session_factory=cmd.factory,
            clock=cmd.env.clock,
            _heartbeat=lambda: None,
        )
    )


@pytest.mark.parametrize("newer", ["manual_resume", "manual_pause", "new_pause", "lost_owner"])
def test_old_timer_cannot_override_new_state_or_authority(cmd: CommandEnv, newer: str) -> None:
    account = agent(cmd)
    command = cmd.run(cmd.env.owner, PAUSE)
    assert cmd.decide(cmd.env.owner, command["approval"]).status_code == 200
    (timer,) = jobs_of(cmd, "agent_resume_due")
    if newer == "new_pause":
        command = cmd.run(cmd.env.owner, "pause the assistant until tomorrow 20:00")
        assert cmd.decide(cmd.env.owner, command["approval"]).status_code == 200
    elif newer == "lost_owner":
        cmd.env.owner.user.is_active = False
        cmd.env.session.commit()
    else:
        # A manual pause needs the agent active first: the HTTP endpoint refuses a second pause.
        actions = ["resume"] if newer == "manual_resume" else ["resume", "pause"]
        for action in actions:
            state = fresh(cmd, AccountAgent, account.id)
            response = cmd.env.call(
                cmd.env.owner,
                "POST",
                f"/accounts/{account.social_account_id}/agent/{action}",
                json={"expected_config_version": state.config_version},
            )
            assert response.status_code == 200, response.text
        if newer == "manual_pause":
            repeat = cmd.env.call(
                cmd.env.owner,
                "POST",
                f"/accounts/{account.social_account_id}/agent/pause",
                json={
                    "expected_config_version": fresh(cmd, AccountAgent, account.id).config_version
                },
            )
            assert repeat.status_code == 409  # HTTP still refuses a second pause
    expected = fresh(cmd, AccountAgent, account.id).state
    version = account.config_version
    cmd.env.clock.advance(timedelta(hours=19))
    run_timer(cmd, timer)
    assert fresh(cmd, AccountAgent, account.id).state == expected
    assert account.config_version == version


def test_pause_staff_manager_and_stale_card_cannot_change_account(cmd: CommandEnv) -> None:
    account = agent(cmd)
    for role in (cmd.env.staff, cmd.env.manager):
        assert cmd.run(role, PAUSE)["error_code"] == "FORBIDDEN"
    command = cmd.run(cmd.env.owner, PAUSE)
    account = fresh(cmd, AccountAgent, account.id)
    account.config_version += 1
    cmd.env.session.commit()
    assert cmd.decide(cmd.env.owner, command["approval"]).status_code == 200
    assert cmd.get(cmd.env.owner, command["id"])["error_code"] == "VERSION_CONFLICT"
    assert jobs_of(cmd, "agent_resume_due") == []


def test_reschedule_validation_failure_rolls_back_old_schedule_and_job(cmd: CommandEnv) -> None:
    item = post(cmd, "Story", kind="story_image")
    command = cmd.run(cmd.env.owner, MOVE)
    before = item.scheduled_at
    item = fresh(cmd, ContentItem, item.id)
    item.media_asset_id = None  # invalidated media after the preview
    cmd.env.session.commit()
    assert cmd.decide(cmd.env.owner, command["approval"]).status_code == 200
    assert cmd.get(cmd.env.owner, command["id"])["error_code"] == "CONTENT_VALIDATION_FAILED"
    item = fresh(cmd, ContentItem, item.id)
    assert (item.version, item.status, item.scheduled_at) == (1, "scheduled", before)
    assert [job.status for job in jobs_of(cmd, "publish_content")] == ["queued"]


@pytest.mark.parametrize("kind", ["move", "pause"])
def test_rejection_and_expiry_never_apply_management_commands(cmd: CommandEnv, kind: str) -> None:
    if kind == "move":
        item = post(cmd, "Story", kind="story_image")
    else:
        account = agent(cmd)
    text = MOVE if kind == "move" else PAUSE
    first = cmd.run(cmd.env.owner, text)
    assert cmd.decide(cmd.env.owner, first["approval"], decision="reject").status_code == 200
    second = cmd.run(cmd.env.owner, text)
    cmd.env.clock.advance(timedelta(minutes=31))
    assert cmd.decide(cmd.env.owner, second["approval"]).status_code == 409
    if kind == "move":
        assert fresh(cmd, ContentItem, item.id).version == 1
    else:
        assert fresh(cmd, AccountAgent, account.id).state == "active"
        assert jobs_of(cmd, "agent_resume_due") == []


def test_target_that_passes_before_confirmation_is_refused(cmd: CommandEnv) -> None:
    account = agent(cmd)
    command = cmd.run(cmd.env.owner, "pause assistant until today 15:05")
    cmd.env.clock.advance(timedelta(minutes=6))
    assert cmd.decide(cmd.env.owner, command["approval"]).status_code == 200
    assert cmd.get(cmd.env.owner, command["id"])["error_code"] == "VALIDATION_FAILED"
    assert fresh(cmd, AccountAgent, account.id).state == "active"


def test_foreign_timer_cannot_resume_an_account(cmd: CommandEnv) -> None:
    import uuid

    account = agent(cmd)
    command = cmd.run(cmd.env.owner, PAUSE)
    assert cmd.decide(cmd.env.owner, command["approval"]).status_code == 200
    (timer,) = jobs_of(cmd, "agent_resume_due")
    # Handler receives a job from another tenant with the first tenant's account ID.
    cmd.env.clock.advance(timedelta(days=1))
    resume_due(
        JobContext(
            job_id=timer.id,
            job_type=timer.job_type,
            workspace_id=uuid.uuid4(),
            correlation_id=None,
            payload=ResumePayload.model_validate(timer.payload),
            attempt=1,
            max_attempts=3,
            session_factory=cmd.factory,
            clock=cmd.env.clock,
            _heartbeat=lambda: None,
        )
    )
    assert fresh(cmd, AccountAgent, account.id).state == "paused"
