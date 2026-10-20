"""P5-00 Q5: staff see where the approval of a reply stands (pending, approved, rejected,
expired, with who decided and the note) without being able to decide it."""

import uuid
from datetime import timedelta

import pytest

from tests.integration.inbox.conftest import InboxEnv

PRICE_Q = "Aylık üyelik ne kadar?"


@pytest.fixture
def gym(inbox: InboxEnv):  # type: ignore[no-untyped-def]
    return inbox.seed_facts()


def staff_view(inbox: InboxEnv, draft_id: uuid.UUID) -> dict:  # type: ignore[type-arg]
    """The draft as staff read it, from the draft route and from the conversation detail."""
    by_route = inbox.env.call(inbox.env.staff, "GET", f"/reply-drafts/{draft_id}")
    assert by_route.status_code == 200, by_route.text
    conversation_id = by_route.json()["conversation_id"]
    detail = inbox.env.call(inbox.env.staff, "GET", f"/conversations/{conversation_id}")
    assert detail.status_code == 200, detail.text
    body = detail.json()
    drafts = [body["open_draft"], *body["recent_drafts"]]
    in_detail = next(d for d in drafts if d and d["id"] == str(draft_id))
    assert in_detail["approval_state"] == by_route.json()["approval_state"]
    return by_route.json()


def test_a_pending_approval_shows_its_expiry_and_nobody_decided(inbox: InboxEnv, gym) -> None:
    draft = inbox.ask(PRICE_Q)
    approval = inbox.approval_of(draft)
    state = staff_view(inbox, draft.id)["approval_state"]
    assert state["status"] == "pending"
    assert state["expires_at"].startswith(approval.expires_at.strftime("%Y-%m-%dT%H:%M"))
    assert state["decided_by_name"] is None and state["decided_at"] is None
    assert state["decision_note"] is None


def test_an_approved_reply_shows_who_approved_it(inbox: InboxEnv, gym) -> None:
    draft = inbox.ask(PRICE_Q)
    inbox.clock.advance(timedelta(minutes=5))
    assert inbox.decide(draft, note="Fiyat doğru.").status_code == 200
    state = staff_view(inbox, draft.id)["approval_state"]
    assert state["status"] == "approved"
    assert state["decided_by_name"] == inbox.env.owner.user.display_name
    assert state["decided_at"] is not None
    assert state["decision_note"] == "Fiyat doğru."


def test_a_rejected_reply_shows_the_name_and_the_note(inbox: InboxEnv, gym) -> None:
    draft = inbox.ask(PRICE_Q)
    response = inbox.decide(draft, "reject", role="manager", note="Önce fiyatı güncelleyin.")
    assert response.status_code == 200, response.text
    state = staff_view(inbox, draft.id)["approval_state"]
    assert state["status"] == "rejected"
    assert state["decided_by_name"] == inbox.env.manager.user.display_name
    assert state["decision_note"] == "Önce fiyatı güncelleyin."


def test_an_unanswered_approval_shows_as_expired(inbox: InboxEnv, gym) -> None:
    draft = inbox.ask(PRICE_Q)
    inbox.clock.advance(timedelta(hours=23, minutes=56))
    inbox.process()
    inbox.env.call(inbox.env.owner, "GET", "/approvals")  # lazy expiry on read
    state = staff_view(inbox, draft.id)["approval_state"]
    assert state["status"] == "expired"
    assert state["decided_by_name"] is None


def test_a_draft_without_an_approval_has_no_state(inbox: InboxEnv, gym) -> None:
    draft = inbox.ask("Bu bir rezalet, şikayetçiyim")  # handed to a person: nothing to approve
    assert draft.approval_id is None
    assert staff_view(inbox, draft.id)["approval_state"] is None


def test_staff_can_see_the_state_but_still_cannot_decide(inbox: InboxEnv, gym) -> None:
    draft = inbox.ask(PRICE_Q)
    assert staff_view(inbox, draft.id)["approval_state"]["status"] == "pending"
    assert inbox.decide(draft, role="staff").status_code == 403
    assert staff_view(inbox, draft.id)["approval_state"]["status"] == "pending"


def test_an_automatic_reply_shows_approved_by_policy_without_a_name(inbox: InboxEnv, gym) -> None:
    items = [{"action_class": "reply.pricing", "mode": "auto"}]
    inbox.env.call(inbox.env.owner, "PUT", "/automation-policies", json={"items": items})
    inbox.env.call(inbox.env.owner, "POST", "/automation-policies/review")
    draft = inbox.ask(PRICE_Q)
    state = staff_view(inbox, draft.id)["approval_state"]
    assert state["status"] == "approved" and state["decided_by_name"] is None


def test_a_foreign_draft_is_a_404(inbox: InboxEnv, gym) -> None:
    from tests.factories import create_workspace

    other = create_workspace(inbox.session, name="Other")
    response = inbox.env.owner.client.get(
        f"/api/v1/workspaces/{other.id}/reply-drafts/{uuid.uuid4()}"
    )
    assert response.status_code == 404
