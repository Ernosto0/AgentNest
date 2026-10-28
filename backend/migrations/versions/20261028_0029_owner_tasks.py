"""Durable account-scoped owner tasks."""

import sqlalchemy as sa
from alembic import op

revision = "0029"
down_revision = "0028"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agent_owner_tasks",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("workspace_id", sa.UUID(), nullable=False),
        sa.Column("social_account_id", sa.UUID(), nullable=False),
        sa.Column("thread_id", sa.UUID(), nullable=False),
        sa.Column("requester_user_id", sa.UUID(), nullable=False),
        sa.Column("requester_role", sa.Text(), nullable=False),
        sa.Column("source_channel", sa.Text(), nullable=False),
        sa.Column("client_request_id", sa.UUID(), nullable=False),
        sa.Column("request_text", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("workspace_id", "id"),
        sa.UniqueConstraint("workspace_id", "social_account_id", "id"),
        sa.UniqueConstraint(
            "workspace_id", "social_account_id", "requester_user_id", "client_request_id"
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "social_account_id"],
            ["account_agents.workspace_id", "account_agents.social_account_id"],
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "social_account_id", "thread_id"],
            ["agent_threads.workspace_id", "agent_threads.social_account_id", "agent_threads.id"],
        ),
        sa.ForeignKeyConstraint(["requester_user_id"], ["users.id"]),
        sa.CheckConstraint("source_channel IN ('api')", name="ck_agent_owner_tasks_source_channel"),
        sa.CheckConstraint(
            "length(request_text) BETWEEN 1 AND 4000",
            name="ck_agent_owner_tasks_request_text_length",
        ),
    )


def downgrade() -> None:
    if op.get_bind().scalar(sa.text("SELECT EXISTS(SELECT 1 FROM agent_owner_tasks)")):
        raise RuntimeError("0029 downgrade requires owner task archival")
    op.drop_table("agent_owner_tasks")
