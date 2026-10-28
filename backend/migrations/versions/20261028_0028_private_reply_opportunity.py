"""One-shot mock private reply reservation and provider evidence."""

import sqlalchemy as sa
from alembic import op

revision = "0028"
down_revision = "0027"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "private_reply_opportunities",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("workspace_id", sa.UUID(), nullable=False),
        sa.Column("social_account_id", sa.UUID(), nullable=False),
        sa.Column("comment_id", sa.UUID(), nullable=False),
        sa.Column("agent_action_id", sa.UUID(), nullable=False),
        sa.Column("comment_version", sa.BigInteger(), nullable=False),
        sa.Column("media_version", sa.BigInteger(), nullable=False),
        sa.Column("text", sa.Text()),
        sa.Column("proposal", sa.dialects.postgresql.JSONB()),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("eligibility_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("provider_reply_id", sa.Text()),
        sa.Column("provider_recipient_id", sa.Text()),
        sa.Column("bound_conversation_id", sa.UUID()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("workspace_id", "id"),
        sa.UniqueConstraint("workspace_id", "social_account_id", "id"),
        sa.UniqueConstraint("social_account_id", "comment_id"),
        sa.UniqueConstraint("agent_action_id"),
        sa.ForeignKeyConstraint(["workspace_id", "social_account_id"], ["social_accounts.workspace_id", "social_accounts.id"]),
        sa.ForeignKeyConstraint(["workspace_id", "social_account_id", "comment_id"], ["public_comments.workspace_id", "public_comments.social_account_id", "public_comments.id"]),
        sa.ForeignKeyConstraint(["workspace_id", "social_account_id", "agent_action_id"], ["agent_actions.workspace_id", "agent_actions.social_account_id", "agent_actions.id"]),
        sa.ForeignKeyConstraint(["workspace_id", "social_account_id", "bound_conversation_id"], ["conversations.workspace_id", "conversations.social_account_id", "conversations.id"]),
        sa.CheckConstraint("status IN ('reserved','succeeded','outcome_unknown','failed','cancelled')", name="ck_private_reply_opportunities_status"),
    )
    op.create_table(
        "sim_private_replies",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("workspace_id", sa.UUID(), nullable=False),
        sa.Column("social_account_id", sa.UUID(), nullable=False),
        sa.Column("comment_external_id", sa.Text(), nullable=False),
        sa.Column("operation_key", sa.Text(), nullable=False),
        sa.Column("provider_reply_id", sa.Text(), nullable=False),
        sa.Column("recipient_external_id", sa.Text()),
        sa.Column("text", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("workspace_id", "id"),
        sa.UniqueConstraint("workspace_id", "social_account_id", "id"),
        sa.UniqueConstraint("social_account_id", "comment_external_id"),
        sa.UniqueConstraint("social_account_id", "operation_key"),
        sa.ForeignKeyConstraint(["workspace_id", "social_account_id"], ["social_accounts.workspace_id", "social_accounts.id"]),
    )
    op.drop_constraint(op.f("ck_operations_operation_type"), "operations", type_="check")
    op.create_check_constraint("operation_type", "operations", "operation_type IN ('send_reply','publish_content','refresh_token','comment_reply','comment_hide','comment_unhide','comment_delete','comment_private_reply')")
    op.drop_constraint(op.f("ck_sim_failure_rules_operation"), "sim_failure_rules", type_="check")
    op.create_check_constraint("operation", "sim_failure_rules", "operation IN ('send','lookup','echo','create_container','container_status','publish','refresh','profile','comment_reply','comment_hide','comment_unhide','comment_delete','comment_lookup','comment_private_reply','private_reply_lookup','any')")


def downgrade() -> None:
    if op.get_bind().scalar(sa.text("SELECT EXISTS(SELECT 1 FROM private_reply_opportunities) OR EXISTS(SELECT 1 FROM sim_private_replies)")):
        raise RuntimeError("0028 downgrade requires private-reply evidence archival")
    op.drop_constraint(op.f("ck_sim_failure_rules_operation"), "sim_failure_rules", type_="check")
    op.create_check_constraint("operation", "sim_failure_rules", "operation IN ('send','lookup','echo','create_container','container_status','publish','refresh','profile','comment_reply','comment_hide','comment_unhide','comment_delete','comment_lookup','any')")
    op.drop_constraint(op.f("ck_operations_operation_type"), "operations", type_="check")
    op.create_check_constraint("operation_type", "operations", "operation_type IN ('send_reply','publish_content','refresh_token','comment_reply','comment_hide','comment_unhide','comment_delete')")
    op.drop_table("sim_private_replies")
    op.drop_table("private_reply_opportunities")
