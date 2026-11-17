"""Workspace plans and idempotent reply allowance ledger.

Revision ID: 0050
Revises: 0049
"""

import sqlalchemy as sa
from alembic import op

revision = "0050"
down_revision = "0049"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "workspace_plans",
        sa.Column(
            "workspace_id",
            sa.Uuid(),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("plan", sa.Text(), nullable=False),
        sa.Column("monthly_quota", sa.Integer(), nullable=False),
        sa.Column("quota_override", sa.Integer()),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("anchor_day", sa.Integer(), nullable=False),
        sa.Column("period_id", sa.Uuid(), nullable=False),
        sa.Column("used", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("warned_80", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("warned_100", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("warned_paused", sa.Boolean(), nullable=False, server_default="false"),
        sa.CheckConstraint(
            "monthly_quota > 0 AND (quota_override IS NULL OR quota_override > 0)",
            name="positive_quota",
        ),
        sa.CheckConstraint("used >= 0", name="used"),
        sa.CheckConstraint("period_end > period_start", name="period"),
        sa.CheckConstraint("status IN ('trial', 'active', 'past_due', 'cancelled')", name="status"),
        sa.CheckConstraint("plan IN ('starter', 'growth', 'pro')", name="plan"),
    )
    op.create_table(
        "reply_usage",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "workspace_id",
            sa.Uuid(),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("draft_key", sa.Text(), nullable=False),
        sa.Column("period_id", sa.Uuid(), nullable=False),
        sa.Column("state", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("workspace_id", "draft_key"),
        sa.UniqueConstraint("workspace_id", "id"),
    )
    op.create_index("ix_reply_usage_workspace_id", "reply_usage", ["workspace_id"])
    # Historical migration snapshot, not the runtime tier catalog. Existing workspaces start today.
    op.execute(
        sa.text("""INSERT INTO workspace_plans
        (workspace_id, plan, monthly_quota, status, period_start, period_end, anchor_day, period_id)
        SELECT id, 'growth', 2500, 'trial', now(), now() + interval '1 month',
        extract(day from now())::integer, gen_random_uuid() FROM workspaces""")
    )
    for table in ("workspace_plans", "reply_usage"):
        op.execute(sa.text(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY"))
        op.execute(sa.text(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY"))
        op.execute(
            sa.text(f"""CREATE POLICY tenant_isolation_policy ON {table} FOR ALL
            USING (workspace_id = nullif(current_setting('app.workspace_id', true), '')::uuid)
            WITH CHECK (workspace_id = nullif(current_setting('app.workspace_id', true), '')::uuid)""")
        )
        for role in ("agentnest_app", "agentnest_worker", "agentnest_migrator"):
            op.execute(
                sa.text(f"""DO $$ BEGIN IF to_regrole('{role}') IS NOT NULL THEN
                GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO {role};
                END IF; END $$;""")
            )


def downgrade() -> None:
    op.drop_table("reply_usage")
    op.drop_table("workspace_plans")
