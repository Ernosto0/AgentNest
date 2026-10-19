"""Fixtures for the command integration tests: a gym workspace with real demo facts, the
scriptable fake provider, and helpers to submit, process and decide commands over HTTP."""

import uuid
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.ai import runtime
from app.core.clock import FrozenClock
from app.core.config import Settings
from app.integrations.llm import FakeLLMProvider
from app.jobs.testing import run_due_jobs
from app.knowledge.models import BusinessFact
from tests.factories import create_fact, money
from tests.helpers.env import Env, Role, build_env

MONTHLY = "pricing.membership_monthly"
QUARTER = "pricing.membership_3_months"
REFORMER = "pricing.reformer_8_sessions"
STUDENT = "pricing.student_monthly"
VOICE = "brand.voice_guidelines"
PHONE = "contact.phone"


@dataclass
class CommandEnv:
    env: Env
    factory: sessionmaker[Session]
    provider: FakeLLMProvider
    facts: dict[str, BusinessFact]

    # --- HTTP helpers ---

    def submit(self, role: Role, text: str, request_id: str | None = None) -> dict[str, Any]:
        response = self.env.call(
            role,
            "POST",
            "/commands",
            json={"text": text, "client_request_id": request_id or str(uuid.uuid4())},
        )
        assert response.status_code == 202, response.text
        body: dict[str, Any] = response.json()
        return body

    def process(self) -> int:
        """Run every due job (the interpretation) the way the worker would."""
        return run_due_jobs(self.env.clock, session_factory=self.factory)

    def get(self, role: Role, command_id: str) -> dict[str, Any]:
        response = self.env.call(role, "GET", f"/commands/{command_id}")
        assert response.status_code == 200, response.text
        body: dict[str, Any] = response.json()
        return body

    def run(self, role: Role, text: str) -> dict[str, Any]:
        """Submit, process, and return the command as the API shows it afterwards."""
        command = self.submit(role, text)
        self.process()
        return self.get(role, command["id"])

    def decide(
        self, role: Role, approval: dict[str, Any], decision: str = "approve", **overrides: Any
    ) -> Any:
        body = {"decision": decision, "payload_hash": approval["payload_hash"], **overrides}
        return self.env.call(role, "POST", f"/approvals/{approval['id']}/decision", json=body)

    def fact(self, key: str) -> BusinessFact:
        self.env.session.expire_all()
        found = self.facts[key]
        self.env.session.refresh(found)
        return found


@pytest.fixture
def provider() -> Iterator[FakeLLMProvider]:
    """The process-wide fake provider, scripted per test and reset afterwards."""
    fake = runtime.get_provider()
    assert isinstance(fake, FakeLLMProvider)
    fake.reset()
    yield fake
    fake.reset()


@pytest.fixture
def cmd(
    db_session: Session,
    make_client: Callable[[], TestClient],
    clock: FrozenClock,
    shared_session_factory: sessionmaker[Session],
    provider: FakeLLMProvider,
) -> CommandEnv:
    env = build_env(db_session, make_client, clock)
    facts = {
        MONTHLY: create_fact(db_session, env.workspace, MONTHLY, money("6000"), clock=clock),
        QUARTER: create_fact(
            db_session, env.workspace, QUARTER, money("16500", unit="package"), clock=clock
        ),
        REFORMER: create_fact(
            db_session, env.workspace, REFORMER, money("4800", unit="package"), clock=clock
        ),
        STUDENT: create_fact(
            db_session, env.workspace, STUDENT, money("4500"), verified=False, clock=clock
        ),
        PHONE: create_fact(
            db_session,
            env.workspace,
            PHONE,
            {"e164": "+905550000000"},
            clock=clock,
        ),
        VOICE: create_fact(
            db_session,
            env.workspace,
            VOICE,
            {"tr": "Sıcak ve kısa.", "en": "Warm and short."},
            clock=clock,
        ),
    }
    db_session.commit()
    return CommandEnv(env, shared_session_factory, provider, facts)


@pytest.fixture
def limited_budget() -> Callable[[int], Any]:
    """``with limited_budget(1): ...`` caps the daily LLM calls for jobs run inside."""

    def _limit(calls: int) -> Any:
        return runtime.override_runtime(
            settings=Settings(_env_file=None, llm_max_calls_per_workspace_per_day=calls)
        )

    return _limit
