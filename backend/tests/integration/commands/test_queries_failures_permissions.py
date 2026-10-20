"""Read-only commands, unsupported requests (INV-04), LLM failure paths, permissions."""

from typing import Any

import pytest
from sqlalchemy import select

from app.ai import runtime
from app.ai.models import AgentRun
from app.approvals.models import Approval
from app.integrations.llm.errors import LLMRefusal, LLMTransientError
from tests.integration.commands.conftest import MONTHLY, STUDENT, CommandEnv

# --- read-only commands ---------------------------------------------------------------------


def test_a_fact_question_is_answered_from_the_rendered_fact(cmd: CommandEnv) -> None:
    command = cmd.run(cmd.env.owner, "Aylık üyelik ne kadar?")
    assert command["status"] == "completed" and command["approval"] is None
    assert command["result"]["message_key"] == "command.fact_value"
    assert command["result"]["params"] == {"label": "Aylık üyelik", "display": "6.000 ₺ / ay"}
    assert command["result"]["links"] == [
        {"target": "knowledge", "category": "pricing", "key": MONTHLY}
    ]


def test_an_english_user_gets_english_formatting(cmd: CommandEnv) -> None:
    cmd.env.owner.user.ui_locale = "en"
    cmd.env.session.commit()
    command = cmd.run(cmd.env.owner, "How much is the monthly membership?")
    assert command["result"]["params"]["display"] == "TRY 6,000 / month"


def test_an_unverified_fact_is_described_not_shown_as_current(cmd: CommandEnv) -> None:
    command = cmd.run(cmd.env.owner, "öğrenci aylık üyelik ne kadar")
    assert command["status"] == "completed"
    assert command["result"]["message_key"] == "command.fact_not_usable"
    assert (
        command["result"]["params"]["state"] == "unverified"
    )  # INV-02: no unverified price as fact


def test_pending_approvals_are_listed_and_never_decided(cmd: CommandEnv) -> None:
    owner = cmd.env.owner
    waiting = cmd.run(owner, "Aylık üyelik artık 7.000 TL")
    listing = cmd.run(owner, "bekleyen onaylar neler")
    assert listing["status"] == "completed"
    assert listing["result"]["message_key"] == "command.pending_approvals"
    assert listing["result"]["params"]["count"] == 1
    assert listing["result"]["params"]["items"][0]["id"] == waiting["approval"]["id"]
    assert listing["result"]["links"] == [{"target": "approvals"}]
    assert cmd.env.session.get(Approval, waiting["approval"]["id"]).status == "pending"  # type: ignore[union-attr]


def test_staff_cannot_ask_for_the_activity_summary(cmd: CommandEnv) -> None:
    command = cmd.run(cmd.env.staff, "bugün neler oldu")
    assert command["status"] == "failed" and command["error_code"] == "FORBIDDEN"
    assert command["result"] == {
        "message_key": "command.forbidden",
        "params": {"permission": "reports.view"},
        "links": [],
    }


# --- unsupported by design (INV-04) ---------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "reason", "link"),
    [
        ("gönderiyi şimdi yayınla", "publish", {"target": "content"}),
        ("müşteriye mesaj gönder", "send_message", {"target": "inbox"}),
        ("hepsini onayla", "approve", {"target": "approvals"}),
        ("approve it", "approve", {"target": "approvals"}),
        ("Instagram hesabımı bağla", "manage_account", {"target": "integrations"}),
        ("hava nasıl", "other", None),
    ],
)
def test_unsupported_requests_point_into_the_app(
    cmd: CommandEnv, text: str, reason: str, link: dict[str, str] | None
) -> None:
    command = cmd.run(cmd.env.owner, text)
    assert command["status"] == "unsupported" and command["approval"] is None
    assert command["result"]["message_key"] == "command.unsupported"
    assert command["result"]["params"]["reason"] == reason
    assert command["result"]["params"]["suggestions"][0].startswith("command.suggest.")
    assert command["result"]["links"] == ([link] if link else [])


def test_a_model_that_invents_an_approve_command_cannot_approve_anything(cmd: CommandEnv) -> None:
    """INV-04: even if the model returns a type outside the registry, nothing is approved."""
    owner = cmd.env.owner
    waiting = cmd.run(owner, "Aylık üyelik artık 7.000 TL")
    cmd.provider.queue(
        "interpret_command",
        {"interpretation": {"type": "approvals.approve", "approval_id": waiting["approval"]["id"]}},
    )
    command = cmd.run(owner, "evet onayla")
    assert command["status"] == "unsupported"
    assert command["result"]["params"]["reason"] == "other"
    assert cmd.env.session.get(Approval, waiting["approval"]["id"]).status == "pending"  # type: ignore[union-attr]
    assert cmd.fact(MONTHLY).current_version == 1


def test_free_text_never_approves_a_pending_confirmation(cmd: CommandEnv) -> None:
    owner = cmd.env.owner
    waiting = cmd.run(owner, "Aylık üyelik artık 7.000 TL")
    for text in ("evet", "tamam", "ok", "yes", "onaylıyorum"):
        assert cmd.run(owner, text)["status"] == "unsupported", text
    assert cmd.env.session.get(Approval, waiting["approval"]["id"]).status == "pending"  # type: ignore[union-attr]
    assert cmd.fact(MONTHLY).value["amount"] == "6000.00"


# --- LLM failure paths ----------------------------------------------------------------------


def test_a_transient_error_is_retried_then_the_command_fails_visibly(cmd: CommandEnv) -> None:
    owner = cmd.env.owner
    for _ in range(3):
        cmd.provider.queue("interpret_command", LLMTransientError("down"))
    command = cmd.submit(owner, "Aylık üyelik artık 7.000 TL")

    cmd.process()  # attempt 1 fails, retry scheduled with backoff
    assert cmd.get(owner, command["id"])["status"] == "interpreting"
    cmd.env.clock.advance(minutes=1)
    cmd.process()  # attempt 2
    assert cmd.get(owner, command["id"])["status"] == "interpreting"
    cmd.env.clock.advance(minutes=6)
    cmd.process()  # attempt 3: out of attempts

    failed = cmd.get(owner, command["id"])
    assert failed["status"] == "failed" and failed["error_code"] == "LLM_UNAVAILABLE"
    runs = cmd.env.session.scalars(select(AgentRun)).all()
    assert len(runs) == 3 and {r.error_code for r in runs} == {"LLM_UNAVAILABLE"}
    assert cmd.fact(MONTHLY).current_version == 1


def test_a_transient_error_that_clears_succeeds_on_retry(cmd: CommandEnv) -> None:
    owner = cmd.env.owner
    cmd.provider.queue("interpret_command", LLMTransientError("blip"))
    command = cmd.submit(owner, "Aylık üyelik artık 7.000 TL")
    cmd.process()
    cmd.env.clock.advance(minutes=1)
    cmd.process()
    assert cmd.get(owner, command["id"])["status"] == "awaiting_confirmation"


def test_invalid_output_is_repaired_once_then_fails_with_llm_output_invalid(
    cmd: CommandEnv,
) -> None:
    cmd.provider.queue("interpret_command", "not json")
    cmd.provider.queue("interpret_command", {"interpretation": {"type": "query.fact"}})
    command = cmd.run(cmd.env.owner, "Aylık üyelik artık 7.000 TL")
    assert command["status"] == "failed" and command["error_code"] == "LLM_OUTPUT_INVALID"
    assert len(cmd.provider.calls) == 2  # the call and exactly one repair
    run = cmd.env.session.scalars(select(AgentRun)).one()
    assert (run.status, run.repair_attempts) == ("failed", 1)


def test_one_bad_answer_is_repaired_and_the_command_proceeds(cmd: CommandEnv) -> None:
    cmd.provider.queue("interpret_command", "not json")
    command = cmd.run(cmd.env.owner, "Aylık üyelik artık 7.000 TL")  # the repair call uses the fake
    assert command["status"] == "awaiting_confirmation"
    assert cmd.env.session.scalars(select(AgentRun)).one().repair_attempts == 1


def test_a_refusal_fails_immediately_without_retry(cmd: CommandEnv) -> None:
    cmd.provider.queue("interpret_command", LLMRefusal("no"))
    command = cmd.run(cmd.env.owner, "Aylık üyelik artık 7.000 TL")
    assert command["status"] == "failed" and command["error_code"] == "LLM_REFUSED"
    assert len(cmd.provider.calls) == 1


def test_the_daily_budget_fails_the_command_and_skips_the_model(
    cmd: CommandEnv, limited_budget: Any
) -> None:
    owner = cmd.env.owner
    with limited_budget(1):
        assert cmd.run(owner, "Aylık üyelik ne kadar?")["status"] == "completed"
        blocked = cmd.run(owner, "Aylık üyelik ne kadar?")
    assert blocked["status"] == "failed" and blocked["error_code"] == "LLM_BUDGET_EXCEEDED"
    assert len(cmd.provider.calls) == 1
    cmd.env.clock.advance(hours=25)
    assert cmd.run(owner, "Aylık üyelik ne kadar?")["status"] == "completed"
    assert runtime.get_provider() is cmd.provider


def test_every_execution_has_an_agent_run(cmd: CommandEnv) -> None:
    cmd.run(cmd.env.owner, "Aylık üyelik ne kadar?")
    cmd.run(cmd.env.owner, "hava nasıl")
    runs = cmd.env.session.scalars(select(AgentRun)).all()
    assert len(runs) == 2 and all(r.is_fake and r.task == "interpret_command" for r in runs)


# --- visibility and permissions -------------------------------------------------------------


def test_commands_are_private_to_the_member_who_typed_them(cmd: CommandEnv) -> None:
    command = cmd.run(cmd.env.owner, "Aylık üyelik artık 7.000 TL")
    for role in (cmd.env.manager, cmd.env.staff):
        assert cmd.env.call(role, "GET", f"/commands/{command['id']}").status_code == 404
        assert cmd.env.call(role, "POST", f"/commands/{command['id']}/cancel").status_code == 404
        answer = {"option_id": MONTHLY}
        assert (
            cmd.env.call(
                role, "POST", f"/commands/{command['id']}/clarification", json=answer
            ).status_code
            == 404
        )
    assert cmd.env.call(cmd.env.manager, "GET", "/commands").json()["items"] == []
    assert [c["id"] for c in cmd.env.call(cmd.env.owner, "GET", "/commands").json()["items"]] == [
        command["id"]
    ]


def test_input_validation(cmd: CommandEnv) -> None:
    owner = cmd.env.owner
    for text in ("", "   ", "x" * 1001):
        response = cmd.env.call(
            owner, "POST", "/commands", json={"text": text, "client_request_id": "r"}
        )
        assert response.status_code == 422, text[:10]
        assert response.json()["code"] == "VALIDATION_FAILED"
    blank_id = cmd.env.call(
        owner, "POST", "/commands", json={"text": "x", "client_request_id": " "}
    )
    assert blank_id.status_code == 422
    extra = cmd.env.call(
        owner, "POST", "/commands", json={"text": "x", "client_request_id": "r", "role": "owner"}
    )
    assert extra.status_code == 422  # unknown fields are refused


def test_the_command_text_is_never_in_the_job_payload_or_the_audit_log(cmd: CommandEnv) -> None:
    from app.audit import service as audit
    from app.jobs.models import Job

    cmd.submit(cmd.env.owner, "Aylık üyelik artık 7.000 TL")
    job = cmd.env.session.scalars(select(Job).where(Job.job_type == "interpret_command")).one()
    assert set(job.payload) == {"command_id"}
    entries = audit.list_entries(cmd.env.session, workspace_id=cmd.env.workspace.id)
    assert "7.000" not in str([e.metadata_ for e in entries])


def test_the_student_price_stays_unverified_until_the_owner_verifies_it(cmd: CommandEnv) -> None:
    """Updating an unverified fact by command verifies it (the owner is authoritative)."""
    owner = cmd.env.owner
    command = cmd.run(owner, "öğrenci aylık üyelik 5000 TL oldu")
    assert command["status"] == "awaiting_confirmation"
    cmd.decide(owner, command["approval"])
    fact = cmd.fact(STUDENT)
    assert fact.status == "verified" and fact.value["amount"] == "5000.00"
