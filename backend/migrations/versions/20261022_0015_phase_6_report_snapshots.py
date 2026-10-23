"""Immutable report generations and retention-safe membership.

Revision ID: 0015
Revises: 0014
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("uq_daily_reports_workspace_id_local_date", "daily_reports", type_="unique")
    op.add_column(
        "daily_reports", sa.Column("revision", sa.Integer(), nullable=False, server_default="1")
    )
    # Existing aggregates cannot honestly be backfilled from today's mutable state.
    op.add_column(
        "daily_reports",
        sa.Column("evidence_complete", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_unique_constraint(
        "uq_daily_reports_workspace_id_local_date_revision",
        "daily_reports",
        ["workspace_id", "local_date", "revision"],
    )
    op.create_table(
        "report_items",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("report_id", sa.Uuid(), nullable=False),
        sa.Column("metric_key", sa.Text(), nullable=False),
        sa.Column("subject_type", sa.Text(), nullable=False),
        sa.Column("subject_id", sa.Uuid(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True)),
        sa.Column("is_simulated", sa.Boolean(), nullable=False),
        sa.Column("link_id", sa.Uuid(), nullable=False),
        sa.Column("measure", sa.Numeric()),
        sa.Column("group_key", sa.Text()),
        sa.PrimaryKeyConstraint("id", name="pk_report_items"),
        sa.UniqueConstraint("workspace_id", "id", name="uq_report_items_workspace_id_id"),
        sa.UniqueConstraint(
            "workspace_id",
            "report_id",
            "metric_key",
            "subject_type",
            "subject_id",
            name="uq_report_items_membership",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name="fk_report_items_workspace_id_workspaces",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "report_id"],
            ["daily_reports.workspace_id", "daily_reports.id"],
            name="fk_report_items_workspace_id_report_id_daily_reports",
            ondelete="CASCADE",
        ),
    )
    op.create_index("ix_report_items_workspace_id", "report_items", ["workspace_id"])
    op.create_table(
        "report_source_gaps",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("metric_key", sa.Text(), nullable=False),
        sa.Column("start_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_report_source_gaps"),
        sa.UniqueConstraint("workspace_id", "id", name="uq_report_source_gaps_workspace_id_id"),
        sa.UniqueConstraint(
            "workspace_id", "metric_key", "start_at", "end_at", name="uq_report_source_gap_period"
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name="fk_report_source_gaps_workspace_id_workspaces",
            ondelete="CASCADE",
        ),
    )
    op.create_index("ix_report_source_gaps_workspace_id", "report_source_gaps", ["workspace_id"])
    # Old cleanup audits are system-wide counts: they cannot identify the lost tenant/day.
    # Conservatively mark pre-cleanup history unknown for then-existing workspaces.
    op.execute("""
        INSERT INTO report_source_gaps (id, workspace_id, metric_key, start_at, end_at)
        SELECT w.id, w.id, 'integration_errors', '0001-01-01T00:00:00Z'::timestamptz, a.last_cleanup
        FROM workspaces w CROSS JOIN (
            SELECT max(occurred_at) AS last_cleanup FROM audit_logs
            WHERE action = 'retention.cleanup_ran'
              AND (metadata->>'webhook_rows_deleted')::bigint > 0
        ) a WHERE a.last_cleanup IS NOT NULL AND w.created_at <= a.last_cleanup
    """)


def downgrade() -> None:
    # Never silently discard historical generations to restore the old unique key.
    if (
        op.get_bind()
        .execute(
            sa.text(
                "SELECT 1 FROM daily_reports GROUP BY workspace_id, local_date "
                "HAVING count(*) > 1 LIMIT 1"
            )
        )
        .first()
    ):
        raise RuntimeError("Cannot downgrade 0015 while multiple report generations exist")
    op.drop_table("report_source_gaps")
    op.drop_table("report_items")
    op.drop_constraint(
        "uq_daily_reports_workspace_id_local_date_revision", "daily_reports", type_="unique"
    )
    op.drop_column("daily_reports", "evidence_complete")
    op.drop_column("daily_reports", "revision")
    op.create_unique_constraint(
        "uq_daily_reports_workspace_id_local_date", "daily_reports", ["workspace_id", "local_date"]
    )
