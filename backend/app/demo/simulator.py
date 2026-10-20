"""The developer simulator (integrations.md §3.3): customers and failures for the mock Instagram.

A simulated customer message is a real Meta-format webhook, signed with the mock app secret and
submitted to the **same ingestion function** as a real one; the only simulator-only step is
recording the message in ``sim_inbound_messages``, which is what opens the mock's 24 h window.
Nothing here is reachable in production (``DEMO_TOOLS_ENABLED`` must be false there).
"""

import re
import unicodedata
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session, sessionmaker

from app.core.clock import Clock
from app.core.config import Settings
from app.core.errors import AppError
from app.core.ids import new_id
from app.inbox.ingest import IngestResult, ingest_webhook
from app.inbox.models import Conversation
from app.integrations.instagram import queries, webhook_format
from app.integrations.instagram.base import AccountRef
from app.integrations.instagram.mock import MockInstagramProvider
from app.integrations.instagram.models import (
    SimContainer,
    SimFailureRule,
    SimPublishedMedia,
    SocialAccount,
)

SCRIPTS_FILE = Path(__file__).parent / "scripts" / "customer_messages.yaml"


class Script(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    label: dict[str, str]
    customer_alias: str
    text: str | None
    attachments: list[dict[str, str]] = []
    expect: str


def load_scripts(path: Path = SCRIPTS_FILE) -> list[Script]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return [Script.model_validate(item) for item in data["scripts"]]


def get_script(script_id: str) -> Script:
    for script in load_scripts():
        if script.id == script_id:
            return script
    raise AppError("NOT_FOUND")


@dataclass(frozen=True)
class PreparedWebhook:
    """A signed webhook ready to be submitted in-process or posted over HTTP."""

    body: bytes
    headers: dict[str, str]
    customer_id: str
    mid: str


def customer_id_for(alias: str) -> str:
    """A stable provider-style id for a simulated customer, from the alias."""
    folded = unicodedata.normalize("NFKD", alias).encode("ascii", "ignore").decode().lower()
    slug = re.sub(r"[^a-z0-9]+", "-", folded).strip("-") or "customer"
    return f"sim-{slug}"


def mock_account(session: Session, workspace_id: uuid.UUID) -> SocialAccount:
    account = queries.get_active_for_workspace(session, workspace_id)
    if account is None or account.provider_kind != "mock":
        raise AppError("ACCOUNT_NOT_CONNECTED")
    return account


def _ref(account: SocialAccount) -> AccountRef:
    return AccountRef(account.id, account.workspace_id, account.external_account_id)


def _sign(payload: dict[str, Any], settings: Settings) -> tuple[bytes, dict[str, str]]:
    body = webhook_format.serialize(payload)
    secret = settings.mock_instagram_app_secret.get_secret_value()
    return body, {webhook_format.SIGNATURE_HEADER: webhook_format.sign(body, secret)}


def prepare_customer_message(
    session_factory: sessionmaker[Session],
    clock: Clock,
    settings: Settings,
    workspace_id: uuid.UUID,
    *,
    customer_alias: str,
    text: str | None,
    attachments: list[dict[str, str]] | None = None,
) -> PreparedWebhook:
    """Open the mock's window for the customer, remember the alias, and sign the webhook."""
    customer = customer_id_for(customer_alias)
    mid = f"sim-mid-{uuid.uuid4().hex[:16]}"
    now = clock.now()
    with session_factory() as session:
        account = mock_account(session, workspace_id)
        session.execute(  # the conversation exists with its display name before the first event
            pg_insert(Conversation)
            .values(
                id=new_id(),
                workspace_id=workspace_id,
                social_account_id=account.id,
                customer_external_id=customer,
                customer_handle=customer_alias,
                is_simulated=True,
            )
            .on_conflict_do_nothing(index_elements=["social_account_id", "customer_external_id"])
        )
        session.commit()
        ref = _ref(account)
        external_id = account.external_account_id
    provider = MockInstagramProvider(
        session_factory, clock, settings.mock_instagram_app_secret.get_secret_value()
    )
    provider.record_simulated_inbound(ref, customer, mid, now)
    payload = webhook_format.build_message_payload(
        external_id, customer, mid, text, now, attachments=attachments
    )
    body, headers = _sign(payload, settings)
    return PreparedWebhook(body, headers, customer, mid)


def simulate_customer_message(
    session_factory: sessionmaker[Session],
    clock: Clock,
    settings: Settings,
    workspace_id: uuid.UUID,
    *,
    customer_alias: str,
    text: str | None,
    attachments: list[dict[str, str]] | None = None,
) -> IngestResult:
    """Deliver a simulated customer message through the real ingestion path (in-process)."""
    prepared = prepare_customer_message(
        session_factory,
        clock,
        settings,
        workspace_id,
        customer_alias=customer_alias,
        text=text,
        attachments=attachments,
    )
    with session_factory() as session:
        return ingest_webhook(session, clock, settings, "mock", prepared.body, prepared.headers)


def prepare_native_reply(
    session_factory: sessionmaker[Session],
    clock: Clock,
    settings: Settings,
    workspace_id: uuid.UUID,
    *,
    conversation_id: uuid.UUID,
    text: str,
) -> PreparedWebhook:
    """The business answers in the Instagram app: an echo with an id we have never seen."""
    with session_factory() as session:
        account = mock_account(session, workspace_id)
        conversation = session.scalars(
            select(Conversation).where(
                Conversation.workspace_id == workspace_id, Conversation.id == conversation_id
            )
        ).one_or_none()
        if conversation is None or conversation.social_account_id != account.id:
            raise AppError("NOT_FOUND")
        customer, external_id = conversation.customer_external_id, account.external_account_id
    mid = f"native-mid-{uuid.uuid4().hex[:16]}"
    payload = webhook_format.build_echo_payload(external_id, customer, mid, text, clock.now())
    body, headers = _sign(payload, settings)
    return PreparedWebhook(body, headers, customer, mid)


def simulate_owner_native_reply(
    session_factory: sessionmaker[Session],
    clock: Clock,
    settings: Settings,
    workspace_id: uuid.UUID,
    *,
    conversation_id: uuid.UUID,
    text: str,
) -> IngestResult:
    prepared = prepare_native_reply(
        session_factory, clock, settings, workspace_id, conversation_id=conversation_id, text=text
    )
    with session_factory() as session:
        return ingest_webhook(session, clock, settings, "mock", prepared.body, prepared.headers)


# --- failure rules -------------------------------------------------------------------------------


def set_failure_rule(
    session: Session,
    workspace_id: uuid.UUID,
    *,
    operation: str,
    mode: str,
    remaining: int | None,
    retry_after_s: int | None,
) -> SimFailureRule:
    account = mock_account(session, workspace_id)
    rule = SimFailureRule(
        workspace_id=workspace_id,
        social_account_id=account.id,
        operation=operation,
        mode=mode,
        remaining=remaining,
        retry_after_s=retry_after_s,
    )
    session.add(rule)
    session.commit()
    return rule


def list_failure_rules(session: Session, workspace_id: uuid.UUID) -> list[SimFailureRule]:
    return list(
        session.scalars(
            select(SimFailureRule)
            .where(SimFailureRule.workspace_id == workspace_id)
            .order_by(SimFailureRule.created_at, SimFailureRule.id)
        )
    )


def delete_failure_rule(session: Session, workspace_id: uuid.UUID, rule_id: uuid.UUID) -> None:
    rule = session.scalars(
        select(SimFailureRule).where(
            SimFailureRule.workspace_id == workspace_id, SimFailureRule.id == rule_id
        )
    ).one_or_none()
    if rule is None:
        raise AppError("NOT_FOUND")
    session.delete(rule)
    session.commit()


# --- what the simulator published -------------------------------------------------------------


def list_published(
    session: Session, workspace_id: uuid.UUID, *, limit: int = 100
) -> list[tuple[SimPublishedMedia, SimContainer]]:
    """The simulator's evidence of what went out, newest first (the "exactly one post" demo)."""
    rows = session.execute(
        select(SimPublishedMedia, SimContainer)
        .join(SimContainer, SimContainer.container_id == SimPublishedMedia.container_id)
        .where(
            SimPublishedMedia.workspace_id == workspace_id,
            SimContainer.workspace_id == workspace_id,
        )
        .order_by(SimPublishedMedia.published_at.desc(), SimPublishedMedia.id)
        .limit(limit)
    )
    return [(media, container) for media, container in rows]
