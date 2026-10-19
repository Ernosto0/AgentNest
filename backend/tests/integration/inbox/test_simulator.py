"""P4-10: the developer simulator and its API. The demo scenario of the phase, end to end."""

import uuid
from collections.abc import Callable
from datetime import timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.cli import main as cli_main
from app.demo import simulator
from app.inbox.models import Conversation, InboundEvent, Message
from app.integrations.instagram.models import SimFailureRule, SimInboundMessage
from tests.factories import create_workspace, login
from tests.integration.inbox.conftest import InboxEnv


@pytest.fixture
def gym(inbox: InboxEnv):  # type: ignore[no-untyped-def]
    inbox.env.workspace.reply_languages = ["tr", "en"]
    inbox.session.commit()
    return inbox.seed_facts()


def dev(inbox: InboxEnv, method: str, path: str, role: str = "owner", **kwargs: Any) -> Any:
    who = getattr(inbox.env, role)
    return who.client.request(method, f"/api/v1/dev{path}", headers=who.headers, **kwargs)


def ws(inbox: InboxEnv, path: str) -> str:
    return f"/workspaces/{inbox.env.workspace.id}{path}"


def simulate(inbox: InboxEnv, script: str) -> Any:
    response = dev(
        inbox, "POST", ws(inbox, "/simulate/customer-message"), json={"script_id": script}
    )
    assert response.status_code == 200, response.text
    inbox.process()
    inbox.draft_now()
    return response


def only_draft(inbox: InboxEnv, customer: str):  # type: ignore[no-untyped-def]
    inbox.session.expire_all()
    return inbox.draft(simulator.customer_id_for(customer))


# --- the scripts ---------------------------------------------------------------------------------


def test_the_scripts_cover_the_demo_cases() -> None:
    scripts = {s.id: s for s in simulator.load_scripts()}
    assert {
        "price", "hours", "location", "trial", "complaint", "refund", "discount", "injection",
        "english_tourist", "russian", "photo_only",
    } <= set(scripts)  # fmt: skip
    assert scripts["photo_only"].text is None and scripts["photo_only"].attachments
    assert all(s.label.keys() >= {"tr", "en"} for s in scripts.values())


def test_the_scripts_are_listed_for_a_signed_in_user(inbox: InboxEnv) -> None:
    response = dev(inbox, "GET", "/scripts", role="staff")
    assert response.status_code == 200
    assert "price" in {s["id"] for s in response.json()}


def test_customer_ids_are_stable_and_provider_like() -> None:
    assert simulator.customer_id_for("Ayşe") == simulator.customer_id_for("Ayşe")
    assert simulator.customer_id_for("Ayşe") == "sim-ayse"
    assert simulator.customer_id_for("Sarah Jones") == "sim-sarah-jones"
    assert simulator.customer_id_for("!!!") == "sim-customer"


# --- the demo scenario ---------------------------------------------------------------------------


def test_demo_price_question_to_a_sent_simulated_reply(inbox: InboxEnv, gym) -> None:
    simulate(inbox, "price")
    draft = only_draft(inbox, "Ayşe")
    assert draft is not None and draft.status == "pending_approval"
    assert draft.text == "Merhaba! Aylık üyelik ücretimiz 6.000 ₺ / ay."
    conversation = inbox.conversation(simulator.customer_id_for("Ayşe"))
    assert conversation.customer_handle == "Ayşe" and conversation.is_simulated

    assert inbox.decide(draft).status_code == 200
    inbox.process()
    assert inbox.refreshed(draft).status == "sent"
    (sent,) = inbox.sim_sent()
    assert sent.recipient_id == "sim-ayse" and sent.text == draft.text


def test_demo_the_complaint_is_handed_to_a_person_with_reasons(inbox: InboxEnv, gym) -> None:
    simulate(inbox, "complaint")
    draft = only_draft(inbox, "Burak")
    assert draft is not None and draft.status == "needs_human"
    assert "INTENT_COMPLAINT" in draft.decision_reasons and draft.text is None
    assert inbox.conversation(simulator.customer_id_for("Burak")).attention == "needs_human"


@pytest.mark.parametrize(
    ("script", "customer", "reason"),
    [
        ("refund", "Selin", "FLAG_REFUND"),
        ("discount", "Elif", "FLAG_DISCOUNT"),
        ("injection", "Kerem", "FLAG_DISCOUNT"),
        ("russian", "Ivan", "LANGUAGE_UNSUPPORTED"),
        ("photo_only", "Deniz", "ATTACHMENT_ONLY"),
    ],
)
def test_demo_every_escalation_script_ends_with_a_person(
    inbox: InboxEnv, gym, script: str, customer: str, reason: str
) -> None:
    simulate(inbox, script)
    draft = only_draft(inbox, customer)
    assert draft is not None and draft.status == "needs_human"
    assert reason in draft.decision_reasons
    assert draft.text is None and draft.approval_id is None


@pytest.mark.parametrize(
    ("script", "customer", "fragment"),
    [
        ("hours", "Mehmet", "Çalışma saatlerimiz"),
        ("location", "Zeynep", "Adresimiz"),
        ("trial", "Can", "deneme seansı ücretsiz"),
        ("english_tourist", "Sarah", "Our monthly membership price is"),
    ],
)
def test_demo_the_answerable_scripts_get_grounded_drafts(
    inbox: InboxEnv, gym, script: str, customer: str, fragment: str
) -> None:
    simulate(inbox, script)
    draft = only_draft(inbox, customer)
    assert draft is not None and draft.status == "pending_approval"
    assert fragment.lower() in (draft.text or "").lower()
    assert draft.validation["passed"] is True


def test_demo_a_price_change_alters_the_next_draft(inbox: InboxEnv, gym) -> None:
    from tests.factories import money
    from tests.helpers.gym import MONTHLY

    first = (simulate(inbox, "price"), only_draft(inbox, "Ayşe"))[1]
    assert first is not None and "6.000" in (first.text or "")
    fact = gym[MONTHLY]
    inbox.env.call(
        inbox.env.owner, "PATCH", f"/facts/{fact.id}",
        json={"expected_version": 1, "value": money("7000")},
    )  # fmt: skip
    simulate(inbox, "english_tourist")
    inbox.clock.advance(timedelta(seconds=30))
    simulate(inbox, "price")
    latest = only_draft(inbox, "Ayşe")
    assert latest is not None and "7.000" in (latest.text or "")
    assert "6.000" not in (latest.text or "")


def test_demo_timeout_after_success_checks_then_the_echo_confirms(inbox: InboxEnv, gym) -> None:
    simulate(inbox, "price")
    draft = only_draft(inbox, "Ayşe")
    assert draft is not None
    rule = dev(
        inbox, "POST", ws(inbox, "/failure-rules"),
        json={"operation": "send", "mode": "timeout_after_success"},
    )  # fmt: skip
    assert rule.status_code == 201
    assert inbox.decide(draft).status_code == 200
    inbox.process()
    assert inbox.refreshed(draft).status == "outcome_unknown"  # "Kontrol ediliyor…"
    inbox.clock.advance(timedelta(seconds=6))
    inbox.process()  # the echo arrives
    assert inbox.refreshed(draft).status == "sent"
    assert len(inbox.sim_sent()) == 1


def test_demo_an_answer_typed_in_the_instagram_app_replaces_the_draft(inbox: InboxEnv, gym) -> None:
    simulate(inbox, "price")
    draft = only_draft(inbox, "Ayşe")
    conversation = inbox.conversation(simulator.customer_id_for("Ayşe"))
    inbox.clock.advance(timedelta(seconds=20))
    response = dev(
        inbox, "POST", ws(inbox, "/simulate/owner-native-reply"),
        json={"conversation_id": str(conversation.id), "text": "Merhaba, size yazıyorum"},
    )  # fmt: skip
    assert response.status_code == 200
    inbox.process()
    assert draft is not None
    refreshed = inbox.refreshed(draft)
    assert (refreshed.status, refreshed.failure_code) == ("superseded", "OWNER_REPLIED_NATIVELY")
    assert inbox.sim_sent() == []  # nothing went through the API


# --- plumbing ------------------------------------------------------------------------------------


def test_the_window_is_opened_in_the_simulator_and_the_event_is_real(inbox: InboxEnv, gym) -> None:
    simulate(inbox, "price")
    inbox.session.expire_all()
    (event,) = inbox.session.scalars(select(InboundEvent)).all()
    assert event.is_simulated and event.provider_kind == "mock" and event.status == "processed"
    (opened,) = inbox.session.scalars(select(SimInboundMessage)).all()
    assert opened.sender_id == "sim-ayse" and opened.received_at == inbox.clock.now() - timedelta(
        seconds=8
    )
    (message,) = inbox.session.scalars(select(Message)).all()
    assert message.external_message_id == opened.mid


def test_the_same_customer_keeps_one_conversation(inbox: InboxEnv, gym) -> None:
    for text in ("Merhaba", "Aylık üyelik ne kadar?"):
        response = dev(
            inbox, "POST", ws(inbox, "/simulate/customer-message"),
            json={"customer_alias": "Ayşe", "text": text},
        )  # fmt: skip
        assert response.status_code == 200
        inbox.clock.advance(timedelta(seconds=2))
        inbox.process()
    inbox.session.expire_all()
    assert len(inbox.session.scalars(select(Conversation)).all()) == 1


def test_a_free_text_message_needs_a_customer_and_text(inbox: InboxEnv, gym) -> None:
    for body in (
        {},
        {"customer_alias": "Ayşe"},
        {"text": "x"},
        {"customer_alias": "A", "text": " "},
    ):
        response = dev(inbox, "POST", ws(inbox, "/simulate/customer-message"), json=body)
        assert response.status_code == 422
    unknown = dev(
        inbox, "POST", ws(inbox, "/simulate/customer-message"), json={"script_id": "nope"}
    )
    assert unknown.status_code == 404


def test_without_a_simulated_account_nothing_can_be_simulated(inbox: InboxEnv, gym) -> None:
    inbox.account.status = "disconnected"
    inbox.session.commit()
    response = dev(
        inbox, "POST", ws(inbox, "/simulate/customer-message"), json={"script_id": "price"}
    )
    assert response.status_code == 409 and response.json()["code"] == "ACCOUNT_NOT_CONNECTED"


def test_only_the_owner_uses_the_workspace_tools(inbox: InboxEnv, gym) -> None:
    for role in ("manager", "staff"):
        path = ws(inbox, "/simulate/customer-message")
        assert dev(inbox, "POST", path, role=role, json={"script_id": "price"}).status_code == 403
        assert dev(inbox, "GET", ws(inbox, "/failure-rules"), role=role).status_code == 403


def test_other_workspaces_are_not_reachable(inbox: InboxEnv, gym) -> None:
    other = create_workspace(inbox.session, name="Other")
    response = dev(
        inbox,
        "POST",
        f"/workspaces/{other.id}/simulate/customer-message",
        json={"script_id": "price"},
    )
    assert response.status_code == 404
    assert dev(inbox, "GET", f"/workspaces/{other.id}/failure-rules").status_code == 404


def test_failure_rules_can_be_added_listed_and_removed(inbox: InboxEnv, gym) -> None:
    created = dev(
        inbox, "POST", ws(inbox, "/failure-rules"),
        json={"operation": "send", "mode": "rate_limited", "remaining": 2, "retry_after_s": 30},
    ).json()  # fmt: skip
    assert (created["operation"], created["mode"], created["remaining"]) == (
        "send",
        "rate_limited",
        2,
    )
    listed = dev(inbox, "GET", ws(inbox, "/failure-rules")).json()["items"]
    assert [r["id"] for r in listed] == [created["id"]]
    assert dev(inbox, "DELETE", ws(inbox, f"/failure-rules/{created['id']}")).status_code == 204
    assert dev(inbox, "GET", ws(inbox, "/failure-rules")).json()["items"] == []
    assert dev(inbox, "DELETE", ws(inbox, f"/failure-rules/{uuid.uuid4()}")).status_code == 404
    inbox.session.expire_all()
    assert inbox.session.scalars(select(SimFailureRule)).all() == []


@pytest.mark.parametrize(
    "body",
    [
        {"operation": "send", "mode": "explode"},
        {"operation": "teleport", "mode": "transient"},
        {"operation": "send", "mode": "transient", "remaining": 0},
        {"operation": "send", "mode": "transient", "extra": 1},
    ],
)
def test_invalid_failure_rules_are_rejected(inbox: InboxEnv, gym, body: dict) -> None:  # type: ignore[type-arg]
    assert dev(inbox, "POST", ws(inbox, "/failure-rules"), json=body).status_code == 422


def test_run_due_jobs_runs_what_is_due_and_the_job_list_shows_it(inbox: InboxEnv, gym) -> None:
    dev(inbox, "POST", ws(inbox, "/simulate/customer-message"), json={"script_id": "price"})
    ran = dev(inbox, "POST", "/jobs/run-due").json()
    assert ran["ran"] >= 1  # the inbound event
    inbox.clock.advance(timedelta(seconds=9))
    assert dev(inbox, "POST", "/jobs/run-due").json()["ran"] >= 1  # the draft job
    jobs = dev(inbox, "GET", "/jobs").json()["items"]
    assert {"process_inbound_event", "draft_reply"} <= {j["job_type"] for j in jobs}
    queued = dev(inbox, "GET", "/jobs?status=succeeded").json()["items"]
    assert queued and all(j["status"] == "succeeded" for j in queued)


def test_the_dev_tools_do_not_exist_when_they_are_switched_off(
    inbox: InboxEnv, build_app: Callable[..., Any]
) -> None:
    app = build_app(demo_tools_enabled=False)
    with TestClient(app) as client:
        login(client, inbox.env.owner.user)
        assert client.get("/api/v1/dev/scripts").status_code == 404


def test_the_dev_routes_need_a_session_and_a_csrf_token(inbox: InboxEnv, gym) -> None:
    anonymous = inbox.webhook_client
    assert anonymous.get("/api/v1/dev/scripts").status_code == 401
    no_csrf = inbox.env.owner.client.post(
        f"/api/v1/dev{ws(inbox, '/simulate/customer-message')}", json={"script_id": "price"}
    )
    assert no_csrf.status_code == 403


# --- the command line ----------------------------------------------------------------------------


def test_the_cli_refuses_clearly_without_what_it_needs(capsys: pytest.CaptureFixture[str]) -> None:
    assert (
        cli_main(["simulate-message", "--workspace", "no-such-workspace", "--script", "price"]) == 1
    )
    assert "no workspace" in capsys.readouterr().err


def test_the_cli_parser_knows_the_simulator_commands() -> None:
    from app.cli import build_parser

    parser = build_parser()
    assert (
        parser.parse_args(["simulate-message", "--workspace", "w", "--script", "price"]).script
        == "price"
    )
    assert parser.parse_args(["run-due-jobs"]).command == "run-due-jobs"
    assert (
        parser.parse_args(
            ["simulate-native-reply", "--workspace", "w", "--conversation", "c", "--text", "t"]
        ).text
        == "t"
    )
