"""Add narrate_command_result to agent_runs task check constraint.

Revision ID: 0043
Revises: 0042
Create Date: 2026-11-09 00:00:00.000000
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0043"
down_revision: str | None = "0042"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(op.f("ck_agent_runs_task"), "agent_runs", type_="check")
    op.create_check_constraint(
        op.f("ck_agent_runs_task"),
        "agent_runs",
        "task IN ('interpret_command', 'draft_reply', 'draft_content', "
        "'extract_fact_candidates', 'account_agent_step', 'narrate_command_result')",
    )


def downgrade() -> None:
    op.drop_constraint(op.f("ck_agent_runs_task"), "agent_runs", type_="check")
    op.create_check_constraint(
        op.f("ck_agent_runs_task"),
        "agent_runs",
        "task IN ('interpret_command', 'draft_reply', 'draft_content', "
        "'extract_fact_candidates', 'account_agent_step')",
    )
