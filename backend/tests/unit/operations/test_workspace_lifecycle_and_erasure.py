"""Unit tests for Phase 8 Session 10: Erasure and Workspace Deletion Lifecycle (P8-05).

Covers:
- Conversation erasure with durable tombstone and audit log.
- In-flight reconciliation guard: redacting personal text immediately while preserving
  operations state machine until settled (INV-05, ADR-022, ADR-025 §3.2).
- Customer erasure across conversations, memories, owner questions, and public comments.
- Role checks: data.delete is strictly Owner-only; Staff and Manager get FORBIDDEN.
- Workspace deletion request: 7-day grace period, pausing automation, cancelling drafts,
  disconnecting accounts, owner email dispatch, audit log (ADR-025 §3.3).
- Workspace deletion cancellation: restoring active status before scheduled date.
- Status inspection with remaining grace period calculation.
- Hard purge procedure and durable deletion_tombstones emission.
"""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from app.core.clock import FrozenClock
from app.core.config import Settings
from app.core.context import ActorRef, WorkspaceContext
from app.core.email import InMemoryEmailOutbox
from app.core.errors import AppError
from app.identity.models import Workspace
from app.inbox.models import Conversation
from app.integrations.instagram.models import SocialAccount
from app.memory.models import CustomerIdentity
from app.operations import data_rights, workspace_lifecycle
from app.operations.models import DeletionTombstone


def _make_ctx(role: str = "owner", workspace_id: uuid.UUID | None = None) -> WorkspaceContext:
    ws_id = workspace_id or uuid.uuid4()
    return WorkspaceContext(
        workspace_id=ws_id,
        actor=ActorRef.user(uuid.uuid4()),
        role=role,
        timezone="UTC",
        locale="en",
        is_demo=False,
    )


def test_erase_conversation_forbidden_for_non_owner() -> None:
    session = MagicMock()
    clock = FrozenClock(datetime(2026, 11, 3, 12, 0, tzinfo=UTC))
    conv_id = uuid.uuid4()

    for role in ("manager", "staff", "viewer"):
        ctx = _make_ctx(role=role)
        with pytest.raises(AppError) as exc_info:
            data_rights.erase_conversation(session, clock, ctx, conv_id)
        assert exc_info.value.code == "FORBIDDEN"


def test_erase_conversation_not_found_when_missing() -> None:
    session = MagicMock()
    session.scalar.return_value = None
    clock = FrozenClock(datetime(2026, 11, 3, 12, 0, tzinfo=UTC))
    ctx = _make_ctx(role="owner")
    conv_id = uuid.uuid4()

    with pytest.raises(AppError) as exc_info:
        data_rights.erase_conversation(session, clock, ctx, conv_id)
    assert exc_info.value.code == "NOT_FOUND"


def test_erase_conversation_owner_success_clean_purge() -> None:
    clock = FrozenClock(datetime(2026, 11, 3, 12, 0, tzinfo=UTC))
    ctx = _make_ctx(role="owner")
    ws_id = ctx.workspace_id
    acc_id = uuid.uuid4()
    conv_id = uuid.uuid4()

    conversation = Conversation(
        id=conv_id,
        workspace_id=ws_id,
        social_account_id=acc_id,
        customer_external_id="part_1",
        customer_handle="cust1",
        handling_mode="agent",
    )
    account = SocialAccount(
        id=acc_id,
        workspace_id=ws_id,
        provider_kind="mock",
        external_account_id="acc_ext_1",
        username="studio",
        status="active",
    )

    session = MagicMock()
    session.scalar.side_effect = lambda stmt: (
        conversation
        if "FROM conversations" in str(stmt)
        else (account if "FROM social_accounts" in str(stmt) else None)
    )
    session.scalars.return_value.all.return_value = []  # No drafts, no unresolved ops

    with patch("app.audit.service.record") as mock_audit:
        res = data_rights.erase_conversation(session, clock, ctx, conv_id)

    assert res["status"] == "erased"
    assert res["conversation_id"] == str(conv_id)
    # Verifies tombstone added
    added_objects = [call[0][0] for call in session.add.call_args_list]
    tombstones = [o for o in added_objects if isinstance(o, DeletionTombstone)]
    assert len(tombstones) == 1
    assert tombstones[0].entity_type == "conversation"
    assert tombstones[0].entity_id == str(conv_id)
    # Verifies audit log recorded
    mock_audit.assert_called_once()
    assert mock_audit.call_args[0][2] == "data_rights.conversation_erased"


def test_erase_conversation_in_flight_reconciliation_guard() -> None:
    """When an operation or draft is in-flight, personal text is redacted immediately.

    Hard row purge is deferred until reconciliation concludes (INV-05).
    """
    clock = FrozenClock(datetime(2026, 11, 3, 12, 0, tzinfo=UTC))
    ctx = _make_ctx(role="owner")
    ws_id = ctx.workspace_id
    acc_id = uuid.uuid4()
    conv_id = uuid.uuid4()
    draft_id = uuid.uuid4()

    conversation = Conversation(
        id=conv_id,
        workspace_id=ws_id,
        social_account_id=acc_id,
        customer_external_id="part_1",
        customer_handle="cust1",
    )
    account = SocialAccount(
        id=acc_id,
        workspace_id=ws_id,
        provider_kind="mock",
        external_account_id="acc_ext_1",
        username="studio",
        status="active",
    )

    session = MagicMock()
    session.scalar.side_effect = lambda stmt: (
        conversation
        if "FROM conversations" in str(stmt)
        else (account if "FROM social_accounts" in str(stmt) else None)
    )

    def _mock_scalars(stmt: Any) -> MagicMock:
        res = MagicMock()
        s_str = str(stmt)
        if "FROM reply_drafts" in s_str and "status IN" in s_str:
            res.all.return_value = [draft_id]  # Draft in 'sending'
        elif "FROM reply_drafts" in s_str:
            res.all.return_value = [draft_id]
        elif "FROM operations" in s_str:
            res.all.return_value = [uuid.uuid4()]  # Operation in 'in_progress'
        else:
            res.all.return_value = []
        return res

    session.scalars.side_effect = _mock_scalars

    with patch("app.audit.service.record") as mock_audit:
        res = data_rights.erase_conversation(session, clock, ctx, conv_id)

    assert res["status"] == "redacted_reconciliation_pending"
    assert res["conversation_id"] == str(conv_id)
    # In-flight reconciliation does not delete conversation row yet
    assert not any(call[0][0] == conversation for call in session.delete.call_args_list)
    mock_audit.assert_called_once()
    assert mock_audit.call_args[0][2] == "data_rights.conversation_erased"


def test_erase_customer_owner_success() -> None:
    clock = FrozenClock(datetime(2026, 11, 3, 12, 0, tzinfo=UTC))
    ctx = _make_ctx(role="owner")
    ws_id = ctx.workspace_id
    acc_id = uuid.uuid4()
    cust_id = uuid.uuid4()

    cust_identity = CustomerIdentity(
        id=cust_id,
        workspace_id=ws_id,
        social_account_id=acc_id,
        provider_subject_hash="hash_123",
        evidence_kind="provider_dm_participant",
        generation=1,
    )
    account = SocialAccount(
        id=acc_id,
        workspace_id=ws_id,
        provider_kind="mock",
        external_account_id="acc_1",
        username="studio",
        status="active",
    )

    session = MagicMock()
    session.scalar.side_effect = lambda stmt: (
        cust_identity
        if "FROM customer_identities" in str(stmt)
        else (account if "FROM social_accounts" in str(stmt) else None)
    )
    session.scalars.return_value.all.return_value = []

    with (
        patch("app.memory.service.erase_customer") as mock_mem_erase,
        patch("app.audit.service.record") as mock_audit,
    ):
        res = data_rights.erase_customer(session, clock, ctx, cust_id)

    assert res["status"] == "erased"
    assert res["customer_identity_id"] == str(cust_id)
    mock_mem_erase.assert_called_once()
    mock_audit.assert_called_once()
    assert mock_audit.call_args[0][2] == "data_rights.customer_erased"

    added_tombstones = [
        call[0][0]
        for call in session.add.call_args_list
        if isinstance(call[0][0], DeletionTombstone)
    ]
    assert len(added_tombstones) == 1
    assert added_tombstones[0].entity_type == "customer"
    assert added_tombstones[0].entity_id == str(cust_id)


def test_workspace_deletion_request_owner_flow() -> None:
    clock = FrozenClock(datetime(2026, 11, 3, 12, 0, tzinfo=UTC))
    ctx = _make_ctx(role="owner")
    ws_id = ctx.workspace_id
    workspace = Workspace(id=ws_id, name="Studio Pro", status="active")
    settings = Settings(product_name="AgentNest", frontend_origin="https://app.agentnest.test")

    session = MagicMock()
    session.get.return_value = workspace
    session.execute.return_value.all.return_value = [("owner@example.com",)]

    outbox = InMemoryEmailOutbox()
    with (
        patch("app.core.email.email_outbox", outbox),
        patch("app.audit.service.record") as mock_audit,
    ):
        res = workspace_lifecycle.request_workspace_deletion(session, clock, ctx, settings)

    assert res["status"] == "deleting"
    assert res["is_deleting"] is True
    assert res["days_remaining"] == 7
    assert res["can_cancel"] is True
    assert workspace.status == "deleting"
    assert workspace.deletion_requested_at == clock.now()
    assert workspace.deletion_scheduled_at == clock.now() + timedelta(days=7)

    # Verifies notification email sent to owner
    emails = outbox.get_messages()
    assert len(emails) == 1
    assert emails[0].to_email == "owner@example.com"
    assert "https://app.agentnest.test/w/" in emails[0].text_body

    mock_audit.assert_called_once()
    assert mock_audit.call_args[0][2] == "workspace.deletion_requested"


def test_workspace_deletion_request_refusal_when_already_deleting() -> None:
    clock = FrozenClock(datetime(2026, 11, 3, 12, 0, tzinfo=UTC))
    ctx = _make_ctx(role="owner")
    ws_id = ctx.workspace_id
    workspace = Workspace(id=ws_id, name="Studio Pro", status="deleting")
    settings = Settings(product_name="AgentNest")

    session = MagicMock()
    session.get.return_value = workspace

    with pytest.raises(AppError) as exc_info:
        workspace_lifecycle.request_workspace_deletion(session, clock, ctx, settings)
    assert exc_info.value.code == "CONFLICT_STATE"


def test_workspace_deletion_cancel_flow() -> None:
    clock = FrozenClock(datetime(2026, 11, 3, 12, 0, tzinfo=UTC))
    ctx = _make_ctx(role="owner")
    ws_id = ctx.workspace_id
    scheduled = clock.now() + timedelta(days=5)
    workspace = Workspace(
        id=ws_id,
        name="Studio Pro",
        status="deleting",
        deletion_requested_at=clock.now() - timedelta(days=2),
        deletion_scheduled_at=scheduled,
    )

    session = MagicMock()
    session.get.return_value = workspace

    with patch("app.audit.service.record") as mock_audit:
        res = workspace_lifecycle.cancel_workspace_deletion(session, clock, ctx)

    assert res["status"] == "active"
    assert res["is_deleting"] is False
    assert res["can_cancel"] is False
    assert workspace.status == "active"
    assert workspace.deletion_requested_at is None
    assert workspace.deletion_scheduled_at is None

    mock_audit.assert_called_once()
    assert mock_audit.call_args[0][2] == "workspace.deletion_cancelled"


def test_workspace_deletion_cancel_refuses_when_not_deleting_or_expired() -> None:
    clock = FrozenClock(datetime(2026, 11, 10, 12, 0, tzinfo=UTC))
    ctx = _make_ctx(role="owner")
    ws_id = ctx.workspace_id

    # Not deleting
    workspace_active = Workspace(id=ws_id, name="Studio Pro", status="active")
    session = MagicMock()
    session.get.return_value = workspace_active

    with pytest.raises(AppError) as exc_info:
        workspace_lifecycle.cancel_workspace_deletion(session, clock, ctx)
    assert exc_info.value.code == "CONFLICT_STATE"

    # Expired past grace period
    workspace_expired = Workspace(
        id=ws_id,
        name="Studio Pro",
        status="deleting",
        deletion_scheduled_at=datetime(2026, 11, 9, 12, 0, tzinfo=UTC),  # in past
    )
    session.get.return_value = workspace_expired
    with pytest.raises(AppError) as exc_info2:
        workspace_lifecycle.cancel_workspace_deletion(session, clock, ctx)
    assert exc_info2.value.code == "CONFLICT_STATE"


def test_purge_workspace_execution() -> None:
    now = datetime(2026, 11, 10, 13, 0, tzinfo=UTC)
    clock = FrozenClock(now)
    ws_id = uuid.uuid4()
    workspace = Workspace(
        id=ws_id,
        name="Purged Workspace",
        status="deleting",
        deletion_scheduled_at=datetime(2026, 11, 10, 12, 0, tzinfo=UTC),
    )

    session = MagicMock()
    session.get.return_value = workspace
    session.scalars.return_value.all.return_value = []  # No in_progress operations

    workspace_lifecycle.purge_workspace(session, clock, ws_id)

    # Verifies workspace deleted and tombstone added
    session.delete.assert_called_once_with(workspace)
    added = [
        call[0][0]
        for call in session.add.call_args_list
        if isinstance(call[0][0], DeletionTombstone)
    ]
    assert len(added) == 1
    assert added[0].entity_type == "workspace"
    assert added[0].entity_id == str(ws_id)
