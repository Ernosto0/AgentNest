"""Real membership, CSRF, pagination and persisted foreign-scope IDs."""

import uuid

from app.agent.models import AgentEvent, AgentSession, AgentThread
from app.agent.tools.broker import BrokerContext
from app.inbox.models import Conversation, Message
from app.owner_requests import service
from tests.helpers.env import build_env
from tests.integration.agent.test_delegation import _account
from tests.integration.agent.test_tools import _seed


def question(env, *, customer="one"):
    db, clock = env.session, env.clock
    social, agent = _account(env)
    agent.controller_mode, agent.state = "agent", "active"
    conversation = Conversation(
        workspace_id=env.workspace.id,
        social_account_id=social.id,
        customer_external_id=customer,
        last_inbound_at=clock.now(),
    )
    db.add(conversation)
    db.flush()
    thread = AgentThread(
        workspace_id=env.workspace.id,
        social_account_id=social.id,
        surface="dm",
        source_ref=str(conversation.id),
        dm_conversation_id=conversation.id,
        event_cursor=1,
    )
    db.add(thread)
    db.flush()
    message = Message(
        workspace_id=env.workspace.id,
        social_account_id=social.id,
        conversation_id=conversation.id,
        direction="inbound",
        sender_kind="customer",
        external_message_id=uuid.uuid4().hex,
        text="Please explain my exception.",
        provider_timestamp=clock.now(),
    )
    db.add(message)
    db.flush()
    goal = AgentSession(
        workspace_id=env.workspace.id,
        thread_id=thread.id,
        goal_key="event:1",
        initiating_event_cursor=1,
    )
    db.add(goal)
    db.add(
        AgentEvent(
            workspace_id=env.workspace.id,
            social_account_id=social.id,
            thread_id=thread.id,
            cursor=1,
            kind="customer_message",
            source_kind="message",
            source_key=str(message.id),
            source_id=str(message.id),
            source_version=1,
            created_at=clock.now(),
        )
    )
    db.flush()
    ctx = BrokerContext(env.ctx(env.owner), social.id, thread.id, "dm", "customer")
    out = service.ask(
        db,
        clock,
        ctx,
        service.AskOwner(
            question="Exception details?", required_info="exception", visibility="customer_reply"
        ),
    )
    db.commit()
    return social, uuid.UUID(out["question_id"])


def test_questions_api_role_version_pagination_and_real_foreign_ids(db_session, make_client, clock):
    env = build_env(db_session, make_client, clock)
    social, qid = question(env)
    base = f"/accounts/{social.id}/owner-questions"
    first = env.call(env.staff, "GET", base)
    assert first.status_code == 200 and len(first.json()["items"]) == 1
    q = first.json()["items"][0]
    request = {
        "expected_version": q["version"],
        "client_request_id": str(uuid.uuid4()),
        "body": "okay",
        "kind": "answer",
    }
    assert env.call(env.staff, "POST", f"{base}/{qid}/answer", json=request).status_code == 403
    proposal = env.call(
        env.staff, "POST", f"{base}/{qid}/answer", json=request | {"kind": "proposal"}
    )
    assert proposal.status_code == 200 and proposal.json()["kind"] == "proposal"
    assert env.call(env.owner, "POST", f"{base}/{qid}/answer", json=request).status_code == 409
    request["expected_version"] = 2
    answer = env.call(
        env.manager,
        "POST",
        f"{base}/{qid}/answer",
        json=request | {"client_request_id": str(uuid.uuid4())},
    )
    assert answer.status_code == 200
    page = env.call(env.owner, "GET", f"{base}/{qid}/answers?limit=1").json()
    assert len(page["items"]) == 1 and page["next_cursor"]
    assert (
        len(
            env.call(
                env.owner, "GET", f"{base}/{qid}/answers?limit=1&cursor={page['next_cursor']}"
            ).json()["items"]
        )
        == 1
    )
    assert env.call(env.owner, "GET", base + "?limit=51").status_code == 422
    assert env.call(env.owner, "GET", base + "?customer_id=" + str(uuid.uuid4())).status_code == 404
    foreign = _seed(db_session)
    assert (
        env.call(env.owner, "GET", f"/accounts/{foreign.account_id}/owner-questions").status_code
        == 404
    )
    social.status = "disconnected"
    db_session.flush()
    second_social, second_qid = question(env, customer="two")
    assert env.call(env.owner, "GET", f"{base}/{second_qid}").status_code == 404
    assert (
        env.call(env.owner, "POST", f"{base}/{second_qid}/answer", json=request).status_code == 404
    )
    second = env.call(
        env.owner, "GET", f"/accounts/{second_social.id}/owner-questions/{second_qid}"
    ).json()
    assert (
        env.call(env.owner, "GET", base + "?customer_id=" + second["customer_id"]).status_code
        == 404
    )
    cancellation = {"expected_version": 1, "client_request_id": str(uuid.uuid4())}
    assert (
        env.call(
            env.staff,
            "POST",
            f"/accounts/{second_social.id}/owner-questions/{second_qid}/cancel",
            json=cancellation,
        ).status_code
        == 403
    )
    assert (
        env.call(
            env.owner,
            "POST",
            f"/accounts/{second_social.id}/owner-questions/{second_qid}/cancel",
            json=cancellation,
        ).status_code
        == 200
    )
    assert (
        env.call(
            env.owner,
            "POST",
            f"/accounts/{second_social.id}/owner-questions/{second_qid}/cancel",
            json=cancellation,
        ).status_code
        == 200
    )
