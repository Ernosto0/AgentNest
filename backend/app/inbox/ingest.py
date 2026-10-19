"""Webhook ingestion (workflows.md §C step 1), shared by the HTTP routes and the simulator.

The path selects the provider kind and therefore the secret, so the signature of the **raw
body** is verified before anything is parsed. After a valid signature every item is stored (or
recorded as ignored) and the answer is always "ok": the provider must not retry what we have
already seen. The workspace is resolved from the receiving account id and the kind, nothing
else. No external call happens here.
"""

import hashlib
import json
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import timedelta
from typing import Literal

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.audit import service as audit
from app.audit.models import AuditLog
from app.core.clock import Clock
from app.core.config import Settings
from app.core.ids import new_id
from app.core.logging import get_logger
from app.inbox.models import InboundEvent
from app.inbox.payloads import ProcessInboundEventPayload
from app.integrations.instagram import queries
from app.integrations.instagram.base import NormalizedInboundEvent
from app.integrations.instagram.registry import get_webhook_codec
from app.integrations.instagram.webhook_format import SIGNATURE_HEADER
from app.jobs.queue import enqueue

log = get_logger(__name__)

SIGNATURE_FAILURE_ALERT_PER_HOUR = 10


@dataclass(frozen=True)
class IngestResult:
    status: Literal["ok", "invalid_signature"]
    received: int = 0
    duplicates: int = 0
    ignored: int = 0


def dedup_key(event: NormalizedInboundEvent) -> str:
    """``ig:{account}:mid:{mid}`` for messages and echoes; a content hash for the rest."""
    account = event.account_id or "unknown"
    if event.mid and event.event_type in ("message", "echo"):
        return f"ig:{account}:mid:{event.mid}"
    digest = hashlib.sha256(
        json.dumps(event.raw_item, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return f"ig:{account}:{event.event_type}:{digest}"


def _header(headers: Mapping[str, str], name: str) -> str | None:
    lowered = name.lower()
    for key, value in headers.items():
        if key.lower() == lowered:
            return value
    return None


def _record_invalid_signature(session: Session, clock: Clock, provider_kind: str) -> None:
    """A system-level audit entry (no payload) is the signature-failure counter."""
    audit.record(
        session,
        None,
        "webhook.signature_invalid",
        None,
        None,
        {"provider_kind": provider_kind},
        is_simulated=provider_kind == "mock",
        clock=clock,
    )
    session.flush()
    since = clock.now() - timedelta(hours=1)
    recent = session.scalar(
        select(func.count())
        .select_from(AuditLog)
        .where(AuditLog.action == "webhook.signature_invalid", AuditLog.occurred_at >= since)
    )
    if (recent or 0) >= SIGNATURE_FAILURE_ALERT_PER_HOUR:
        log.error("webhook_signature_failures", provider_kind=provider_kind, last_hour=recent)
    else:
        log.warning("webhook_signature_invalid", provider_kind=provider_kind)


def ingest_webhook(
    session: Session,
    clock: Clock,
    settings: Settings,
    provider_kind: str,
    raw_body: bytes,
    headers: Mapping[str, str],
) -> IngestResult:
    """Verify, store, enqueue. Commits. Raises ``ProviderNotEnabled`` for a disabled kind."""
    codec = get_webhook_codec(provider_kind, settings)
    if not codec.verify_signature(raw_body, _header(headers, SIGNATURE_HEADER)):
        _record_invalid_signature(session, clock, provider_kind)
        session.commit()
        return IngestResult(status="invalid_signature")

    try:
        payload = json.loads(raw_body)
    except ValueError:
        log.warning("webhook_body_not_json", provider_kind=provider_kind)
        return IngestResult(status="ok")

    received = duplicates = ignored = 0
    for event in codec.parse_webhook(payload):
        outcome = _store(session, clock, provider_kind, event)
        if outcome == "duplicate":
            duplicates += 1
        else:
            received += 1
            ignored += outcome == "ignored"
    session.commit()
    return IngestResult(status="ok", received=received, duplicates=duplicates, ignored=ignored)


def _store(
    session: Session, clock: Clock, provider_kind: str, event: NormalizedInboundEvent
) -> Literal["queued", "ignored", "duplicate"]:
    account = (
        queries.resolve_by_external(session, provider_kind, event.account_id)
        if event.account_id
        else None
    )
    status = "received"
    ignore_reason: str | None = None
    if account is None:
        status, ignore_reason = "ignored", "UNKNOWN_ACCOUNT"
    elif account.status == "disconnected":
        status, ignore_reason = "ignored", "ACCOUNT_DISCONNECTED"
    elif event.event_type == "other":
        status, ignore_reason = "ignored", "UNSUPPORTED_EVENT"

    event_id = new_id()
    correlation_id = uuid.uuid4()
    inserted = session.scalar(
        pg_insert(InboundEvent)
        .values(
            id=event_id,
            workspace_id=account.workspace_id if account else None,
            social_account_id=account.id if account else None,
            provider_kind=provider_kind,
            dedup_key=dedup_key(event),
            event_type=event.event_type,
            payload=event.raw_item,
            status=status,
            ignore_reason=ignore_reason,
            correlation_id=correlation_id,
            is_simulated=provider_kind == "mock",
            received_at=clock.now(),
        )
        .on_conflict_do_nothing(index_elements=["dedup_key"])
        .returning(InboundEvent.id)
    )
    if inserted is None:
        return "duplicate"
    if status == "ignored" or account is None:
        return "ignored"
    enqueue(
        session,
        "process_inbound_event",
        ProcessInboundEventPayload(event_id=event_id),
        workspace_id=account.workspace_id,
        correlation_id=correlation_id,
        dedup_key=f"process_inbound_event:{event_id}",
        clock=clock,
    )
    return "queued"
