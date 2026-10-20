"""P4-09: approved answers, and how drafts and answers react when a fact they quote changes.

AC-C3 (the next draft carries the new price), AC-C5 (a pending draft is superseded and redrafted,
a sent message is unchanged), INV-02 (no literal values in an approved answer)."""

import uuid
from datetime import timedelta

import pytest
from sqlalchemy import select

from app.inbox.models import ReplyDraft
from app.knowledge import impact
from app.knowledge.models import ApprovedAnswer, FactReference
from tests.factories import create_workspace, money
from tests.helpers.gym import MONTHLY, PHONE
from tests.integration.inbox.conftest import InboxEnv

PRICE_Q = "Aylık üyelik ne kadar?"
PARKING = {
    "title": "Otopark",
    "intent": "faq",
    "example_questions": ["Otopark var mı?", "Park yeri var mı?"],
    "answer_template": "Evet, binanın önünde otopark var. Bize ulaşın: {{fact:contact.phone}}",
    "language": "tr",
}


@pytest.fixture
def gym(inbox: InboxEnv):  # type: ignore[no-untyped-def]
    return inbox.seed_facts()


def call(inbox: InboxEnv, role: str, method: str, path: str, **kwargs):  # type: ignore[no-untyped-def]
    return inbox.env.call(getattr(inbox.env, role), method, path, **kwargs)


def create(inbox: InboxEnv, body: dict | None = None, role: str = "owner"):  # type: ignore[no-untyped-def,type-arg]
    return call(inbox, role, "POST", "/approved-answers", json=body or PARKING)


def change_price(inbox: InboxEnv, gym, amount: str = "7000", role: str = "owner"):  # type: ignore[no-untyped-def]
    fact = gym[MONTHLY]
    inbox.session.refresh(fact)
    return call(
        inbox,
        role,
        "PATCH",
        f"/facts/{fact.id}",
        json={"expected_version": fact.current_version, "value": money(amount)},
    )


# --- approved answers: the API -------------------------------------------------------------------


def test_the_owner_creates_an_answer_that_quotes_a_fact_by_placeholder(
    inbox: InboxEnv, gym
) -> None:
    response = create(inbox)
    assert response.status_code == 201, response.text
    body = response.json()
    assert (body["status"], body["version"], body["language"]) == ("active", 1, "tr")
    assert body["answer_template"].endswith("{{fact:contact.phone}}")
    references = inbox.session.scalars(
        select(FactReference).where(FactReference.referrer_id == uuid.UUID(body["id"]))
    ).all()
    assert [(r.referrer_type, r.fact_id) for r in references] == [
        ("approved_answer", gym[PHONE].id)
    ]


def test_every_member_can_read_but_only_owners_and_managers_write(inbox: InboxEnv, gym) -> None:
    assert create(inbox, role="staff").status_code == 403
    assert create(inbox, role="manager").status_code == 201
    listed = call(inbox, "staff", "GET", "/approved-answers")
    assert listed.status_code == 200 and len(listed.json()["items"]) == 1


@pytest.mark.parametrize(
    "template",
    [
        "Aylık üyelik 6.000 ₺",
        "Bizi arayın: 0555 000 00 00",
        "Detaylar: https://example.com/fiyat",
        "Hafta içi 07:00 - 23:00 açığız",
        "%20 indirim yapıyoruz",
    ],
)
def test_a_literal_critical_value_is_refused_with_the_offending_spans(
    inbox: InboxEnv, gym, template: str
) -> None:
    response = create(inbox, {**PARKING, "answer_template": template})
    assert response.status_code == 422
    (error,) = response.json()["errors"]
    assert error["code"] == "LITERAL_VALUE" and error["field"] == "answer_template"
    assert error["params"]["issues"], "the offending spans are listed"
    assert inbox.session.scalars(select(ApprovedAnswer)).all() == []


def test_a_placeholder_for_a_fact_that_does_not_exist_is_refused(inbox: InboxEnv, gym) -> None:
    response = create(inbox, {**PARKING, "answer_template": "Fiyat: {{fact:pricing.invented}}"})
    assert response.status_code == 422
    assert response.json()["errors"][0]["code"] == "UNKNOWN_FACT"


@pytest.mark.parametrize(
    "patch",
    [
        {"intent": "nonsense"},
        {"language": "de"},
        {"title": ""},
        {"example_questions": []},
        {"answer_template": ""},
        {"answer_template": "a" * 901},
    ],
)
def test_invalid_answers_are_refused(inbox: InboxEnv, gym, patch: dict) -> None:  # type: ignore[type-arg]
    assert create(inbox, {**PARKING, **patch}).status_code == 422


def test_editing_an_answer_checks_the_new_wording_and_bumps_the_version(
    inbox: InboxEnv, gym
) -> None:
    answer = create(inbox).json()
    path = f"/approved-answers/{answer['id']}"
    bad = call(
        inbox, "owner", "PATCH", path, json={"expected_version": 1, "answer_template": "6.000 ₺"}
    )
    assert bad.status_code == 422
    stale = call(inbox, "owner", "PATCH", path, json={"expected_version": 9, "title": "Park"})
    assert stale.status_code == 409 and stale.json()["code"] == "VERSION_CONFLICT"
    ok = call(
        inbox, "owner", "PATCH", path,
        json={"expected_version": 1, "answer_template": "Evet, otopark var.", "title": "Park"},
    )  # fmt: skip
    assert ok.status_code == 200 and ok.json()["version"] == 2 and ok.json()["title"] == "Park"
    # the facts it quotes follow the new wording
    assert (
        inbox.session.scalars(
            select(FactReference).where(FactReference.referrer_type == "approved_answer")
        ).all()
        == []
    )


def test_an_archived_answer_is_not_offered_to_the_model(inbox: InboxEnv, gym, provider) -> None:  # type: ignore[no-untyped-def]
    answer = create(inbox).json()
    call(
        inbox,
        "owner",
        "PATCH",
        f"/approved-answers/{answer['id']}",
        json={"expected_version": 1, "status": "archived"},
    )
    inbox.ask("Otopark var mı?")
    assert answer["id"] not in provider.calls[0].messages[0].content


def test_answers_of_another_workspace_are_not_found(inbox: InboxEnv, gym) -> None:
    other = create_workspace(inbox.session, name="Other")
    base = f"/api/v1/workspaces/{other.id}"
    assert inbox.env.owner.client.get(f"{base}/approved-answers").status_code == 404
    assert (
        call(
            inbox,
            "owner",
            "PATCH",
            f"/approved-answers/{uuid.uuid4()}",
            json={"expected_version": 1},
        ).status_code
        == 404
    )


# --- approved answers in drafting ----------------------------------------------------------------


def test_a_matching_answer_becomes_the_draft_rendered_from_facts(inbox: InboxEnv, gym) -> None:
    create(inbox)
    draft = inbox.ask("Otopark var mı?")
    assert draft.source == "approved_answer"
    assert draft.text == "Evet, binanın önünde otopark var. Bize ulaşın: 0555 000 00 00"
    assert (draft.status, draft.decision_reasons) == (
        "pending_approval",
        ["POLICY_REQUIRES_APPROVAL"],
    )
    assert draft.validation["passed"] is True


# --- saving a sent reply as an answer ---------------------------------------------------


def sent_price_reply(inbox: InboxEnv):  # type: ignore[no-untyped-def]
    draft = inbox.ask(PRICE_Q)
    inbox.approve_and_send(draft)
    return next(m for m in inbox.messages() if m.direction == "outbound")


def test_a_sent_reply_becomes_an_answer_with_placeholders_instead_of_values(
    inbox: InboxEnv, gym
) -> None:
    message = sent_price_reply(inbox)
    response = call(inbox, "owner", "POST", f"/approved-answers/from-message/{message.id}", json={})
    assert response.status_code == 201, response.text
    body = response.json()
    assert (
        body["answer_template"]
        == "Merhaba! Aylık üyelik ücretimiz {{fact:pricing.membership_monthly}}."
    )
    assert "6.000" not in body["answer_template"]
    assert body["example_questions"] == [PRICE_Q]
    assert (body["intent"], body["language"]) == ("pricing", "tr")
    assert body["created_from_message_id"] == str(message.id)


def test_the_automatic_reply_notice_is_not_saved_into_the_answer(inbox: InboxEnv, gym) -> None:
    call(
        inbox,
        "owner",
        "PUT",
        "/automation-policies",
        json={"items": [{"action_class": "reply.pricing", "mode": "auto"}]},
    )
    inbox.ask(PRICE_Q)
    message = next(m for m in inbox.messages() if m.direction == "outbound")
    assert "otomatik" in (message.text or "")
    body = call(
        inbox, "owner", "POST", f"/approved-answers/from-message/{message.id}", json={}
    ).json()
    assert "otomatik" not in body["answer_template"]
    assert body["answer_template"].endswith("{{fact:pricing.membership_monthly}}.")


def test_a_hand_typed_reply_with_a_literal_value_must_be_fixed_before_saving(
    inbox: InboxEnv, gym
) -> None:
    inbox.deliver_and_process(PRICE_Q)
    typed = call(
        inbox, "owner", "POST", f"/conversations/{inbox.conversation().id}/replies",
        json={"text": "Aylık üyelik 6.000 ₺", "client_request_id": "r-1"},
    )  # fmt: skip
    assert typed.status_code == 201
    inbox.process()
    message = next(m for m in inbox.messages() if m.direction == "outbound")
    refused = call(inbox, "owner", "POST", f"/approved-answers/from-message/{message.id}", json={})
    assert refused.status_code == 422 and refused.json()["errors"][0]["code"] == "LITERAL_VALUE"
    fixed = call(
        inbox, "owner", "POST", f"/approved-answers/from-message/{message.id}",
        json={"answer_template": "Aylık üyelik {{fact:pricing.membership_monthly}}"},
    )  # fmt: skip
    assert fixed.status_code == 201


def test_only_an_outbound_message_can_be_saved(inbox: InboxEnv, gym) -> None:
    inbox.deliver_and_process(PRICE_Q)
    inbound = inbox.messages()[0]
    response = call(inbox, "owner", "POST", f"/approved-answers/from-message/{inbound.id}", json={})
    assert response.status_code == 409
    missing = call(
        inbox, "owner", "POST", f"/approved-answers/from-message/{uuid.uuid4()}", json={}
    )
    assert missing.status_code == 404
    assert (
        call(
            inbox, "staff", "POST", f"/approved-answers/from-message/{inbound.id}", json={}
        ).status_code
        == 403
    )


# --- a fact changes ------------------------------------------------------------------------------


def test_the_impact_report_counts_the_drafts_and_answers_that_quote_the_fact(
    inbox: InboxEnv, gym
) -> None:
    inbox.ask(PRICE_Q)
    call(
        inbox,
        "owner",
        "POST",
        "/approved-answers",
        json={**PARKING, "answer_template": "Aylık {{fact:pricing.membership_monthly}}"},
    )
    report = impact.analyze_impact(inbox.session, inbox.env.ctx(inbox.env.owner), gym[MONTHLY].id)
    counts = {i["referrer_type"]: i["counts"] for i in report.to_dict()["items"]}
    assert counts == {"reply_draft": {"pending_approval": 1}, "approved_answer": {"active": 1}}


def test_ac_c5_a_pending_draft_is_superseded_and_drafted_again_with_the_new_price(
    inbox: InboxEnv, gym
) -> None:
    old = inbox.ask(PRICE_Q)
    assert "6.000" in (old.text or "")
    assert change_price(inbox, gym).status_code == 200

    old = inbox.refreshed(old)
    assert (old.status, old.failure_code) == ("superseded", "FACT_CHANGED")
    assert inbox.approval_of(old).status == "cancelled"
    inbox.process()  # the redraft

    new = inbox.draft()
    assert new is not None and new.id != old.id
    assert new.status == "pending_approval"
    assert new.text == "Merhaba! Aylık üyelik ücretimiz 7.000 ₺ / ay."  # AC-C3
    assert "6.000" not in (new.text or "")
    reference = inbox.session.scalars(
        select(FactReference).where(FactReference.referrer_id == new.id)
    ).one()
    assert reference.fact_version == 2
    assert inbox.approval_of(new).status == "pending"  # a fresh approval for the new text


def test_a_queued_draft_is_cancelled_and_drafted_again(inbox: InboxEnv, gym) -> None:
    inbox.deliver_and_process(PRICE_Q)
    draft = inbox.make_draft("queued", with_approval=False)
    inbox.session.add(
        FactReference(
            workspace_id=inbox.env.workspace.id,
            fact_id=gym[MONTHLY].id,
            fact_version=1,
            referrer_type="reply_draft",
            referrer_id=draft.id,
        )
    )
    inbox.session.commit()
    assert change_price(inbox, gym).status_code == 200
    refreshed = inbox.refreshed(draft)
    assert (refreshed.status, refreshed.failure_code) == ("cancelled", "FACT_CHANGED")
    inbox.draft_now()  # one draft job per conversation: it runs when the debounce is over
    new = inbox.draft()
    assert new is not None and new.id != draft.id and "7.000" in (new.text or "")


def test_ac_c5_a_message_that_was_already_sent_is_unchanged(inbox: InboxEnv, gym) -> None:
    sent = sent_price_reply(inbox)
    draft = inbox.draft()
    assert draft is not None and draft.status == "sent"
    assert change_price(inbox, gym).status_code == 200
    inbox.process()
    after = inbox.refreshed(draft)
    assert after.status == "sent" and after.text == draft.text
    assert "6.000" in (sent.text or "")
    inbox.session.expire_all()
    assert inbox.session.get(type(sent), sent.id).text == sent.text  # type: ignore[union-attr]
    assert len(inbox.sim_sent()) == 1
    assert inbox.draft().id == draft.id  # no new draft was made  # type: ignore[union-attr]


def test_a_draft_that_does_not_quote_the_fact_is_left_alone(inbox: InboxEnv, gym) -> None:
    draft = inbox.ask("Çalışma saatleriniz nedir?")
    assert change_price(inbox, gym).status_code == 200
    assert inbox.refreshed(draft).status == "pending_approval"
    assert inbox.approval_of(draft).status == "pending"


def test_a_draft_that_waits_for_a_person_is_not_touched_either(inbox: InboxEnv, gym) -> None:
    draft = inbox.ask("Bu bir rezalet, şikayetçiyim")
    assert change_price(inbox, gym).status_code == 200
    assert inbox.refreshed(draft).status == "needs_human"


def test_a_price_change_by_a_staff_proposal_changes_nothing_yet(inbox: InboxEnv, gym) -> None:
    """Staff can only contest a verified value (a candidate): drafts keep the verified price."""
    draft = inbox.ask(PRICE_Q)
    response = change_price(inbox, gym, "5500", role="staff")
    assert response.status_code == 202  # accepted as a proposal for the owner, not applied
    assert response.json()["relation"] == "contest"
    assert inbox.refreshed(draft).status == "pending_approval"
    assert inbox.approval_of(draft).status == "pending"


def test_a_price_change_marks_the_answers_that_quote_it_for_review(inbox: InboxEnv, gym) -> None:
    created = call(
        inbox, "owner", "POST", "/approved-answers",
        json={**PARKING, "answer_template": "Aylık üyelik {{fact:pricing.membership_monthly}}"},
    ).json()  # fmt: skip
    parking = create(inbox).json()  # quotes the phone, not the price
    assert change_price(inbox, gym).status_code == 200
    inbox.session.expire_all()
    assert inbox.session.get(ApprovedAnswer, uuid.UUID(created["id"])).status == "needs_review"  # type: ignore[union-attr]
    assert inbox.session.get(ApprovedAnswer, uuid.UUID(parking["id"])).status == "active"  # type: ignore[union-attr]
    # an answer under review is still offered, and editing it puts it back in service
    edited = call(
        inbox,
        "owner",
        "PATCH",
        f"/approved-answers/{created['id']}",
        json={
            "expected_version": 1,
            "answer_template": "Aylık üyelik ücretimiz {{fact:pricing.membership_monthly}}",
        },
    )
    assert edited.json()["status"] == "active"


def test_an_answer_under_review_is_still_used_for_drafting(inbox: InboxEnv, gym, provider) -> None:  # type: ignore[no-untyped-def]
    created = call(
        inbox,
        "owner",
        "POST",
        "/approved-answers",
        json={
            **PARKING,
            "answer_template": "Üyelik {{fact:pricing.membership_monthly}} (otopark dahil)",
        },
    ).json()
    change_price(inbox, gym)
    draft = inbox.ask("Otopark var mı?")
    assert draft.source == "approved_answer"
    assert "7.000" in (draft.text or "")  # rendered from the current value
    assert created["id"] in provider.calls[0].messages[0].content


def test_the_same_change_twice_does_not_draft_twice(inbox: InboxEnv, gym) -> None:
    inbox.ask(PRICE_Q)
    change_price(inbox, gym, "7000")
    inbox.clock.advance(timedelta(seconds=1))
    change_price(inbox, gym, "7500")
    inbox.process()
    open_drafts = [
        d for d in inbox.session.scalars(select(ReplyDraft)) if d.status == "pending_approval"
    ]
    assert len(open_drafts) == 1 and "7.500" in (open_drafts[0].text or "")
