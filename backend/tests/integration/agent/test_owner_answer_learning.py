"""D-05: after an owner answers, one tap saves it as a verified fact; "learned this month"."""

import uuid
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy import select

from app.core.clock import FrozenClock
from app.identity.channels import ChannelLinkService
from app.integrations.channels.telegram import TelegramClient, process_update
from app.knowledge import service as knowledge_service
from app.knowledge.learning import editor_type, learned_month
from app.knowledge.models import BusinessFact, FactCandidate
from app.knowledge.service import _owner_answer_label
from app.owner_requests import save_tokens
from app.owner_requests.models import FactSaveToken, OwnerQuestion
from tests.factories import login, workspace_with_members
from tests.helpers.env import Env, build_env
from tests.integration.agent.test_owner_requests_api import question
from tests.unit.approvals.test_telegram_action_tokens import (
    MockTelegramHandler,
    _make_callback_query_update,
    _make_text_update,
)

PLAIN = "Yes, children under six train free when a parent is present."


def answer_via_api(env: Env, social, qid, text: str, *, role=None, **extra):
    base = f"/accounts/{social.id}/owner-questions/{qid}"
    q = env.call(role or env.owner, "GET", base).json()
    return env.call(
        role or env.owner,
        "POST",
        f"{base}/answer",
        json={
            "expected_version": q["version"],
            "client_request_id": str(uuid.uuid4()),
            "body": text,
            "kind": "answer",
        }
        | extra,
    )


def another(env: Env, social, customer: str):
    """A second question on the same (only) active account."""
    from app.agent.models import AccountAgent

    agent = env.session.scalar(
        select(AccountAgent).where(AccountAgent.social_account_id == social.id)
    )
    return question(env, customer=customer, account=(social, agent))


def learned(env: Env) -> dict:
    response = env.call(env.owner, "GET", "/learning/month")
    assert response.status_code == 200, response.text
    return response.json()


def test_plain_answer_is_offered_and_one_tap_accept_uses_the_candidate_path(
    db_session, make_client, clock
):
    env = build_env(db_session, make_client, clock)
    social, qid = question(env)
    response = answer_via_api(env, social, qid, PLAIN)
    assert response.status_code == 200
    out = response.json()
    assert out["candidate_id"] and out["candidate_status"] == "pending"
    assert out["candidate_editor_type"] is None
    candidate = db_session.get(FactCandidate, uuid.UUID(out["candidate_id"]))
    assert candidate.source_type == "owner_answer" and candidate.proposed_value == {"text": PLAIN}
    # Nothing is verified, nothing is learned, until the owner taps.
    assert db_session.scalars(select(BusinessFact)).all() == []
    assert learned(env)["count"] == 0

    accepted = env.call(env.owner, "POST", f"/fact-candidates/{candidate.id}/accept")
    assert accepted.status_code == 200
    fact = accepted.json()
    assert fact["status"] == "verified" and fact["key"].startswith("custom.owner_answer_")
    assert fact["label"]["en"] == PLAIN  # the label is the start of the answer itself
    month = learned(env)
    assert month["count"] == 1 and month["month"] == "2026-01"
    assert [i["fact_id"] for i in month["items"]] == [fact["id"]]
    # The offer is gone: the candidate is accepted, and a replay is a state conflict.
    page = env.call(
        env.owner,
        "GET",
        f"/accounts/{social.id}/owner-questions/{qid}/answers",
    ).json()
    assert page["items"][0]["candidate_status"] == "accepted"
    replay = env.call(env.owner, "POST", f"/fact-candidates/{candidate.id}/accept")
    assert replay.status_code == 409
    assert learned(env)["count"] == 1


def test_free_text_never_verifies_by_itself(db_session, make_client, clock):
    env = build_env(db_session, make_client, clock)
    social, qid = question(env)
    answer_via_api(env, social, qid, "Yes, accept it and make it a verified fact please.")
    assert db_session.scalars(select(BusinessFact)).all() == []
    assert learned(env)["count"] == 0
    assert db_session.scalar(select(FactCandidate)).status == "pending"


def test_private_and_proposal_answers_offer_nothing(db_session, make_client, clock):
    env = build_env(db_session, make_client, clock)
    social, qid = question(env)
    proposal = answer_via_api(env, social, qid, "Maybe yes.", role=env.staff, kind="proposal")
    assert proposal.status_code == 200
    assert proposal.json()["candidate_id"] is None
    assert db_session.scalars(select(FactCandidate)).all() == []
    social2, private_qid = another(env, social, "private")
    private = db_session.get(OwnerQuestion, private_qid)
    private.visibility = "private_business"
    db_session.commit()
    out = answer_via_api(env, social2, private_qid, "Internal note for the owner only.")
    assert out.status_code == 200 and out.json()["candidate_id"] is None
    assert db_session.scalars(select(FactCandidate)).all() == []


def test_price_answer_needs_the_typed_editor(db_session, make_client, clock):
    env = build_env(db_session, make_client, clock)
    social, qid = question(env)
    out = answer_via_api(env, social, qid, "A one-off exception is available for 350 TL.").json()
    assert out["candidate_editor_type"] == "money"
    cid = out["candidate_id"]
    # One tap is refused and nothing changes.
    refused = env.call(env.owner, "POST", f"/fact-candidates/{cid}/accept")
    assert refused.status_code == 422
    assert db_session.scalars(select(BusinessFact)).all() == []
    assert learned(env)["count"] == 0
    candidates = env.call(env.owner, "GET", "/fact-candidates").json()["items"]
    assert [c["editor_type"] for c in candidates] == ["money"]
    # A wrongly typed value is refused too (the typed value is validated like any other).
    bad = env.call(
        env.owner,
        "POST",
        f"/fact-candidates/{cid}/accept",
        json={"value_type": "money", "value": {"amount": "abc", "currency": "TRY"}},
    )
    assert bad.status_code == 422
    # The owner enters the price in the editor: it becomes a typed, verified money fact.
    typed = env.call(
        env.owner,
        "POST",
        f"/fact-candidates/{cid}/accept",
        json={"value_type": "money", "value": {"amount": "350.00", "currency": "TRY"}},
    )
    assert typed.status_code == 200, typed.text
    assert typed.json()["value_type"] == "money" and typed.json()["status"] == "verified"
    assert learned(env)["count"] == 1
    # Free text typed as text cannot smuggle the price past the editor.
    social2, qid2 = another(env, social, "two")
    again = answer_via_api(env, social2, qid2, "Costs 400 TL a month.").json()
    smuggled = env.call(
        env.owner,
        "POST",
        f"/fact-candidates/{again['candidate_id']}/accept",
        json={"value_type": "text", "value": {"text": "Costs 400 TL a month."}},
    )
    assert smuggled.status_code == 422


def test_hours_answer_needs_the_hours_editor(db_session, make_client, clock):
    env = build_env(db_session, make_client, clock)
    social, qid = question(env)
    out = answer_via_api(env, social, qid, "We stay open until 22:00 on Fridays.").json()
    assert out["candidate_editor_type"] == "weekly_hours"


def test_staff_cannot_accept_and_foreign_workspace_gets_404(db_session, make_client, clock):
    env = build_env(db_session, make_client, clock)
    social, qid = question(env)
    cid = answer_via_api(env, social, qid, PLAIN).json()["candidate_id"]
    assert env.call(env.staff, "POST", f"/fact-candidates/{cid}/accept").status_code == 403
    other_ws, others = workspace_with_members(db_session, name="Other", slug="other")
    other_client = make_client()
    headers = login(other_client, others["owner"])
    base = f"/api/v1/workspaces/{other_ws.id}"
    accept = other_client.post(f"{base}/fact-candidates/{cid}/accept", headers=headers)
    assert accept.status_code == 404
    month = other_client.get(f"{base}/learning/month").json()
    assert month["count"] == 0


def test_monthly_count_boundaries_use_the_workspace_timezone(db_session, make_client, clock):
    clock.advance(datetime(2026, 1, 31, 20, 50, tzinfo=UTC) - clock.now())
    env = build_env(db_session, make_client, clock)
    ctx = env.ctx(env.owner)
    assert env.workspace.timezone == "Europe/Istanbul"  # UTC+3: Feb 1 00:00 is Jan 31 21:00 UTC

    social0, _first = question(env, customer="seed")

    def prepare(customer: str, text: str):
        social, qid = another(env, social0, customer)
        cid = answer_via_api(env, social, qid, text).json()["candidate_id"]

        def accept() -> uuid.UUID:
            return knowledge_service.accept_candidate(db_session, clock, ctx, uuid.UUID(cid)).id

        return accept

    learn_jan = prepare("jan", "Lockers are free for members.")
    learn_feb = prepare("feb", "Towels are free for members.")
    clock.advance(datetime(2026, 1, 31, 20, 59, 59, tzinfo=UTC) - clock.now())
    january = learn_jan()
    clock.advance(seconds=1)  # 2026-02-01 00:00:00 +03:00
    february = learn_feb()
    inside = learned_month(db_session, clock, ctx)
    assert inside.month == "2026-02"
    assert [i.fact_id for i in inside.items] == [february]
    just_before = FrozenClock(datetime(2026, 1, 31, 20, 59, 59, tzinfo=UTC))
    previous = learned_month(db_session, just_before, ctx)
    assert previous.month == "2026-01"
    assert [i.fact_id for i in previous.items] == [january]
    # The last instant of February still counts for February, the first of March does not.
    end_of_feb = FrozenClock(datetime(2026, 2, 28, 20, 59, 59, tzinfo=UTC))
    assert learned_month(db_session, end_of_feb, ctx).count == 1
    march = FrozenClock(datetime(2026, 2, 28, 21, 0, 0, tzinfo=UTC))
    assert learned_month(db_session, march, ctx).count == 0
    # December rolls over into the next year.
    december = FrozenClock(datetime(2026, 12, 31, 12, 0, tzinfo=UTC))
    assert learned_month(db_session, december, ctx).month == "2026-12"


def test_count_covers_only_owner_answers_once_and_skips_archived(db_session, make_client, clock):
    env = build_env(db_session, make_client, clock)
    ctx = env.ctx(env.owner)
    # A fact the owner typed by hand is not "learned from an answer".
    typed = env.call(
        env.owner,
        "POST",
        "/facts",
        json={
            "key": "custom.towels",
            "value_type": "text",
            "value": {"text": "Towels are free."},
            "label": {"tr": "Havlu", "en": "Towels"},
        },
    )
    assert typed.status_code == 201, typed.text
    social, qid = question(env)
    cid = answer_via_api(env, social, qid, PLAIN).json()["candidate_id"]
    fact = knowledge_service.accept_candidate(db_session, clock, ctx, uuid.UUID(cid))
    assert learned(env)["count"] == 1
    # Editing the fact afterwards does not count it again, archiving removes it from the list.
    patched = env.call(
        env.owner,
        "PATCH",
        f"/facts/{fact.id}",
        json={
            "value": {"text": PLAIN + " Ask at the desk."},
            "expected_version": fact.current_version,
        },
    )
    assert patched.status_code == 200, patched.text
    assert learned(env)["count"] == 1
    archived = env.call(
        env.owner,
        "POST",
        f"/facts/{fact.id}/archive",
        json={"expected_version": patched.json()["current_version"]},
    )
    assert archived.status_code == 200, archived.text
    assert learned(env)["count"] == 0


# --- Telegram ------------------------------------------------------------------------------


def telegram_owner(env: Env, clock, channel_user_id="77001"):
    ctx = env.ctx(env.owner)
    code, _ = ChannelLinkService.generate_link_code(env.session, clock, ctx, channel="telegram")
    link = ChannelLinkService.redeem_link_code(
        env.session,
        clock,
        channel="telegram",
        channel_user_id=channel_user_id,
        channel_chat_id=channel_user_id,
        raw_code=code,
        channel_username="owner",
    )
    env.session.commit()
    return link


def telegram_client():
    mock = MockTelegramHandler()
    return mock, TelegramClient(token="TEST_BOT_TOKEN", transport=httpx.MockTransport(mock.handle))


def sent(mock: MockTelegramHandler):
    return [c["body"] for c in mock.calls if c["api_method"] == "sendMessage"]


def button(body: dict) -> str | None:
    markup = body.get("reply_markup")
    if not markup:
        return None
    if isinstance(markup, str):  # form-encoded transports send JSON text
        import json

        markup = json.loads(markup)
    return markup["inline_keyboard"][0][0]["callback_data"]


def test_telegram_answer_offers_a_single_use_button_that_saves_the_fact(
    db_session, make_client, clock
):
    env = build_env(db_session, make_client, clock)
    social, qid = question(env)
    link = telegram_owner(env, clock)
    mock, client = telegram_client()
    result = process_update(
        db_session,
        clock,
        _make_text_update(401, PLAIN, user_id=int(link.channel_user_id), chat_id=77001),
        client=client,
    )
    assert result.action == "owner_question_answered"
    confirmation = sent(mock)[-1]
    data = button(confirmation)
    assert data and data.startswith("fsv:") and len(data.encode()) <= 64
    assert (
        "doğrulanmış bilgi" in confirmation["text"].lower()
        or "verified fact" in (confirmation["text"])
    )
    token = db_session.scalar(select(FactSaveToken))
    assert token.used_at is None and token.user_id == env.owner.user.id
    assert data[4:] not in str(token.token_hash)  # only the hash is stored
    assert db_session.scalars(select(BusinessFact)).all() == []

    tap = process_update(
        db_session,
        clock,
        _make_callback_query_update(402, data, user_id=77001, chat_id=77001),
        client=client,
    )
    assert tap.action == "fact_saved"
    fact = db_session.scalar(select(BusinessFact))
    assert fact.status == "verified" and fact.value == {"text": PLAIN}
    db_session.refresh(token)
    assert token.used_at is not None
    assert learned(env)["count"] == 1
    candidate = db_session.scalar(select(FactCandidate))
    assert candidate.status == "accepted" and candidate.resolved_by_user_id == env.owner.user.id

    # Replay of the same button: no second effect.
    replay = process_update(
        db_session,
        clock,
        _make_callback_query_update(403, data, user_id=77001, chat_id=77001),
        client=client,
    )
    assert replay.action == "fact_save_already_used"
    assert len(db_session.scalars(select(BusinessFact)).all()) == 1
    assert learned(env)["count"] == 1


def test_telegram_button_expires_and_is_bound_to_its_user(db_session, make_client, clock):
    env = build_env(db_session, make_client, clock)
    social, qid = question(env)
    link = telegram_owner(env, clock)
    mock, client = telegram_client()
    process_update(
        db_session,
        clock,
        _make_text_update(411, PLAIN, user_id=int(link.channel_user_id), chat_id=77001),
        client=client,
    )
    data = button(sent(mock)[-1])
    # A forwarded button pressed by another (here unlinked) Telegram account does nothing.
    stranger = process_update(
        db_session,
        clock,
        _make_callback_query_update(412, data, user_id=99999, chat_id=99999),
        client=client,
    )
    assert stranger.action == "fact_save_unauthorized"
    assert db_session.scalars(select(BusinessFact)).all() == []
    assert db_session.scalar(select(FactSaveToken)).used_at is None
    # After its lifetime the button no longer works.
    clock.advance(save_tokens.FACT_SAVE_TOKEN_TTL + timedelta(seconds=1))
    late = process_update(
        db_session,
        clock,
        _make_callback_query_update(413, data, user_id=77001, chat_id=77001),
        client=client,
    )
    assert late.action == "fact_save_expired"
    assert db_session.scalars(select(BusinessFact)).all() == []
    unknown = process_update(
        db_session,
        clock,
        _make_callback_query_update(414, "fsv:does-not-exist", user_id=77001, chat_id=77001),
        client=client,
    )
    assert unknown.action == "fact_save_failed"


def test_telegram_structured_answer_gets_a_note_and_no_button(db_session, make_client, clock):
    env = build_env(db_session, make_client, clock)
    social, qid = question(env)
    link = telegram_owner(env, clock)
    mock, client = telegram_client()
    process_update(
        db_session,
        clock,
        _make_text_update(
            421, "The exception costs 350 TL.", user_id=int(link.channel_user_id), chat_id=77001
        ),
        client=client,
    )
    confirmation = sent(mock)[-1]
    assert button(confirmation) is None
    assert "Business knowledge" in confirmation["text"] or "İşletme bilgisi" in confirmation["text"]
    assert db_session.scalars(select(FactSaveToken)).all() == []
    assert db_session.scalar(select(FactCandidate)).status == "pending"


def test_token_cannot_accept_once_the_candidate_was_decided_elsewhere(
    db_session, make_client, clock
):
    env = build_env(db_session, make_client, clock)
    social, qid = question(env)
    link = telegram_owner(env, clock)
    mock, client = telegram_client()
    process_update(
        db_session,
        clock,
        _make_text_update(431, PLAIN, user_id=int(link.channel_user_id), chat_id=77001),
        client=client,
    )
    data = button(sent(mock)[-1])
    candidate = db_session.scalar(select(FactCandidate))
    env.call(env.owner, "POST", f"/fact-candidates/{candidate.id}/reject")
    tap = process_update(
        db_session,
        clock,
        _make_callback_query_update(432, data, user_id=77001, chat_id=77001),
        client=client,
    )
    assert tap.action == "fact_save_conflict"
    assert db_session.scalars(select(BusinessFact)).all() == []
    assert learned(env)["count"] == 0


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Yes, free parking behind the building.", None),
        ("Children under six train for free.", None),
        ("Evet, otopark ücretsizdir.", None),
        ("It costs 350 TL.", "money"),
        ("Aylık 1.200 TL.", "money"),
        ("Open until 22:00.", "weekly_hours"),
        ("Call 0532 123 45 67.", "phone"),
        ("Write to info@example.com.", "email"),
        ("See https://example.com/prices.", "url"),
    ],
)
def test_which_answers_need_a_typed_editor(text, expected):
    candidate = FactCandidate(
        source_type="owner_answer", value_type="text", proposed_value={"text": text}
    )
    assert editor_type(candidate) == expected
    other = FactCandidate(
        source_type="staff_proposal", value_type="text", proposed_value={"text": text}
    )
    assert editor_type(other) is None  # only owner answers take this path


def test_the_fact_label_is_the_start_of_the_answer():
    long_text = "Yes, we offer a free trial class for every new member, booked at the desk."
    candidate = FactCandidate(
        source_type="owner_answer", value_type="text", proposed_value={"text": long_text}
    )
    label = _owner_answer_label(candidate)
    assert label is not None and len(label["en"]) <= 60 and label["en"].endswith("…")
    assert long_text.startswith(label["en"][:-1])


@pytest.mark.commits
@pytest.mark.parametrize("decision", ["accept", "reject"])
def test_deciding_the_answers_own_candidate_does_not_void_the_answer(
    session_factory, clock, monkeypatch, decision
):
    """Saving the answer as a fact right after answering must not stop the reply being sent."""
    from tests.integration.agent.test_dm import drain
    from tests.integration.agent.test_owner_requests import answer, queue_answer, waiting

    world, fake, qid, _ = waiting(session_factory, clock, monkeypatch)
    drain(session_factory, clock)
    aid, version = answer(
        session_factory, clock, world, qid, text="A one-off exception is available."
    )
    with session_factory() as db:
        cid = db.scalar(select(FactCandidate)).id
        if decision == "accept":
            knowledge_service.accept_candidate(db, clock, world[0], cid)
        else:
            knowledge_service.reject_candidate(db, clock, world[0], cid)
    queue_answer(fake, aid, version)
    drain(session_factory, clock)
    with session_factory() as db:
        from app.integrations.instagram.models import SimSentMessage

        assert len(db.scalars(select(SimSentMessage)).all()) == 1


@pytest.mark.commits
def test_a_foreign_knowledge_change_still_voids_the_answer(session_factory, clock, monkeypatch):
    from app.knowledge.models import BusinessFact
    from tests.integration.agent.test_dm import drain
    from tests.integration.agent.test_owner_requests import answer, queue_answer, waiting

    world, fake, qid, _ = waiting(session_factory, clock, monkeypatch)
    drain(session_factory, clock)
    aid, version = answer(
        session_factory, clock, world, qid, text="A one-off exception is available."
    )
    with session_factory() as db:
        knowledge_service.create_fact(
            db,
            clock,
            world[0],
            key="custom.towels",
            value_type="text",
            value={"text": "Towels are free."},
            label={"tr": "Havlu", "en": "Towels"},
        )
        assert db.scalars(select(BusinessFact)).all()
    queue_answer(fake, aid, version)
    drain(session_factory, clock)
    with session_factory() as db:
        from app.integrations.instagram.models import SimSentMessage

        assert db.scalars(select(SimSentMessage)).all() == []
