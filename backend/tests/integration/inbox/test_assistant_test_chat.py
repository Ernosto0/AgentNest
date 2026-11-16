"""F-02, Session 01: the owner's "try your assistant" test chat (backend).

Proves: roles, isolation, the draft with its decision, reason and facts used, that nothing is ever
sent or counted (no approval, operation, notification, memory, report number, send job), reset,
the per-workspace rate limits, and that the chat works with the demo tools off and without any
connected account.
"""

import uuid
from collections.abc import Callable
from datetime import timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.approvals.models import Approval
from app.audit.models import AuditLog
from app.core.clock import FrozenClock
from app.core.config import Settings
from app.inbox import sandbox
from app.inbox.models import (
    AssistantTestTurn,
    Conversation,
    InboundEvent,
    Message,
    ReplyDraft,
)
from app.integrations.instagram.models import SimInboundMessage, SimSentMessage
from app.integrations.llm import FakeLLMProvider
from app.jobs.models import Job
from app.jobs.testing import run_due_jobs
from app.memory.models import CustomerIdentity, CustomerMemory, MemorySource
from app.notifications.models import Notification
from app.operations.models import Operation
from app.policy.engine import Decision
from app.policy.rules_reply import AUTO
from app.reporting.metrics import compute_metrics
from app.reporting.periods import day_bounds, local_date_of
from tests.factories import knowledge_ctx
from tests.helpers.env import Env, Role, build_env
from tests.helpers.gym import STUDENT, seed_gym_facts
from tests.integration.inbox.conftest import InboxEnv

PRICE_Q = "Aylık üyelik ne kadar?"
BASE = "/assistant/test-chat"


def proposal(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "intent": "pricing",
        "flags": [],
        "can_answer": True,
        "needs_human": False,
        "approved_answer_id": None,
        "reply_template": "Merhaba! Aylık üyelik ücretimiz {{fact:pricing.membership_monthly}}.",
        "used_fact_keys": ["pricing.membership_monthly"],
        "language": "tr",
    }
    base.update(overrides)
    return base


class Chat:
    """The test chat of one workspace, driven through the API as a role."""

    def __init__(self, env: Env, factory: sessionmaker[Session]) -> None:
        self.env = env
        self.factory = factory

    @property
    def clock(self) -> FrozenClock:
        return self.env.clock

    @property
    def session(self) -> Session:
        return self.env.session

    def send(self, text: str = PRICE_Q, role: Role | None = None) -> Any:
        self.clock.advance(timedelta(seconds=1))  # people do not type in the same microsecond
        return self.env.call(
            role or self.env.owner, "POST", f"{BASE}/messages", json={"text": text}
        )

    def get(self, role: Role | None = None) -> Any:
        return self.env.call(role or self.env.owner, "GET", BASE)

    def reset(self, role: Role | None = None) -> Any:
        return self.env.call(role or self.env.owner, "POST", f"{BASE}/reset")

    def process(self) -> int:
        return run_due_jobs(self.clock, session_factory=self.factory)

    def ask(self, text: str = PRICE_Q, role: Role | None = None) -> dict[str, Any]:
        """A test message, all the way to its ready turn."""
        response = self.send(text, role)
        assert response.status_code == 202, response.text
        self.process()
        turns = self.get(role).json()["items"]
        turn = next(t for t in turns if t["id"] == response.json()["id"])
        assert turn["status"] == "ready", turn
        return turn

    def limit(self, **overrides: object) -> None:
        app = self.env.owner.client.app
        app.state.settings = app.state.settings.model_copy(update=overrides)  # type: ignore[attr-defined]


@pytest.fixture
def provider() -> FakeLLMProvider:
    from app.ai import runtime

    fake = runtime.get_provider()
    assert isinstance(fake, FakeLLMProvider)
    fake.reset()
    return fake


@pytest.fixture(autouse=True)
def _reset_provider_after(provider: FakeLLMProvider):  # type: ignore[no-untyped-def]
    yield
    provider.reset()


@pytest.fixture
def chat(
    db_session: Session,
    make_client: Callable[[], TestClient],
    clock: FrozenClock,
    shared_session_factory: sessionmaker[Session],
) -> Chat:
    """A workspace with verified facts and **no connected Instagram account**."""
    env = build_env(db_session, make_client, clock)
    seed_gym_facts(db_session, env.workspace, clock)
    db_session.commit()
    return Chat(env, shared_session_factory)


@pytest.fixture
def connected(inbox: InboxEnv) -> Chat:
    """The same, with a connected (mock) account that has real conversations in it."""
    inbox.seed_facts()
    return Chat(inbox.env, inbox.factory)


# --- roles and isolation ------------------------------------------------------------------------


@pytest.mark.parametrize("role", ["owner", "manager"])
def test_owner_and_manager_can_use_the_chat(chat: Chat, role: str) -> None:
    who = getattr(chat.env, role)
    assert chat.send(role=who).status_code == 202
    assert chat.get(who).status_code == 200
    assert chat.reset(who).status_code == 200


def test_staff_cannot_use_the_chat(chat: Chat) -> None:
    staff = chat.env.staff
    assert chat.send(role=staff).status_code == 403
    assert chat.get(staff).status_code == 403
    assert chat.reset(staff).status_code == 403
    assert chat.session.scalar(select(func.count()).select_from(AssistantTestTurn)) == 0


def test_a_member_of_another_workspace_gets_404(
    chat: Chat, make_client: Callable[[], TestClient], db_session: Session
) -> None:
    from tests.factories import login, workspace_with_members

    _, users = workspace_with_members(db_session, name="Foreign", slug="foreign")
    foreign = make_client()
    headers = login(foreign, users["owner"])
    base = f"/api/v1/workspaces/{chat.env.workspace.id}{BASE}"
    assert foreign.get(base, headers=headers).status_code == 404
    assert foreign.post(f"{base}/messages", json={"text": "hi"}, headers=headers).status_code == 404
    assert foreign.post(f"{base}/reset", headers=headers).status_code == 404
    assert chat.session.scalar(select(func.count()).select_from(AssistantTestTurn)) == 0


def test_the_chat_needs_a_session_and_a_csrf_token(chat: Chat) -> None:
    base = f"/api/v1/workspaces/{chat.env.workspace.id}{BASE}"
    anonymous = TestClient(chat.env.owner.client.app)
    assert anonymous.get(base).status_code == 401
    no_csrf = chat.env.owner.client.post(f"{base}/messages", json={"text": "hi"})
    assert no_csrf.status_code == 403


def test_each_member_sees_only_their_own_chat(chat: Chat) -> None:
    chat.ask(PRICE_Q, chat.env.owner)
    assert len(chat.get(chat.env.owner).json()["items"]) == 1
    assert chat.get(chat.env.manager).json()["items"] == []


# --- the draft, the decision, the reason, the facts ---------------------------------------------


def test_the_message_is_accepted_at_once_and_drafted_by_the_job(chat: Chat) -> None:
    response = chat.send()
    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "pending" and body["draft"] is None
    assert body["customer_text"] == PRICE_Q and body["is_simulated"] is True
    assert chat.get().json()["items"][0]["status"] == "pending"
    jobs = chat.session.scalars(select(Job).where(Job.job_type == "assistant_test_draft")).all()
    assert len(jobs) == 1 and jobs[0].workspace_id == chat.env.workspace.id
    assert chat.process() >= 1
    ready = chat.get().json()["items"][0]
    assert ready["status"] == "ready" and ready["completed_at"] is not None


def test_a_price_question_returns_the_draft_with_its_decision_and_facts(chat: Chat) -> None:
    turn = chat.ask(PRICE_Q)
    draft = turn["draft"]
    assert draft["text"] and "6.000 ₺" in draft["text"]
    assert draft["decision"] == "approval_required"
    assert draft["reasons"] == ["POLICY_REQUIRES_APPROVAL"]
    assert draft["language"] == "tr" and draft["intent"] == "pricing"
    monthly = next(f for f in draft["facts_used"] if f["key"] == "pricing.membership_monthly")
    assert monthly["display"] == "6.000 ₺ / ay"
    assert monthly["label"]
    assert monthly["verified_at"] is not None  # when the owner last verified it
    assert turn["is_simulated"] is True


def test_a_complaint_is_held_for_a_person_with_the_reason(
    chat: Chat, provider: FakeLLMProvider
) -> None:
    provider.queue(
        "draft_reply",
        proposal(
            intent="complaint",
            flags=["complaint"],
            reply_template="Üzgünüz, durumu hemen inceliyoruz.",
            used_fact_keys=[],
        ),
    )
    draft = chat.ask("Berbat bir hizmet, çok kızgınım")["draft"]
    assert draft["decision"] == "human_required"
    assert "INTENT_COMPLAINT" in draft["reasons"]
    assert draft["text"] is None  # nothing the assistant would send on its own
    assert draft["suggestion_text"]  # wording a person may start from


def test_an_ungrounded_price_is_never_a_draft(chat: Chat, provider: FakeLLMProvider) -> None:
    invented = proposal(reply_template="Aylık üyelik 6.500 ₺.", used_fact_keys=[])
    provider.queue("draft_reply", invented)
    provider.queue("draft_reply", invented)  # the regeneration says the same
    draft = chat.ask(PRICE_Q)["draft"]
    assert draft["decision"] == "human_required"
    assert "GROUNDING_FAILED" in draft["reasons"]
    assert draft["text"] is None
    assert "⟦" in (draft["suggestion_text"] or "")  # the invented value is marked, not sent


def test_an_unverified_price_is_never_quoted(chat: Chat, provider: FakeLLMProvider) -> None:
    unverified = proposal(
        reply_template=f"Öğrenci üyeliği {{{{fact:{STUDENT}}}}}.", used_fact_keys=[STUDENT]
    )
    provider.queue("draft_reply", unverified)
    provider.queue("draft_reply", unverified)
    turn = chat.ask("Öğrenci indirimi var mı?")
    assert turn["draft"]["decision"] == "human_required"
    assert "FACT_NOT_USABLE" in turn["draft"]["reasons"]
    assert turn["draft"]["text"] is None and turn["draft"]["facts_used"] == []
    assert "4.500" not in str(turn)


def test_a_second_message_continues_the_conversation(chat: Chat, provider: FakeLLMProvider) -> None:
    chat.ask(PRICE_Q)
    chat.ask("Peki çalışma saatleriniz?")
    last = provider.calls[-1]
    sent = "\n".join(m.content for m in last.messages)
    assert PRICE_Q in sent and "Peki çalışma saatleriniz?" in sent


def test_the_model_failing_for_good_leaves_a_human_required_turn(
    chat: Chat, provider: FakeLLMProvider
) -> None:
    from app.integrations.llm.errors import LLMTransientError

    for _ in range(3):
        provider.queue("draft_reply", LLMTransientError("overloaded"))
    response = chat.send()
    for wait in (0, 13, 73):  # the job's backoff: 10 s then 60 s, each with 20 % jitter
        chat.clock.advance(timedelta(seconds=wait))
        chat.process()
    turn = chat.get().json()["items"][0]
    assert turn["status"] == "ready" and turn["id"] == response.json()["id"]
    assert turn["draft"]["decision"] == "human_required"
    assert "LLM_UNAVAILABLE" in turn["draft"]["reasons"] and turn["draft"]["text"] is None


def test_the_chat_works_with_the_demo_tools_off(
    chat: Chat, build_app: Callable[..., Any], db_session: Session
) -> None:
    from tests.factories import login

    app = build_app(demo_tools_enabled=False)
    with TestClient(app) as client:
        headers = login(client, chat.env.owner.user)
        base = f"/api/v1/workspaces/{chat.env.workspace.id}{BASE}"
        assert client.get("/api/v1/dev/scripts").status_code == 404
        assert (
            client.post(f"{base}/messages", json={"text": PRICE_Q}, headers=headers).status_code
            == 202
        )


def test_a_blank_or_oversized_message_is_refused(chat: Chat) -> None:
    assert chat.send("   ").status_code == 422
    assert chat.send("x" * (sandbox.MAX_MESSAGE_CHARS + 1)).status_code == 422
    assert chat.env.session.scalar(select(func.count()).select_from(AssistantTestTurn)) == 0


# --- nothing is sent and nothing is counted -----------------------------------------------------

TABLES = (
    Conversation,
    Message,
    ReplyDraft,
    Approval,
    Operation,
    Notification,
    InboundEvent,
    SimSentMessage,
    SimInboundMessage,
    CustomerIdentity,
    CustomerMemory,
    MemorySource,
    AuditLog,
)


def counts(session: Session) -> dict[str, int]:
    session.expire_all()
    result = {
        t.__tablename__: int(session.scalar(select(func.count()).select_from(t)) or 0)
        for t in TABLES
    }
    result["jobs_other_than_test_draft"] = int(
        session.scalar(
            select(func.count()).select_from(Job).where(Job.job_type != "assistant_test_draft")
        )
        or 0
    )
    return result


def observable(chat: Chat) -> dict[str, Any]:
    """Everything an owner sees that must not move: numbers, queues, feeds."""
    env = chat.env
    ctx = knowledge_ctx(env.workspace, env.owner.user, "owner")
    start, end = day_bounds(local_date_of(chat.clock.now(), ctx.timezone), ctx.timezone)
    metrics = compute_metrics(chat.session, ctx, start, end, chat.clock.now())
    return {
        "metrics": metrics.as_list(),
        "simulated": metrics.has_simulated_data,
        "home": env.call(env.owner, "GET", "/home/attention").json(),
        "approvals": env.call(env.owner, "GET", "/approvals").json(),
        "notifications": env.call(env.owner, "GET", "/notifications").json(),
        "conversations": env.call(env.owner, "GET", "/conversations").json(),
    }


def test_nothing_is_sent_or_counted_in_a_workspace_with_a_connected_account(
    connected: Chat, provider: FakeLLMProvider
) -> None:
    inbox_env = connected.env
    # A real conversation exists, so the report and the queues are not trivially empty.
    before_counts, before_view = counts(connected.session), observable(connected)
    for text in (PRICE_Q, "Çalışma saatleriniz nedir?", "Berbat hizmet, şikayetçiyim"):
        connected.ask(text)
    assert counts(connected.session) == before_counts
    assert observable(connected) == before_view
    assert not connected.session.scalars(
        select(Job).where(Job.job_type.in_(("send_reply", "reconcile_send", "emit_echo")))
    ).all()
    assert (
        connected.session.scalar(
            select(func.count())
            .select_from(Operation)
            .where(Operation.workspace_id == inbox_env.workspace.id)
        )
        == 0
    )
    connected.reset()
    assert counts(connected.session) == before_counts


def test_a_workspace_with_a_real_conversation_keeps_its_numbers(inbox: InboxEnv) -> None:
    inbox.seed_facts()
    inbox.ask()  # a real simulated customer, a real draft waiting for approval
    chat = Chat(inbox.env, inbox.factory)
    before_counts, before_view = counts(chat.session), observable(chat)
    assert before_counts["reply_drafts"] == 1 and before_counts["approvals"] == 1
    chat.ask(PRICE_Q)
    chat.ask(PRICE_Q)
    assert counts(chat.session) == before_counts
    assert observable(chat) == before_view
    assert len(before_view["approvals"]["items"]) == 1  # the real one is there, the tests add none


def test_even_an_automatic_decision_sends_nothing(
    connected: Chat, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If policy says ``auto`` the real pipeline would queue a send job; the sandbox must not."""
    import app.inbox.sandbox as module

    monkeypatch.setattr(module, "decide", lambda *a, **k: Decision(AUTO, ()))
    before = counts(connected.session)
    turn = connected.ask(PRICE_Q)
    assert turn["draft"]["decision"] == "auto" and turn["draft"]["text"]
    assert counts(connected.session) == before
    assert not connected.session.scalars(select(Job).where(Job.job_type == "send_reply")).all()


def test_the_turn_table_can_never_hold_a_real_row(chat: Chat) -> None:
    from sqlalchemy.exc import IntegrityError

    ctx = chat.env.ctx(chat.env.owner)
    chat.session.add(
        AssistantTestTurn(
            workspace_id=ctx.workspace_id,
            user_id=chat.env.owner.user.id,
            customer_text="x",
            is_simulated=False,
            created_at=chat.clock.now(),
        )
    )
    with pytest.raises(IntegrityError):
        chat.session.flush()
    chat.session.rollback()


def test_the_send_executor_refuses_a_simulated_draft_for_a_real_account(inbox: InboxEnv) -> None:
    """Defence in depth (INV-09): whatever a draft is, simulated content never reaches Meta."""
    inbox.seed_facts()
    draft = inbox.ask()
    assert inbox.decide(draft).status_code == 200  # approved, send job queued
    assert draft.is_simulated
    inbox.account.provider_kind = "meta"  # the account turned real after the draft was made
    inbox.session.commit()
    inbox.process()
    after = inbox.refreshed(draft)
    assert after.status == "cancelled" and after.failure_code == "SIMULATED_TO_REAL_ACCOUNT"
    assert inbox.operation(draft) is None
    assert inbox.sim_sent() == []


# --- reset ---------------------------------------------------------------------------------------


def test_reset_clears_the_chat_and_its_content(chat: Chat) -> None:
    chat.ask(PRICE_Q)
    chat.ask("Çalışma saatleriniz nedir?")
    cleared = chat.reset()
    assert cleared.status_code == 200 and cleared.json() == {"cleared": 2}
    assert chat.get().json()["items"] == []
    rows = chat.session.scalars(select(AssistantTestTurn)).all()
    assert len(rows) == 2  # kept as the rate limit's memory...
    for row in rows:  # ...with nothing of the conversation left in them
        assert row.status == "reset" and row.reset_at is not None
        assert row.customer_text is None and row.draft_text is None
        assert row.facts_used == [] and row.decision is None


def test_reset_only_clears_the_callers_chat(chat: Chat) -> None:
    chat.ask(PRICE_Q, chat.env.owner)
    chat.ask(PRICE_Q, chat.env.manager)
    assert chat.reset(chat.env.owner).json() == {"cleared": 1}
    assert chat.get(chat.env.owner).json()["items"] == []
    assert len(chat.get(chat.env.manager).json()["items"]) == 1


def test_a_draft_that_arrives_after_a_reset_is_discarded(chat: Chat) -> None:
    chat.send()
    chat.reset()
    chat.process()  # the queued job finds a reset turn and does nothing
    assert chat.get().json()["items"] == []
    row = chat.session.scalars(select(AssistantTestTurn)).one()
    assert row.status == "reset" and row.draft_text is None and row.decision is None


def test_a_new_chat_starts_after_a_reset_without_the_old_messages(
    chat: Chat, provider: FakeLLMProvider
) -> None:
    chat.ask(PRICE_Q)
    chat.reset()
    chat.ask("Çalışma saatleriniz nedir?")
    sent = "\n".join(m.content for m in provider.calls[-1].messages)
    assert PRICE_Q not in sent


# --- rate limits ---------------------------------------------------------------------------------


def test_the_hourly_limit_stops_the_chat_with_a_retry_after(chat: Chat) -> None:
    chat.limit(test_chat_max_messages_per_hour=2)
    chat.ask(PRICE_Q)
    chat.ask(PRICE_Q)
    refused = chat.send()
    assert refused.status_code == 429
    assert refused.json()["code"] == "TEST_CHAT_RATE_LIMITED"
    assert int(refused.headers["Retry-After"]) >= 1
    assert chat.session.scalar(select(func.count()).select_from(AssistantTestTurn)) == 2
    assert chat.get().json()["remaining_this_hour"] == 0
    chat.clock.advance(timedelta(hours=1, seconds=1))  # the window slides on
    assert chat.send().status_code == 202


def test_resetting_does_not_give_the_limit_back(chat: Chat) -> None:
    chat.limit(test_chat_max_messages_per_hour=2)
    chat.ask(PRICE_Q)
    chat.ask(PRICE_Q)
    chat.reset()
    assert chat.send().status_code == 429


def test_the_limit_is_per_workspace_not_per_member(chat: Chat) -> None:
    chat.limit(test_chat_max_messages_per_hour=2)
    chat.ask(PRICE_Q, chat.env.owner)
    chat.ask(PRICE_Q, chat.env.manager)
    assert chat.send(role=chat.env.owner).status_code == 429
    assert chat.send(role=chat.env.manager).status_code == 429


def test_the_daily_limit_holds_after_the_hourly_window_has_passed(chat: Chat) -> None:
    chat.limit(test_chat_max_messages_per_hour=10, test_chat_max_messages_per_day=3)
    for _ in range(3):
        chat.ask(PRICE_Q)
        chat.clock.advance(timedelta(hours=2))
    assert chat.send().status_code == 429
    chat.clock.advance(timedelta(hours=19))
    assert chat.send().status_code == 202
    assert chat.get().json()["remaining_today"] >= 0


def test_the_limit_of_one_workspace_does_not_touch_another(
    chat: Chat, make_client: Callable[[], TestClient], db_session: Session
) -> None:
    from tests.factories import login, workspace_with_members

    chat.limit(test_chat_max_messages_per_hour=1)
    other, users = workspace_with_members(db_session, name="Other", slug="other")
    client = make_client()
    headers = login(client, users["owner"])
    chat.ask(PRICE_Q)
    assert chat.send().status_code == 429
    response = client.post(
        f"/api/v1/workspaces/{other.id}{BASE}/messages", json={"text": PRICE_Q}, headers=headers
    )
    assert response.status_code == 202


def test_only_a_few_drafts_may_wait_at_once(chat: Chat) -> None:
    for _ in range(sandbox.MAX_PENDING):
        assert chat.send().status_code == 202  # no job has run: all pending
    refused = chat.send()
    assert refused.status_code == 429 and refused.json()["code"] == "TEST_CHAT_RATE_LIMITED"
    chat.process()
    assert chat.send().status_code == 202


def test_old_turns_are_deleted_and_stop_counting(chat: Chat) -> None:
    chat.ask(PRICE_Q)
    chat.clock.advance(sandbox.RETENTION + timedelta(hours=1))
    assert chat.send().status_code == 202
    assert chat.session.scalar(select(func.count()).select_from(AssistantTestTurn)) == 1


def test_the_limits_default_to_something_a_person_can_hit_but_a_script_cannot(
    settings: Settings,
) -> None:
    assert settings.test_chat_max_messages_per_hour <= 30
    assert settings.test_chat_max_messages_per_day <= 100
    assert (
        settings.test_chat_max_messages_per_day <= settings.llm_max_calls_per_workspace_per_day // 4
    )


def test_ids_in_the_responses_are_the_turns_own(chat: Chat) -> None:
    turn = chat.ask()
    row = chat.session.get(AssistantTestTurn, uuid.UUID(turn["id"]))
    assert row is not None and row.workspace_id == chat.env.workspace.id and row.is_simulated
