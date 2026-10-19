"""Workflow B end to end: command -> confirmation -> versioned fact update (AC-C1, AC-C2)."""

from datetime import datetime, timedelta

import pytest
from sqlalchemy import select

from app.ai.models import AgentRun
from app.approvals.models import Approval
from app.audit import service as audit
from app.commands.models import OwnerCommand
from app.knowledge import repository as knowledge_repo
from app.knowledge.models import FactCandidate
from app.notifications.models import Notification
from tests.factories import knowledge_ctx
from tests.integration.commands.conftest import MONTHLY, CommandEnv


def _audit(cmd: CommandEnv, action: str) -> list:  # type: ignore[type-arg]
    return list(
        audit.list_entries(cmd.env.session, workspace_id=cmd.env.workspace.id, action=action)
    )


def test_ac_c1_the_command_reaches_a_confirmation_with_old_and_new_values(
    cmd: CommandEnv,
) -> None:
    owner = cmd.env.owner
    submitted = cmd.submit(owner, "Aylık üyelik artık 7.000 TL")
    assert submitted["status"] == "interpreting" and submitted["approval"] is None

    assert cmd.process() == 1  # the interpretation job
    command = cmd.get(owner, submitted["id"])

    assert command["status"] == "awaiting_confirmation"
    assert command["command_type"] == "knowledge.update_fact"
    approval = command["approval"]
    assert approval["kind"] == "confirmation" and approval["status"] == "pending"
    assert approval["action"] == "command.update_fact"
    assert approval["summary"]["label"] == "Aylık üyelik"
    assert approval["summary"]["old_formatted"] == "6.000 ₺ / ay"
    assert approval["summary"]["new_formatted"] == "7.000 ₺ / ay"
    assert approval["summary"]["impact"] == {"total": 0, "items": []}
    assert len(approval["payload_hash"]) == 64 and approval["can_decide"] is True
    expires = datetime.fromisoformat(approval["expires_at"].replace("Z", "+00:00"))
    assert expires == cmd.env.clock.now() + timedelta(minutes=30)
    assert approval["subject"] == {
        "type": "owner_command",
        "id": submitted["id"],
        "version": 1,
        "status": "awaiting_confirmation",
        "link": {"target": "owner_command", "id": submitted["id"]},
    }
    # Nothing changed yet.
    assert cmd.fact(MONTHLY).current_version == 1
    assert cmd.fact(MONTHLY).value["amount"] == "6000.00"


def test_the_interpretation_is_recorded_as_a_fake_agent_run(cmd: CommandEnv) -> None:
    command = cmd.run(cmd.env.owner, "Aylık üyelik artık 7.000 TL")
    run = cmd.env.session.scalars(select(AgentRun)).one()
    assert (run.task, run.status, run.provider, run.is_fake) == (
        "interpret_command",
        "succeeded",
        "fake",
        True,
    )
    assert run.prompt_version == "v1" and run.repair_attempts == 0
    assert run.output is not None and run.output["interpretation"]["fact_key"] == MONTHLY
    stored = cmd.env.session.get(OwnerCommand, command["id"])
    assert stored is not None and stored.agent_run_id == run.id
    # The model saw the owner's facts and the registry, and the text as data: never the secret key.
    call = cmd.provider.calls[0]
    body = call.messages[0].content
    assert "<command_registry>" in body and "<business_facts>" in body
    assert "<owner_command>\nAylık üyelik artık 7.000 TL\n</owner_command>" in body
    assert '"6.000 ₺ / ay"' in body
    assert "knowledge.update_fact" in body and "approve" not in call.system.split("Never")[0]


def test_ac_c2_confirming_updates_the_fact_and_keeps_the_history(cmd: CommandEnv) -> None:
    owner = cmd.env.owner
    command = cmd.run(owner, "Aylık üyelik artık 7.000 TL")

    response = cmd.decide(owner, command["approval"])
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "approved"
    assert response.json()["subject"]["status"] == "completed"

    done = cmd.get(owner, command["id"])
    assert done["status"] == "completed" and done["error_code"] is None
    assert done["result"]["message_key"] == "command.fact_updated"
    assert done["result"]["params"] == {
        "label": "Aylık üyelik",
        "old_display": "6.000 ₺ / ay",
        "new_display": "7.000 ₺ / ay",
        "version": 2,
    }
    assert done["result"]["links"] == [
        {"target": "knowledge", "category": "pricing", "key": MONTHLY}
    ]

    fact = cmd.fact(MONTHLY)
    assert fact.current_version == 2 and fact.status == "verified"
    assert fact.value == {"amount": "7000.00", "currency": "TRY", "unit": "month"}
    versions = knowledge_repo.list_versions(
        cmd.env.session, knowledge_ctx(cmd.env.workspace), fact.id
    )
    by_version = {v.version: v for v in versions}
    assert by_version[1].value["amount"] == "6000.00"  # the previous version is untouched (INV-17)
    assert by_version[2].value["amount"] == "7000.00"
    assert (by_version[2].source_type, by_version[2].source_ref) == ("owner_command", command["id"])
    assert by_version[2].actor_id == str(owner.user.id)

    (updated,) = _audit(cmd, "fact.updated")
    assert updated.metadata_["source_type"] == "owner_command"
    assert updated.metadata_["source_ref"] == command["id"]  # references the command
    assert (updated.metadata_["old_display"], updated.metadata_["new_display"]) == (
        "6.000 ₺ / ay",
        "7.000 ₺ / ay",
    )
    for action in ("command.received", "command.interpreted", "command.executed"):
        assert len(_audit(cmd, action)) == 1, action
    assert len(_audit(cmd, "approval.requested")) == 1
    assert len(_audit(cmd, "approval.approved")) == 1


def test_the_other_verifiers_are_told_the_fact_changed(cmd: CommandEnv) -> None:
    command = cmd.run(cmd.env.owner, "Aylık üyelik artık 7.000 TL")
    cmd.decide(cmd.env.owner, command["approval"])
    notes = cmd.env.session.scalars(
        select(Notification).where(Notification.type == "knowledge.fact_changed")
    ).all()
    assert [n.recipient_user_id for n in notes] == [cmd.env.manager.user.id]
    assert notes[0].params["new_display"] == "7.000 ₺ / ay"


def test_a_manager_can_confirm_an_owners_command(cmd: CommandEnv) -> None:
    command = cmd.run(cmd.env.owner, "Aylık üyelik artık 7.000 TL")
    approval = cmd.env.call(
        cmd.env.manager, "GET", f"/approvals/{command['approval']['id']}"
    ).json()
    assert approval["can_decide"] is True
    assert cmd.decide(cmd.env.manager, command["approval"]).status_code == 200
    assert cmd.fact(MONTHLY).value["amount"] == "7000.00"
    version = knowledge_repo.get_version(
        cmd.env.session, knowledge_ctx(cmd.env.workspace), cmd.facts[MONTHLY].id, 2
    )
    assert version is not None and version.actor_id == str(cmd.env.manager.user.id)  # the decider


def test_staff_confirmation_creates_a_contest_candidate_not_a_fact_change(
    cmd: CommandEnv,
) -> None:
    staff = cmd.env.staff
    command = cmd.run(staff, "Aylık üyelik artık 7.500 TL")
    assert command["status"] == "awaiting_confirmation"  # staff may ask...
    assert cmd.decide(staff, command["approval"]).status_code == 200  # ...and confirm their own

    done = cmd.get(staff, command["id"])
    assert done["status"] == "completed"
    assert done["result"]["message_key"] == "command.fact_proposed"
    fact = cmd.fact(MONTHLY)
    assert fact.current_version == 1 and fact.value["amount"] == "6000.00"  # unchanged
    candidate = cmd.env.session.scalars(select(FactCandidate)).one()
    assert (candidate.fact_key, candidate.relation, candidate.status) == (
        MONTHLY,
        "contest",
        "pending",
    )
    assert candidate.source_type == "staff_proposal"
    assert candidate.proposed_value["amount"] == "7500.00"
    assert candidate.proposed_by_actor_id == str(staff.user.id)


def test_the_same_value_is_reported_as_already_set_without_a_confirmation(cmd: CommandEnv) -> None:
    command = cmd.run(cmd.env.owner, "Aylık üyelik artık 6.000 TL")
    assert command["status"] == "completed" and command["approval"] is None
    assert command["result"]["message_key"] == "command.fact_unchanged"
    assert cmd.env.session.scalars(select(Approval)).all() == []


def test_a_brand_voice_command_goes_through_the_same_confirmation(cmd: CommandEnv) -> None:
    owner = cmd.env.owner
    command = cmd.run(owner, "Marka dilimiz daha samimi olsun")
    assert command["command_type"] == "knowledge.update_brand_voice"
    approval = command["approval"]
    assert approval["action"] == "command.update_brand_voice"
    assert approval["summary"]["old_formatted"] == "Sıcak ve kısa."
    assert "samimi" in approval["summary"]["new_formatted"]
    cmd.decide(owner, approval)
    assert "samimi" in cmd.fact("brand.voice_guidelines").value["tr"]
    assert (
        cmd.fact("brand.voice_guidelines").value["en"] == "Warm and short."
    )  # other language kept


def test_the_confirmation_binds_the_fact_version_the_owner_saw(cmd: CommandEnv) -> None:
    """If the fact changed between the confirmation and the decision, nothing is overwritten
    (FACT_CHANGED_MEANWHILE): the owner asks again with the current value in front of them."""
    owner = cmd.env.owner
    command = cmd.run(owner, "Aylık üyelik artık 7.000 TL")
    edit = cmd.env.call(
        owner,
        "PATCH",
        f"/facts/{cmd.facts[MONTHLY].id}",
        json={
            "expected_version": 1,
            "value": {"amount": "6500", "currency": "TRY", "unit": "month"},
        },
    )
    assert edit.status_code == 200, edit.text

    assert cmd.decide(owner, command["approval"]).status_code == 200
    done = cmd.get(owner, command["id"])
    assert done["status"] == "failed" and done["error_code"] == "FACT_CHANGED_MEANWHILE"
    assert done["result"]["message_key"] == "command.fact_changed_meanwhile"
    assert cmd.fact(MONTHLY).value["amount"] == "6500.00"  # the manual edit survives
    assert cmd.fact(MONTHLY).current_version == 2
    assert cmd.env.session.get(Approval, command["approval"]["id"]).status == "approved"  # type: ignore[union-attr]


def test_a_rejected_confirmation_cancels_the_command(cmd: CommandEnv) -> None:
    owner = cmd.env.owner
    command = cmd.run(owner, "Aylık üyelik artık 7.000 TL")
    assert cmd.decide(owner, command["approval"], "reject").status_code == 200
    assert cmd.get(owner, command["id"])["status"] == "cancelled"
    assert cmd.fact(MONTHLY).current_version == 1


def test_a_tampered_stored_payload_cannot_be_executed(cmd: CommandEnv) -> None:
    """Execution re-checks the binding: the stored payload must still match the approved hash."""
    owner = cmd.env.owner
    command = cmd.run(owner, "Aylık üyelik artık 7.000 TL")
    stored = cmd.env.session.get(OwnerCommand, command["id"])
    assert stored is not None and stored.resolution is not None
    tampered = {
        **stored.resolution,
        "new_value": {**stored.resolution["new_value"], "amount": "1.00"},
    }
    stored.resolution = tampered
    cmd.env.session.commit()

    response = cmd.decide(owner, command["approval"])
    assert response.status_code == 409 and response.json()["code"] == "APPROVAL_STALE"
    assert cmd.fact(MONTHLY).value["amount"] == "6000.00"
    cmd.env.session.expire_all()
    assert cmd.env.session.get(Approval, command["approval"]["id"]).status == "pending"  # type: ignore[union-attr]


@pytest.mark.parametrize("text", ["Aylık üyelik artık 7.000 TL"])
def test_resubmitting_with_the_same_request_id_returns_the_same_command(
    cmd: CommandEnv, text: str
) -> None:
    first = cmd.submit(cmd.env.owner, text, request_id="req-1")
    second = cmd.submit(cmd.env.owner, text, request_id="req-1")
    assert first["id"] == second["id"]
    assert cmd.process() == 1  # one job, not two
    assert len(cmd.env.session.scalars(select(OwnerCommand)).all()) == 1
    assert len(_audit(cmd, "command.received")) == 1
