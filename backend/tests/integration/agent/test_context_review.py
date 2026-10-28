"""Operator checks for real foreign references and public context construction."""

from dataclasses import replace

from app.agent.context import assemble
from app.agent.models import AgentThread
from tests.helpers.env import build_env
from tests.integration.agent.test_context_grounding import scenario
from tests.integration.agent.test_tools import _seed


def test_personality_routes_reject_existing_foreign_account(db_session, make_client, clock):
    env = build_env(db_session, make_client, clock)
    foreign = _seed(db_session)
    path = f"/accounts/{foreign.account_id}/agent/personality"
    assert env.call(env.owner, "GET", path).status_code == 404
    assert (
        env.call(
            env.manager,
            "PATCH",
            path,
            json={"expected_version": 1, "personality": {"tone": "neutral"}},
        ).status_code
        == 404
    )


def test_public_context_omits_private_turn_even_if_thread_has_dm_link(db_session, clock):
    context, _, message = scenario(db_session, clock)
    message.text = "PRIVATE-CUSTOMER-DATE-2026-12-14"
    thread = db_session.get(AgentThread, context.thread_id)
    thread.surface = "comment"
    db_session.flush()
    public = assemble(db_session, clock, replace(context, surface="comment"))
    assert message.text not in public.messages[0].content
    assert '"turns": []' in public.messages[0].content
