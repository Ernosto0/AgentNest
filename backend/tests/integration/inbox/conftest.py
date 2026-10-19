"""Fixtures for the inbox integration tests: a gym workspace with a connected simulated
Instagram account and helpers to deliver signed webhooks the way the simulator does."""

import uuid
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.ai import runtime
from app.approvals import service as approvals_service
from app.approvals.models import Approval
from app.core.clock import FrozenClock
from app.core.config import Settings
from app.handlers import load_handlers
from app.inbox.context import DraftContext, DraftSkip, prepare
from app.inbox.drafting import DraftPlan, make_plan
from app.inbox.models import Conversation, Message, ReplyDraft
from app.inbox.payloads import DraftReplyPayload
from app.integrations.instagram import webhook_format as wf
from app.integrations.instagram.models import SocialAccount
from app.integrations.llm import FakeLLMProvider
from app.jobs.models import Job
from app.jobs.registry import JobContext, get_handler, job_handler, registry_snapshot
from app.jobs.testing import run_due_jobs
from app.knowledge.models import BusinessFact
from tests.helpers.env import Env, build_env
from tests.helpers.gym import seed_gym_facts

# Register every job handler before any test snapshots the registry: a module imported for the
# first time inside a snapshot would lose its handlers when the snapshot is restored.
load_handlers()

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

    def deliver_and_process(
        self, text: str | None = "Aylık üyelik ne kadar?", **kwargs: Any
    ) -> Any:
        response = self.deliver(text, **kwargs)
        assert response.status_code == 200, response.text
        self.process()
        return response

    # --- drafting ---

    def seed_facts(self, **kwargs: Any) -> dict[str, BusinessFact]:
        return seed_gym_facts(self.session, self.env.workspace, self.clock, **kwargs)

    def context(
        self,
        *,
        message_id: uuid.UUID | None = None,
        requested: bool = False,
        customer: str = "cust-1",
    ) -> DraftContext | DraftSkip:
        self.session.expire_all()
        conversation = self.conversation(customer)
        return prepare(
            self.session,
            self.clock,
            self.env.workspace.id,
            conversation.id,
            message_id=message_id,
            requested=requested,
        )

    def plan(self, context: DraftContext) -> DraftPlan:
        deps = runtime.runner_deps(self.factory, self.clock)
        return make_plan(deps, context, uuid.uuid4())

    def drafted(self, text: str | None, **kwargs: Any) -> DraftPlan:
        """Deliver ``text``, process it, and run the pipeline on the result."""
        self.deliver_and_process(text, **kwargs)
        context = self.context()
        assert isinstance(context, DraftContext), context
        return self.plan(context)

    # --- reading state ---

    def conversation(self, customer: str = "cust-1") -> Conversation:
        self.session.expire_all()
        return self.session.scalars(
            select(Conversation).where(Conversation.customer_external_id == customer)
        ).one()

    def messages(self, customer: str = "cust-1") -> list[Message]:
        self.session.expire_all()
        conversation = self.conversation(customer)
        return list(
            self.session.scalars(
                select(Message)
                .where(Message.conversation_id == conversation.id)
                .order_by(Message.provider_timestamp, Message.created_at)
            )
        )

    def jobs(self, job_type: str) -> list[Job]:
        self.session.expire_all()
        return list(
            self.session.scalars(
                select(Job).where(Job.job_type == job_type).order_by(Job.created_at, Job.id)
            )
        )

    def draft(self, customer: str = "cust-1") -> ReplyDraft | None:
        self.session.expire_all()
        conversation = self.conversation(customer)
        return self.session.scalars(
            select(ReplyDraft)
            .where(ReplyDraft.conversation_id == conversation.id)
            .order_by(ReplyDraft.created_at.desc(), ReplyDraft.id)
        ).first()

    # --- building state ---

    def make_draft(
        self,
        status: str = "pending_approval",
        *,
        customer: str = "cust-1",
        with_approval: bool | None = None,
        text: str = "Aylık üyelik ücretimiz 6.000 ₺.",
    ) -> ReplyDraft:
        """A draft on the customer's conversation, with a pending approval where one belongs."""
        conversation = self.conversation(customer)
        last = self.messages(customer)[-1]
        decision = {
            "pending_approval": "approval_required",
            "needs_human": "human_required",
            "blocked": "blocked",
        }.get(status, "approval_required")
        draft = ReplyDraft(
            workspace_id=self.env.workspace.id,
            conversation_id=conversation.id,
            covers_through_message_id=last.id,
            source="ai",
            language="tr",
            intent="pricing",
            text=text,
            decision=decision,
            decision_reasons=["POLICY_REQUIRES_APPROVAL"],
            status=status,
            created_by_actor_type="system",
            is_simulated=True,
            created_at=self.clock.now(),
        )
        self.session.add(draft)
        self.session.flush()
        if with_approval if with_approval is not None else status == "pending_approval":
            approval = approvals_service.request(
                self.session,
                self.clock,
                self.env.ctx(self.env.owner),
                kind="authorization",
                action="reply.send",
                subject_type="reply_draft",
                subject_id=draft.id,
                subject_version=draft.version,
                payload={"draft_id": str(draft.id)},
                summary={"text": text},
                required_permission="reply.approve",
                expires_at=self.clock.now() + timedelta(hours=1),
                is_simulated=True,
            )
            draft.approval_id = approval.id
        self.session.commit()
        return draft

    def approval_status(self, draft: ReplyDraft) -> str | None:
        self.session.expire_all()
        if draft.approval_id is None:
            return None
        approval = self.session.get(Approval, draft.approval_id)
        return approval.status if approval else None


@pytest.fixture(autouse=True)
def _draft_reply_stub() -> Iterator[None]:
    """Until the drafting job exists, processing only needs the job type to be enqueueable."""
    if get_handler("draft_reply") is not None:
        yield
        return
    with registry_snapshot():

        @job_handler("draft_reply", DraftReplyPayload)
        def _noop(job: JobContext) -> None:
            return None

        yield


@pytest.fixture
def provider() -> Iterator[FakeLLMProvider]:
    """The process-wide fake LLM provider, scripted per test and reset afterwards."""
    fake = runtime.get_provider()
    assert isinstance(fake, FakeLLMProvider)
    fake.reset()
    yield fake
    fake.reset()


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
