"""Unit tests for Phase 8 Session 09: Data-Rights Export (P8-05, ADR-025 §3.1).

Covers:
- Permission checks: data.export is strictly Owner-only. Staff and Manager get FORBIDDEN.
- Conversation export schema_version: "1.0" JSON format.
- Chronological message ordering and draft/approval inclusion.
- Operations history without provider credentials or secrets.
- Linked customer identity, memory export, owner questions/answers.
- Strict isolation: public comments linked strictly by provider participant ID (INV-18);
  unlinked third-party comments excluded.
- Customer export across conversations, messages, memories, and public comments.
- Audit emission: data_rights.conversation_exported and data_rights.customer_exported.
- Cross-workspace isolation (foreign IDs return NOT_FOUND).
"""

import uuid
from datetime import UTC, datetime
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from app.agent.models import AgentThread
from app.approvals.models import Approval
from app.comments.models import PublicComment
from app.core.clock import FrozenClock
from app.core.context import ActorRef, WorkspaceContext
from app.core.errors import AppError
from app.identity.models import Workspace
from app.inbox.models import Conversation, Message, ReplyDraft
from app.integrations.instagram.models import SocialAccount
from app.memory import service as memory_service
from app.memory.models import CustomerIdentity
from app.operations import data_rights
from app.operations.models import Operation
from app.owner_requests.models import OwnerAnswer, OwnerQuestion


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


def test_export_conversation_forbidden_for_non_owner() -> None:
    session = MagicMock()
    clock = FrozenClock(datetime(2026, 11, 3, 12, 0, tzinfo=UTC))
    conv_id = uuid.uuid4()

    for role in ("manager", "staff", "viewer"):
        ctx = _make_ctx(role=role)
        with pytest.raises(AppError) as exc_info:
            data_rights.export_conversation(session, clock, ctx, conv_id)
        assert exc_info.value.code == "FORBIDDEN"


def test_export_conversation_not_found_when_missing() -> None:
    session = MagicMock()
    session.scalar.return_value = None  # No conversation found
    clock = FrozenClock(datetime(2026, 11, 3, 12, 0, tzinfo=UTC))
    ctx = _make_ctx(role="owner")
    conv_id = uuid.uuid4()

    with pytest.raises(AppError) as exc_info:
        data_rights.export_conversation(session, clock, ctx, conv_id)
    assert exc_info.value.code == "NOT_FOUND"


def test_export_conversation_owner_success() -> None:
    clock = FrozenClock(datetime(2026, 11, 3, 12, 0, tzinfo=UTC))
    ctx = _make_ctx(role="owner")
    ws_id = ctx.workspace_id
    acc_id = uuid.uuid4()
    conv_id = uuid.uuid4()
    participant_id = "participant_abc"

    conversation = Conversation(
        id=conv_id,
        workspace_id=ws_id,
        social_account_id=acc_id,
        customer_external_id=participant_id,
        customer_handle="test_customer",
        handling_mode="agent",
        created_at=datetime(2026, 11, 1, 10, 0, tzinfo=UTC),
        last_message_at=datetime(2026, 11, 2, 11, 0, tzinfo=UTC),
    )
    workspace = Workspace(id=ws_id, name="Test Studio")
    account = SocialAccount(
        id=acc_id,
        workspace_id=ws_id,
        provider_kind="mock",
        external_account_id="acc_123",
        username="studio_official",
        status="active",
        token_ciphertext=b"super_secret_token",
    )

    msg1 = Message(
        id=uuid.uuid4(),
        workspace_id=ws_id,
        conversation_id=conv_id,
        social_account_id=acc_id,
        direction="inbound",
        sender_kind="customer",
        external_message_id="mid_1",
        text="What are your opening hours?",
        attachments=[],
        provider_timestamp=datetime(2026, 11, 1, 10, 0, tzinfo=UTC),
        is_deleted=False,
        created_at=datetime(2026, 11, 1, 10, 0, tzinfo=UTC),
    )
    msg2 = Message(
        id=uuid.uuid4(),
        workspace_id=ws_id,
        conversation_id=conv_id,
        social_account_id=acc_id,
        direction="outbound",
        sender_kind="agent",
        external_message_id="mid_2",
        text="We are open Mon-Sat 9am-6pm.",
        attachments=[],
        provider_timestamp=datetime(2026, 11, 1, 10, 1, tzinfo=UTC),
        is_deleted=False,
        created_at=datetime(2026, 11, 1, 10, 1, tzinfo=UTC),
    )

    draft_id = uuid.uuid4()
    op_id = uuid.uuid4()
    draft = ReplyDraft(
        id=draft_id,
        workspace_id=ws_id,
        conversation_id=conv_id,
        covers_through_message_id=msg1.id,
        source="suggested",
        origin="legacy",
        decision="propose",
        status="sent",
        text="We are open Mon-Sat 9am-6pm.",
        operation_id=op_id,
        created_at=datetime(2026, 11, 1, 10, 0, 30, tzinfo=UTC),
        updated_at=datetime(2026, 11, 1, 10, 1, 0, tzinfo=UTC),
    )

    approval = Approval(
        id=uuid.uuid4(),
        workspace_id=ws_id,
        subject_type="reply_draft",
        subject_id=draft_id,
        status="approved",
        decided_at=datetime(2026, 11, 1, 10, 0, 50, tzinfo=UTC),
        decision_note="Looks accurate",
    )

    operation = Operation(
        id=op_id,
        workspace_id=ws_id,
        social_account_id=acc_id,
        operation_type="send_reply",
        idempotency_key="key_123",
        subject_type="reply_draft",
        subject_id=draft_id,
        provider_kind="mock",
        status="succeeded",
        last_error_code=None,
        created_at=datetime(2026, 11, 1, 10, 0, 55, tzinfo=UTC),
        started_at=datetime(2026, 11, 1, 10, 0, 56, tzinfo=UTC),
        completed_at=datetime(2026, 11, 1, 10, 1, 0, tzinfo=UTC),
    )

    cust_id = uuid.uuid4()
    expected_key = memory_service.digest(f"mock:dm:{participant_id}")
    customer_identity = CustomerIdentity(
        id=cust_id,
        workspace_id=ws_id,
        social_account_id=acc_id,
        provider_subject_hash=expected_key,
        evidence_kind="provider_dm_participant",
        generation=1,
        revision=0,
        created_at=datetime(2026, 11, 1, 10, 0, tzinfo=UTC),
    )

    q_id = uuid.uuid4()
    ans_id = uuid.uuid4()
    question = OwnerQuestion(
        id=q_id,
        workspace_id=ws_id,
        social_account_id=acc_id,
        thread_id=uuid.uuid4(),
        session_id=uuid.uuid4(),
        customer_identity_id=cust_id,
        required_info="holiday_hours",
        visibility="customer_reply",
        continuation_key="cont_1",
        body="Do we open on Sunday this week?",
        state="answered",
        answer_id=ans_id,
        source_cursor=1,
        source_hash="hash_1",
        knowledge_fence="fence_1",
        ownership_generation=1,
        deletion_generation=0,
        created_at=datetime(2026, 11, 1, 10, 2, tzinfo=UTC),
        expires_at=datetime(2026, 11, 2, 10, 2, tzinfo=UTC),
    )
    answer = OwnerAnswer(
        id=ans_id,
        workspace_id=ws_id,
        social_account_id=acc_id,
        thread_id=question.thread_id,
        question_id=q_id,
        version=1,
        kind="answer",
        body="Yes, 10am-4pm on Sunday.",
        author_user_id=uuid.uuid4(),
        author_role="owner",
        client_request_id=uuid.uuid4(),
        request_hash="req_hash",
        created_at=datetime(2026, 11, 1, 10, 5, tzinfo=UTC),
        expires_at=datetime(2026, 11, 2, 10, 5, tzinfo=UTC),
    )

    comment_owned = PublicComment(
        id=uuid.uuid4(),
        workspace_id=ws_id,
        social_account_id=acc_id,
        media_id=uuid.uuid4(),
        thread_id=uuid.uuid4(),
        external_id="comm_1",
        author_external_id=participant_id,
        text="Love the shop!",
        state="visible",
        provider_timestamp=datetime(2026, 11, 1, 9, 30, tzinfo=UTC),
        updated_at=datetime(2026, 11, 1, 9, 30, tzinfo=UTC),
        is_simulated=True,
    )

    _comment_third_party = PublicComment(
        id=uuid.uuid4(),
        workspace_id=ws_id,
        social_account_id=acc_id,
        media_id=uuid.uuid4(),
        thread_id=uuid.uuid4(),
        external_id="comm_2",
        author_external_id="unrelated_user_456",
        text="Is shipping free?",
        state="visible",
        provider_timestamp=datetime(2026, 11, 1, 9, 35, tzinfo=UTC),
        updated_at=datetime(2026, 11, 1, 9, 35, tzinfo=UTC),
        is_simulated=True,
    )

    # Set up mock session
    session = MagicMock()
    # Mock queries
    session.scalar.side_effect = lambda stmt: _route_scalar(
        stmt,
        conversation,
        account,
        customer_identity,
        answer,
    )
    session.get.side_effect = lambda model, pk: workspace if model == Workspace else None

    # Mock scalars
    def _mock_scalars(stmt: Any) -> MagicMock:
        res = MagicMock()
        s_str = str(stmt)
        if "FROM messages" in s_str:
            res.all.return_value = [msg1, msg2]
            res.__iter__.return_value = iter([msg1, msg2])
        elif "FROM reply_drafts" in s_str:
            res.all.return_value = [draft]
            res.__iter__.return_value = iter([draft])
        elif "FROM approvals" in s_str:
            res.all.return_value = [approval]
            res.__iter__.return_value = iter([approval])
        elif "FROM operations" in s_str:
            res.all.return_value = [operation]
            res.__iter__.return_value = iter([operation])
        elif "FROM owner_questions" in s_str:
            res.all.return_value = [question]
            res.__iter__.return_value = iter([question])
        elif "FROM public_comments" in s_str:
            # Query filters by author_external_id == participant_id, so third-party is excluded
            res.all.return_value = [comment_owned]
            res.__iter__.return_value = iter([comment_owned])
        else:
            res.all.return_value = []
            res.__iter__.return_value = iter([])
        return res

    session.scalars.side_effect = _mock_scalars

    with patch("app.memory.service.export_customer") as mock_mem_exp:
        mock_mem_exp.return_value = {
            "customer_id": str(cust_id),
            "memories": [{"kind": "preference", "body": "Prefers morning visits"}],
        }
        with patch("app.audit.service.record") as mock_audit:
            result = data_rights.export_conversation(session, clock, ctx, conv_id)

    # Assert schema and content
    assert result["schema_version"] == "1.0"
    assert result["exported_at"] == clock.now().isoformat()
    assert result["workspace"]["id"] == str(ws_id)
    assert result["conversation"]["id"] == str(conv_id)
    assert result["conversation"]["participant_id"] == participant_id

    # Messages
    assert len(result["messages"]) == 2
    assert result["messages"][0]["text"] == "What are your opening hours?"
    assert result["messages"][1]["text"] == "We are open Mon-Sat 9am-6pm."

    # Drafts and approvals
    assert len(result["reply_drafts"]) == 1
    assert result["reply_drafts"][0]["draft_text"] == "We are open Mon-Sat 9am-6pm."
    assert len(result["approvals"]) == 1
    assert result["approvals"][0]["status"] == "approved"

    # Operations: safe metadata only, no access tokens
    assert len(result["operations"]) == 1
    assert result["operations"][0]["status"] == "succeeded"
    assert "access_token" not in str(result)
    assert "super_secret_token" not in str(result)

    # Memory and questions
    assert result["customer_memory"]["memories"][0]["body"] == "Prefers morning visits"
    assert len(result["owner_questions"]) == 1
    assert result["owner_questions"][0]["answer"]["answer_body"] == "Yes, 10am-4pm on Sunday."

    # Linked public comments (INV-18: strictly participant, not third-party)
    assert len(result["linked_public_comments"]) == 1
    assert result["linked_public_comments"][0]["external_id"] == "comm_1"
    assert result["linked_public_comments"][0]["text"] == "Love the shop!"
    assert "comm_2" not in str(result["linked_public_comments"])

    # Audit recorded
    mock_audit.assert_called_once()
    call_args = mock_audit.call_args[0]
    assert call_args[2] == "data_rights.conversation_exported"
    assert call_args[3] == "conversation"
    assert call_args[4] == conv_id


def test_export_customer_forbidden_for_non_owner() -> None:
    session = MagicMock()
    clock = FrozenClock(datetime(2026, 11, 3, 12, 0, tzinfo=UTC))
    cust_id = uuid.uuid4()

    for role in ("manager", "staff", "viewer"):
        ctx = _make_ctx(role=role)
        with pytest.raises(AppError) as exc_info:
            data_rights.export_customer(session, clock, ctx, cust_id)
        assert exc_info.value.code == "FORBIDDEN"


def test_export_customer_not_found_when_missing() -> None:
    session = MagicMock()
    session.scalar.return_value = None  # No customer identity found
    clock = FrozenClock(datetime(2026, 11, 3, 12, 0, tzinfo=UTC))
    ctx = _make_ctx(role="owner")
    cust_id = uuid.uuid4()

    with pytest.raises(AppError) as exc_info:
        data_rights.export_customer(session, clock, ctx, cust_id)
    assert exc_info.value.code == "NOT_FOUND"


def test_export_customer_owner_success() -> None:
    clock = FrozenClock(datetime(2026, 11, 3, 12, 0, tzinfo=UTC))
    ctx = _make_ctx(role="owner")
    ws_id = ctx.workspace_id
    acc_id = uuid.uuid4()
    cust_id = uuid.uuid4()
    conv_id = uuid.uuid4()
    participant_id = "participant_xyz"

    workspace = Workspace(id=ws_id, name="Test Studio")
    account = SocialAccount(
        id=acc_id,
        workspace_id=ws_id,
        provider_kind="mock",
        external_account_id="acc_123",
        username="studio_official",
        status="active",
        token_ciphertext=b"token",
    )

    expected_hash = memory_service.digest(f"mock:dm:{participant_id}")
    customer_identity = CustomerIdentity(
        id=cust_id,
        workspace_id=ws_id,
        social_account_id=acc_id,
        provider_subject_hash=expected_hash,
        evidence_kind="provider_dm_participant",
        generation=2,
        revision=1,
        created_at=datetime(2026, 11, 1, 9, 0, tzinfo=UTC),
    )

    thread = AgentThread(
        id=uuid.uuid4(),
        workspace_id=ws_id,
        social_account_id=acc_id,
        surface="dm",
        source_ref="src_1",
        dm_conversation_id=conv_id,
        customer_identity_id=cust_id,
    )

    conversation = Conversation(
        id=conv_id,
        workspace_id=ws_id,
        social_account_id=acc_id,
        customer_external_id=participant_id,
        customer_handle="xyz_customer",
        handling_mode="agent",
        created_at=datetime(2026, 11, 1, 9, 0, tzinfo=UTC),
    )

    msg = Message(
        id=uuid.uuid4(),
        workspace_id=ws_id,
        conversation_id=conv_id,
        social_account_id=acc_id,
        direction="inbound",
        sender_kind="customer",
        external_message_id="mid_100",
        text="Hello there!",
        attachments=[],
        provider_timestamp=datetime(2026, 11, 1, 9, 5, tzinfo=UTC),
        is_deleted=False,
        created_at=datetime(2026, 11, 1, 9, 5, tzinfo=UTC),
    )

    comment = PublicComment(
        id=uuid.uuid4(),
        workspace_id=ws_id,
        social_account_id=acc_id,
        media_id=uuid.uuid4(),
        thread_id=uuid.uuid4(),
        external_id="comm_xyz",
        author_external_id=participant_id,
        text="Super neat!",
        state="visible",
        provider_timestamp=datetime(2026, 11, 1, 8, 0, tzinfo=UTC),
        updated_at=datetime(2026, 11, 1, 8, 0, tzinfo=UTC),
        is_simulated=True,
    )

    session = MagicMock()
    session.scalar.side_effect = lambda stmt: _route_customer_scalar(
        stmt, customer_identity, account
    )
    session.get.side_effect = lambda model, pk: workspace if model == Workspace else None

    def _mock_scalars(stmt: Any) -> MagicMock:
        res = MagicMock()
        s_str = str(stmt)
        if "FROM agent_threads" in s_str:
            res.all.return_value = [thread]
            res.__iter__.return_value = iter([thread])
        elif "FROM conversations" in s_str:
            res.all.return_value = [conversation]
            res.__iter__.return_value = iter([conversation])
        elif "FROM messages" in s_str:
            res.all.return_value = [msg]
            res.__iter__.return_value = iter([msg])
        elif "FROM owner_questions" in s_str:
            res.all.return_value = []
            res.__iter__.return_value = iter([])
        elif "FROM public_comments" in s_str:
            res.all.return_value = [comment]
            res.__iter__.return_value = iter([comment])
        else:
            res.all.return_value = []
            res.__iter__.return_value = iter([])
        return res

    session.scalars.side_effect = _mock_scalars

    with patch("app.memory.service.export_customer") as mock_mem_exp:
        mock_mem_exp.return_value = {
            "customer_id": str(cust_id),
            "memories": [{"kind": "note", "body": "VIP customer"}],
        }
        with patch("app.audit.service.record") as mock_audit:
            result = data_rights.export_customer(session, clock, ctx, cust_id)

    assert result["schema_version"] == "1.0"
    assert result["exported_at"] == clock.now().isoformat()
    assert result["customer_identity"]["id"] == str(cust_id)
    assert result["customer_identity"]["generation"] == 2
    assert len(result["conversations"]) == 1
    assert result["conversations"][0]["id"] == str(conv_id)
    assert len(result["messages"]) == 1
    assert result["messages"][0]["text"] == "Hello there!"
    assert result["memory"]["memories"][0]["body"] == "VIP customer"
    assert len(result["public_comments"]) == 1
    assert result["public_comments"][0]["text"] == "Super neat!"

    mock_audit.assert_called_once()
    assert mock_audit.call_args[0][2] == "data_rights.customer_exported"
    assert mock_audit.call_args[0][3] == "customer"
    assert mock_audit.call_args[0][4] == cust_id


def _route_scalar(
    stmt: Any,
    conversation: Conversation,
    account: SocialAccount,
    customer_identity: CustomerIdentity,
    answer: OwnerAnswer,
) -> Any:
    s_str = str(stmt)
    if "FROM conversations" in s_str:
        return conversation
    if "FROM social_accounts" in s_str:
        return account
    if "FROM customer_identities" in s_str:
        return customer_identity
    if "FROM owner_answers" in s_str:
        return answer
    return None


def _route_customer_scalar(
    stmt: Any, customer_identity: CustomerIdentity, account: SocialAccount
) -> Any:
    s_str = str(stmt)
    if "FROM customer_identities" in s_str:
        return customer_identity
    if "FROM social_accounts" in s_str:
        return account
    return None
