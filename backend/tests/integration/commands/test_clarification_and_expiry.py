"""Clarification (AC-C6), cancel and expiry (AC-C7)."""

from sqlalchemy import select

from app.approvals.models import Approval
from app.commands.models import OwnerCommand
from tests.integration.commands.conftest import MONTHLY, QUARTER, REFORMER, STUDENT, CommandEnv


def _options(command: dict) -> dict[str, str]:  # type: ignore[type-arg]
    return {o["id"]: o["label"] for o in command["clarification"]["options"]}


def test_ac_c6_an_ambiguous_price_asks_which_fact_and_changes_nothing(cmd: CommandEnv) -> None:
    owner = cmd.env.owner
    command = cmd.run(owner, "fiyat artık 7000")

    assert command["status"] == "needs_clarification" and command["approval"] is None
    clarification = command["clarification"]
    assert clarification["question_key"] == "command.clarify.which_fact"
    assert clarification["params"] == {"raw": "7000"}
    # monthly / 3 months / reformer 8: the verified prices (not the unverified student price)
    assert _options(command) == {
        MONTHLY: "Aylık üyelik · 6.000 ₺ / ay",
        QUARTER: "3 aylık üyelik · 16.500 ₺ / paket",
        REFORMER: "Reformer 8 seans · 4.800 ₺ / paket",
    }
    assert STUDENT not in _options(command)
    assert "value" not in str(clarification)  # server-side values are never exposed
    for key in (MONTHLY, QUARTER, REFORMER):
        assert (
            cmd.fact(key).current_version == 1
        )  # nothing changes before a choice and a confirmation
    assert cmd.env.session.scalars(select(Approval)).all() == []


def test_choosing_an_option_continues_to_a_confirmation_then_the_update(cmd: CommandEnv) -> None:
    owner = cmd.env.owner
    command = cmd.run(owner, "fiyat artık 7000")

    answered = cmd.env.call(
        owner, "POST", f"/commands/{command['id']}/clarification", json={"option_id": QUARTER}
    )
    assert answered.status_code == 202, answered.text
    body = answered.json()
    assert body["status"] == "awaiting_confirmation" and body["clarification"] is None
    assert body["approval"]["summary"]["label"] == "3 aylık üyelik"
    assert body["approval"]["summary"]["old_formatted"] == "16.500 ₺ / paket"
    assert body["approval"]["summary"]["new_formatted"] == "7.000 ₺ / paket"
    assert cmd.fact(QUARTER).current_version == 1  # still nothing changed

    assert cmd.decide(owner, body["approval"]).status_code == 200
    assert cmd.fact(QUARTER).value["amount"] == "7000.00"
    assert cmd.fact(MONTHLY).value["amount"] == "6000.00"  # the other prices are untouched
    assert cmd.fact(REFORMER).value["amount"] == "4800.00"


def test_an_option_that_was_never_offered_is_refused(cmd: CommandEnv) -> None:
    owner = cmd.env.owner
    command = cmd.run(owner, "fiyat artık 7000")
    for bad in (STUDENT, "pricing.unknown", "", "0"):
        response = cmd.env.call(
            owner, "POST", f"/commands/{command['id']}/clarification", json={"option_id": bad}
        )
        assert response.status_code == 422, bad
        assert response.json()["code"] == "VALIDATION_FAILED"
    assert cmd.get(owner, command["id"])["status"] == "needs_clarification"  # still waiting


def test_a_clarification_can_only_be_answered_while_waiting(cmd: CommandEnv) -> None:
    owner = cmd.env.owner
    command = cmd.run(
        owner, "Aylık üyelik artık 7.000 TL"
    )  # awaiting confirmation, nothing to answer
    response = cmd.env.call(
        owner, "POST", f"/commands/{command['id']}/clarification", json={"option_id": MONTHLY}
    )
    assert response.status_code == 409 and response.json()["code"] == "CONFLICT_STATE"


def test_when_the_model_and_the_parser_disagree_the_owner_picks_the_value(
    cmd: CommandEnv,
) -> None:
    owner = cmd.env.owner
    cmd.provider.queue(
        "interpret_command",
        {
            "interpretation": {
                "type": "knowledge.update_fact",
                "fact_key": MONTHLY,
                "raw_value_text": "7.000 TL",
                "normalized_value": {"kind": "money", "amount": "7.00", "currency": "TRY"},
                "reason": None,
            }
        },
    )
    command = cmd.run(owner, "Aylık üyelik artık 7.000 TL")
    assert command["status"] == "needs_clarification"
    assert command["clarification"]["question_key"] == "command.clarify.which_value"
    assert _options(command) == {"0": "7.000 ₺", "1": "7 ₺"}  # the code's reading is first
    assert cmd.fact(MONTHLY).current_version == 1

    answered = cmd.env.call(
        owner, "POST", f"/commands/{command['id']}/clarification", json={"option_id": "0"}
    ).json()
    assert answered["status"] == "awaiting_confirmation"
    assert answered["approval"]["summary"]["new_formatted"] == "7.000 ₺ / ay"


def test_ac_c7_an_unconfirmed_command_expires_after_30_minutes(cmd: CommandEnv) -> None:
    owner = cmd.env.owner
    command = cmd.run(owner, "Aylık üyelik artık 7.000 TL")
    cmd.env.clock.advance(minutes=29, seconds=59)
    assert cmd.get(owner, command["id"])["status"] == "awaiting_confirmation"

    cmd.env.clock.advance(seconds=2)  # 30 minutes
    expired = cmd.get(owner, command["id"])
    assert expired["status"] == "expired" and expired["approval"]["status"] == "expired"
    assert expired["completed_at"] is not None
    assert cmd.fact(MONTHLY).current_version == 1 and cmd.fact(MONTHLY).value["amount"] == "6000.00"

    late = cmd.decide(owner, command["approval"])  # too late to confirm
    assert late.status_code == 409 and late.json()["code"] == "APPROVAL_EXPIRED"
    assert cmd.fact(MONTHLY).value["amount"] == "6000.00"


def test_the_sweep_expires_confirmations_without_anyone_reading(cmd: CommandEnv) -> None:
    from app.approvals.jobs import enqueue_approval_expiry

    command = cmd.run(cmd.env.owner, "Aylık üyelik artık 7.000 TL")
    cmd.env.clock.advance(minutes=31)
    enqueue_approval_expiry(cmd.env.session, cmd.env.clock)
    cmd.env.session.commit()
    cmd.process()
    stored = cmd.env.session.get(OwnerCommand, command["id"])
    assert stored is not None
    cmd.env.session.refresh(stored)
    assert stored.status == "expired"


def test_an_unanswered_clarification_expires_too(cmd: CommandEnv) -> None:
    from app.commands.jobs import enqueue_command_expiry

    owner = cmd.env.owner
    command = cmd.run(owner, "fiyat artık 7000")
    cmd.env.clock.advance(minutes=31)

    enqueue_command_expiry(cmd.env.session, cmd.env.clock)  # the periodic job
    cmd.env.session.commit()
    cmd.process()
    assert cmd.get(owner, command["id"])["status"] == "expired"
    response = cmd.env.call(
        owner, "POST", f"/commands/{command['id']}/clarification", json={"option_id": MONTHLY}
    )
    assert response.status_code == 409


def test_a_clarification_also_expires_lazily_on_read(cmd: CommandEnv) -> None:
    owner = cmd.env.owner
    command = cmd.run(owner, "fiyat artık 7000")
    cmd.env.clock.advance(minutes=30, seconds=1)
    assert cmd.get(owner, command["id"])["status"] == "expired"


def test_cancelling_a_confirmation_withdraws_it(cmd: CommandEnv) -> None:
    owner = cmd.env.owner
    command = cmd.run(owner, "Aylık üyelik artık 7.000 TL")
    response = cmd.env.call(owner, "POST", f"/commands/{command['id']}/cancel")
    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"
    assert response.json()["approval"]["status"] == "cancelled"

    late = cmd.decide(owner, command["approval"])
    assert late.status_code == 409 and late.json()["code"] == "APPROVAL_ALREADY_DECIDED"
    assert cmd.fact(MONTHLY).current_version == 1


def test_cancelling_a_clarification_and_the_cases_where_cancel_is_refused(cmd: CommandEnv) -> None:
    owner = cmd.env.owner
    waiting = cmd.run(owner, "fiyat artık 7000")
    assert (
        cmd.env.call(owner, "POST", f"/commands/{waiting['id']}/cancel").json()["status"]
        == "cancelled"
    )

    done = cmd.run(owner, "Aylık üyelik ne kadar?")
    assert done["status"] == "completed"
    refused = cmd.env.call(owner, "POST", f"/commands/{done['id']}/cancel")
    assert refused.status_code == 409 and refused.json()["code"] == "CONFLICT_STATE"

    interpreting = cmd.submit(owner, "Aylık üyelik ne kadar?")  # the job has not run yet
    still = cmd.env.call(owner, "POST", f"/commands/{interpreting['id']}/cancel")
    assert still.status_code == 409  # state-machines.md §3: no cancel while interpreting


def test_a_cancelled_command_is_not_resurrected_by_a_late_result(cmd: CommandEnv) -> None:
    """The result of a model call that finishes after the command left ``interpreting`` is
    discarded (agent-runtime.md §2)."""
    from app.ai.schemas import InterpretCommandOutput
    from app.commands import service

    owner = cmd.env.owner
    command = cmd.submit(owner, "Aylık üyelik artık 7.000 TL")
    stored = cmd.env.session.get(OwnerCommand, command["id"])
    assert stored is not None
    stored.status = "cancelled"  # e.g. resolved by something else while the model ran
    cmd.env.session.commit()

    output = InterpretCommandOutput.model_validate(
        {"interpretation": {"type": "query.pending_approvals"}}
    )
    service.finish_interpretation(
        cmd.env.session,
        cmd.env.clock,
        cmd.env.workspace.id,
        stored.id,
        output=output,
        error_code=None,
        agent_run_id=None,
    )
    cmd.env.session.refresh(stored)
    assert stored.status == "cancelled" and stored.result is None
