"""Durable content proposals, scoped read references and owner clarifications."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0030"
down_revision = "0029"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("agent_actions", sa.Column("content_intent", JSONB(), nullable=True))
    op.add_column(
        "agent_owner_tasks", sa.Column("read_refs", JSONB(), nullable=False, server_default="{}")
    )
    op.add_column("agent_owner_tasks", sa.Column("clarification", sa.Text(), nullable=True))
    op.add_column(
        "agent_owner_tasks", sa.Column("answers", JSONB(), nullable=False, server_default="[]")
    )


def downgrade() -> None:
    if op.get_bind().scalar(
        sa.text("SELECT EXISTS(SELECT 1 FROM agent_actions WHERE content_intent IS NOT NULL)")
    ):
        raise RuntimeError("0030 downgrade requires content intent archival")
    if op.get_bind().scalar(
        sa.text(
            "SELECT EXISTS(SELECT 1 FROM agent_owner_tasks "
            "WHERE clarification IS NOT NULL "
            "OR answers <> '[]'::jsonb OR read_refs <> '{}'::jsonb)"
        )
    ):
        raise RuntimeError("0030 downgrade requires owner continuation archival")
    for column in ("answers", "clarification", "read_refs"):
        op.drop_column("agent_owner_tasks", column)
    op.drop_column("agent_actions", "content_intent")
