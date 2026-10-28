"""Version-bound public replies and moderation ledger subjects."""

import sqlalchemy as sa
from alembic import op

revision = "0027"
down_revision = "0026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "public_comment_actions",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("workspace_id", sa.UUID(), nullable=False),
        sa.Column("social_account_id", sa.UUID(), nullable=False),
        sa.Column("comment_id", sa.UUID(), nullable=False),
        sa.Column("agent_action_id", sa.UUID(), nullable=False),
        sa.Column("effect", sa.Text(), nullable=False),
        sa.Column("text", sa.Text()),
        sa.Column("proposal", sa.dialects.postgresql.JSONB()),
        sa.Column("comment_version", sa.BigInteger(), nullable=False),
        sa.Column("media_version", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("workspace_id", "id"),
        sa.UniqueConstraint("workspace_id", "social_account_id", "id"),
        sa.UniqueConstraint("agent_action_id"),
        sa.ForeignKeyConstraint(
            ["workspace_id", "social_account_id"],
            ["social_accounts.workspace_id", "social_accounts.id"],
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "social_account_id", "comment_id"],
            [
                "public_comments.workspace_id",
                "public_comments.social_account_id",
                "public_comments.id",
            ],
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "social_account_id", "agent_action_id"],
            ["agent_actions.workspace_id", "agent_actions.social_account_id", "agent_actions.id"],
        ),
        sa.CheckConstraint(
            "effect IN ('reply','hide','unhide','delete')", name="ck_public_comment_actions_effect"
        ),
    )
    op.create_table(
        "sim_comment_effects",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("workspace_id", sa.UUID(), nullable=False),
        sa.Column("social_account_id", sa.UUID(), nullable=False),
        sa.Column("operation_key", sa.Text(), nullable=False),
        sa.Column("target_external_id", sa.Text(), nullable=False),
        sa.Column("effect", sa.Text(), nullable=False),
        sa.Column("provider_id", sa.Text(), nullable=False),
        sa.Column("text", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("workspace_id", "id"),
        sa.UniqueConstraint("workspace_id", "social_account_id", "id"),
        sa.UniqueConstraint("social_account_id", "operation_key"),
        sa.ForeignKeyConstraint(
            ["workspace_id", "social_account_id"],
            ["social_accounts.workspace_id", "social_accounts.id"],
        ),
    )
    op.drop_constraint(op.f("ck_operations_operation_type"), "operations", type_="check")
    op.create_check_constraint(
        "operation_type",
        "operations",
        "operation_type IN ('send_reply','publish_content','refresh_token',"
        "'comment_reply','comment_hide','comment_unhide','comment_delete')",
    )
    op.drop_constraint(op.f("ck_sim_failure_rules_operation"), "sim_failure_rules", type_="check")
    op.create_check_constraint(
        "operation",
        "sim_failure_rules",
        "operation IN ('send','lookup','echo','create_container','container_status',"
        "'publish','refresh','profile','comment_reply','comment_hide','comment_unhide',"
        "'comment_delete','comment_lookup','any')",
    )


def downgrade() -> None:
    if op.get_bind().scalar(
        sa.text(
            "SELECT EXISTS(SELECT 1 FROM public_comment_actions) "
            "OR EXISTS(SELECT 1 FROM sim_comment_effects)"
        )
    ):
        raise RuntimeError("0027 downgrade requires explicit public-effect archival")
    op.drop_constraint(op.f("ck_sim_failure_rules_operation"), "sim_failure_rules", type_="check")
    op.create_check_constraint(
        "operation",
        "sim_failure_rules",
        "operation IN ('send','lookup','echo','create_container','container_status',"
        "'publish','refresh','profile','any')",
    )
    op.drop_constraint(op.f("ck_operations_operation_type"), "operations", type_="check")
    op.create_check_constraint(
        "operation_type",
        "operations",
        "operation_type IN ('send_reply','publish_content','refresh_token')",
    )
    op.drop_table("sim_comment_effects")
    op.drop_table("public_comment_actions")
