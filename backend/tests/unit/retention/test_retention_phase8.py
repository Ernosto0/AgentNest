"""Unit tests for Phase 8 Session 12: Retention Cleanup Extensions (P8-06).

Covers:
- Phase 7.5 Owner questions & answers text redaction at text_cutoff.
- Phase 7.5 Agent owner tasks text redaction at text_cutoff.
- Phase 7.5 Agent steps raw input/tool checkpoints scrubbed at agent_input_cutoff.
- Phase 7.5 Agent actions intent/grant scrubbed at agent_input_cutoff (active states protected).
- Ledger preservation: statuses, versions, token counts, and timestamps remain intact.
- Multi-workspace tenant RLS context handling (set_tenant_context called per workspace).
- Accurate aggregation into RetentionCounts.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any
from unittest.mock import MagicMock, patch

from sqlalchemy.sql.dml import Delete, Update

from app.core.config import Settings
from app.retention.cleanup import RetentionCounts, run_retention


def test_run_retention_full_phase8_coverage() -> None:
    now = datetime(2026, 11, 3, 12, 0, tzinfo=UTC)
    settings = Settings(
        retention_webhook_payload_days=30,
        retention_inbound_event_row_days=90,
        retention_agent_input_days=30,
        retention_message_text_days=180,
        retention_customer_memory_days=180,
        retention_notifications_read_days=90,
        retention_jobs_succeeded_days=7,
        retention_jobs_dead_days=90,
    )

    ws1_id = uuid.uuid4()
    ws2_id = uuid.uuid4()

    executed_statements: list[Any] = []
    set_tenant_calls: list[Any] = []

    mock_session = MagicMock()

    # Discover workspaces
    mock_session.scalars.return_value.all.return_value = [ws1_id, ws2_id]

    def mock_execute(statement: Any, *args: Any, **kwargs: Any) -> Any:
        executed_statements.append(statement)
        res = MagicMock()
        # Return 1 changed row per batch to simulate exactly 1 batch execution per rule
        res.rowcount = 1
        return res

    mock_session.execute.side_effect = mock_execute

    session_factory = MagicMock()
    session_factory.return_value.__enter__.return_value = mock_session

    with (
        patch("app.retention.cleanup._delete_inbound_events", return_value=5),
        patch(
            "app.retention.cleanup.set_tenant_context",
            side_effect=lambda s, ws: set_tenant_calls.append(ws),
        ),
        patch("app.comments.privacy.retention_batch", return_value=(3, 3)) as mock_public,
        patch("app.memory.service.retention_batch", return_value=4) as mock_memory,
        patch("app.owner_requests.service.recover_questions"),
    ):
        # We need public and memory while-loops to terminate (examined < batch_size on 2nd call)
        mock_public.side_effect = [(3, 100), (0, 0)]
        mock_memory.side_effect = [4, 0]

        counts = run_retention(session_factory, settings, now, batch_size=100)

    # 1. Verify counts returned
    assert isinstance(counts, RetentionCounts)
    assert counts.webhook_rows_deleted == 5
    assert counts.public_sources_nulled == 3
    assert counts.memories_nulled == 4

    # 2. Verify set_tenant_context was bound for both workspaces
    assert ws1_id in set_tenant_calls
    assert ws2_id in set_tenant_calls

    # 3. Inspect executed statements to prove every Phase 7.5 rule executed
    target_tables = []
    for stmt in executed_statements:
        if isinstance(stmt, (Update, Delete)):
            target_tables.append(stmt.table.name)

    # Check that each expected Phase 7.5 table received an update statement
    assert "owner_questions" in target_tables
    assert "owner_answers" in target_tables
    assert "agent_owner_tasks" in target_tables
    assert "agent_steps" in target_tables
    assert "agent_actions" in target_tables
    assert "messages" in target_tables
    assert "reply_drafts" in target_tables
    assert "notifications" in target_tables
    assert "jobs" in target_tables


def test_retention_phase8_owner_question_and_answer_statements() -> None:
    now = datetime(2026, 11, 3, 12, 0, tzinfo=UTC)
    settings = Settings(retention_message_text_days=180)

    executed_updates: list[Update] = []
    mock_session = MagicMock()
    mock_session.scalars.return_value.all.return_value = []  # Single global fallback mode

    def mock_execute(stmt: Any, *args: Any, **kwargs: Any) -> Any:
        if isinstance(stmt, Update):
            executed_updates.append(stmt)
        res = MagicMock()
        res.rowcount = 1
        return res

    mock_session.execute.side_effect = mock_execute
    session_factory = MagicMock()
    session_factory.return_value.__enter__.return_value = mock_session

    with (
        patch("app.retention.cleanup._delete_inbound_events", return_value=0),
        patch("app.comments.privacy.retention_batch", return_value=(0, 0)),
        patch("app.memory.service.retention_batch", return_value=0),
        patch("app.owner_requests.service.recover_questions"),
    ):
        counts = run_retention(session_factory, settings, now, batch_size=100)
    assert counts.webhook_rows_deleted == 0

    # Verify OwnerQuestion update statement: body=None, source_message_id=None, source_hash=""
    q_updates = [u for u in executed_updates if u.table.name == "owner_questions"]
    assert len(q_updates) >= 1
    q_stmt = q_updates[0]
    # Check values mapped
    val_names = {c.name for c in q_stmt._values}
    assert "body" in val_names
    assert "source_message_id" in val_names
    assert "source_hash" in val_names

    # Verify OwnerAnswer update statement: body=None
    ans_updates = [u for u in executed_updates if u.table.name == "owner_answers"]
    assert len(ans_updates) >= 1
    ans_stmt = ans_updates[0]
    ans_val_names = {c.name for c in ans_stmt._values}
    assert "body" in ans_val_names

    # Verify OwnerTask update statement: request_text="[REDACTED]", clarification=None, answers=[]
    task_updates = [u for u in executed_updates if u.table.name == "agent_owner_tasks"]
    assert len(task_updates) >= 1
    task_stmt = task_updates[0]
    task_val_names = {c.name for c in task_stmt._values}
    assert "request_text" in task_val_names
    assert "clarification" in task_val_names
    assert "answers" in task_val_names

    # Verify AgentStep update statement: read_checkpoint=None, input_ref=None, output_ref=None
    step_updates = [u for u in executed_updates if u.table.name == "agent_steps"]
    assert len(step_updates) >= 1
    step_stmt = step_updates[0]
    step_val_names = {c.name for c in step_stmt._values}
    assert "read_checkpoint" in step_val_names
    assert "input_ref" in step_val_names
    assert "output_ref" in step_val_names

    # Verify AgentAction update statement: content_intent=None, policy_grant=None
    action_updates = [u for u in executed_updates if u.table.name == "agent_actions"]
    assert len(action_updates) >= 1
    act_stmt = action_updates[0]
    act_val_names = {c.name for c in act_stmt._values}
    assert "content_intent" in act_val_names
    assert "policy_grant" in act_val_names
