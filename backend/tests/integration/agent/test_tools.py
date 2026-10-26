"""The broker derives tenant and visibility from a server-owned context."""

import uuid

from sqlalchemy.orm import Session

from app.agent.models import AgentThread
from app.agent.tools import BrokerContext, build_default_broker
from app.core.clock import FrozenClock
from app.core.context import ActorRef, WorkspaceContext
from app.identity.models import Workspace
from app.integrations.instagram.models import SocialAccount


def _seed(db: Session, *, surface: str = "dm") -> BrokerContext:
    workspace = Workspace(
        name="Broker",
        slug=f"broker-{uuid.uuid4().hex[:8]}",
        business_category="services",
        market="global",
        default_locale="en",
        timezone="UTC",
        currency="USD",
    )
    db.add(workspace)
    db.flush()
    account = SocialAccount(
        workspace_id=workspace.id, provider_kind="mock", external_account_id=uuid.uuid4().hex
    )
    db.add(account)
    db.flush()
    thread = AgentThread(
        workspace_id=workspace.id,
        social_account_id=account.id,
        surface=surface,
        source_ref=uuid.uuid4().hex,
    )
    db.add(thread)
    db.flush()
    return BrokerContext(
        WorkspaceContext(workspace.id, ActorRef.system("test"), None, "UTC", "en", False),
        account.id,
        thread.id,
        surface,  # type: ignore[arg-type]
        "customer",
    )


def test_public_context_cannot_read_private_thread(db_session: Session, clock: FrozenClock) -> None:
    broker = build_default_broker()
    public = _seed(db_session, surface="comment")
    assert {tool.name for tool in broker.available(public)} == {"knowledge.read"}
    denied = broker.dispatch(
        db_session, clock, public, name="thread.read", version="v1", arguments={"limit": 1}
    )
    assert (denied.ok, denied.error) == (False, "TOOL_FORBIDDEN")


def test_unknown_invalid_and_foreign_scope_fail_closed(
    db_session: Session, clock: FrozenClock
) -> None:
    broker = build_default_broker()
    private = _seed(db_session)
    assert (
        broker.dispatch(
            db_session, clock, private, name="delegate.all", version="v1", arguments={}
        ).error
        == "UNKNOWN_TOOL"
    )
    assert (
        broker.dispatch(
            db_session,
            clock,
            private,
            name="thread.read",
            version="v1",
            arguments={"limit": 1, "workspace_id": str(private.workspace.workspace_id)},
        ).error
        == "TOOL_ARGUMENT_INVALID"
    )
    assert (
        broker.dispatch(
            db_session, clock, private, name="thread.read", version="v0", arguments={"limit": 1}
        ).error
        == "STALE_TOOL_SCHEMA"
    )
    assert (
        broker.dispatch(
            db_session, clock, private, name="thread.read", version="v1", arguments={"limit": 99}
        ).error
        == "TOOL_ARGUMENT_INVALID"
    )
    foreign = _seed(db_session)
    changed = BrokerContext(
        private.workspace, foreign.account_id, private.thread_id, "dm", "customer"
    )
    assert (
        broker.dispatch(
            db_session, clock, changed, name="thread.read", version="v1", arguments={"limit": 1}
        ).error
        == "TOOL_SCOPE_INVALID"
    )
    result = broker.dispatch(
        db_session, clock, private, name="thread.read", version="v1", arguments={"limit": 1}
    )
    assert result.ok and result.data == {"messages": []}
