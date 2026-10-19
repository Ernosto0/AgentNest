"""Fixtures for the inbox integration tests: a gym workspace with a connected simulated
Instagram account and helpers to deliver signed webhooks the way the simulator does."""

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.core.clock import FrozenClock
from app.core.config import Settings
from app.integrations.instagram import webhook_format as wf
from app.integrations.instagram.models import SocialAccount
from app.jobs.testing import run_due_jobs
from tests.helpers.env import Env, build_env

APP_SECRET = "dev-mock-instagram-app-secret"  # the test default of MOCK_INSTAGRAM_APP_SECRET
WEBHOOK_PATH = "/webhooks/instagram/mock"


@dataclass
class InboxEnv:
    env: Env
    account: SocialAccount
    factory: sessionmaker[Session]
    webhook_client: TestClient
    settings: Settings

    @property
    def session(self) -> Session:
        return self.env.session

    @property
    def clock(self) -> FrozenClock:
        return self.env.clock

    # --- webhook delivery ---

    def post(
        self,
        payload: dict[str, Any],
        *,
        secret: str | None = APP_SECRET,
        path: str = WEBHOOK_PATH,
    ) -> Any:
        body = wf.serialize(payload)
        headers = {"Content-Type": "application/json"}
        if secret is not None:
            headers[wf.SIGNATURE_HEADER] = wf.sign(body, secret)
        return self.webhook_client.post(path, content=body, headers=headers)

    def message_payload(
        self,
        text: str | None = "Aylık üyelik ne kadar?",
        *,
        customer: str = "cust-1",
        mid: str | None = None,
        at: datetime | None = None,
        account_id: str | None = None,
        attachments: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        return wf.build_message_payload(
            account_id or self.account.external_account_id,
            customer,
            mid or f"mid-{uuid.uuid4().hex[:10]}",
            text,
            at or self.clock.now(),
            attachments=attachments,
        )

    def deliver(self, text: str | None = "Aylık üyelik ne kadar?", **kwargs: Any) -> Any:
        return self.post(self.message_payload(text, **kwargs))

    def process(self) -> int:
        """Run every due job the way the worker would."""
        return run_due_jobs(self.clock, session_factory=self.factory)


@pytest.fixture
def inbox(
    db_session: Session,
    make_client: Callable[[], TestClient],
    clock: FrozenClock,
    shared_session_factory: sessionmaker[Session],
    settings: Settings,
) -> InboxEnv:
    env = build_env(db_session, make_client, clock)
    account = SocialAccount(
        workspace_id=env.workspace.id,
        provider_kind="mock",
        external_account_id="mock-golkent",
        username="golkent.demo",
        status="connected",
        capabilities={"messaging": True},
    )
    db_session.add(account)
    db_session.commit()
    return InboxEnv(env, account, shared_session_factory, make_client(), settings)
