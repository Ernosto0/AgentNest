"""Single customer follow-up per conversation. Revision 0090, parent 0083."""

import sqlalchemy as sa
from alembic import op

revision = "0090"
down_revision = "0083"
branch_labels = None
depends_on = None
TABLE = "conversation_follow_ups"


def upgrade() -> None:
    op.create_table(
        TABLE,
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("answer_draft_id", sa.Uuid(), nullable=False),
        sa.Column("covers_through_message_id", sa.Uuid(), nullable=False),
        sa.Column("answered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("reason_code", sa.Text(), nullable=True),
        sa.Column("reply_draft_id", sa.Uuid(), nullable=True),
        sa.Column("is_simulated", sa.Boolean(), server_default="false", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("drafted_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_conversation_follow_ups")),
        sa.UniqueConstraint(
            "workspace_id", "id", name=op.f("uq_conversation_follow_ups_workspace_id_id")
        ),
        sa.UniqueConstraint(
            "workspace_id",
            "conversation_id",
            name=op.f("uq_conversation_follow_ups_workspace_id_conversation_id"),
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            ondelete="CASCADE",
            name=op.f("fk_conversation_follow_ups_workspace_id_workspaces"),
        ),
        *[
            sa.ForeignKeyConstraint(
                ["workspace_id", column],
                [f"{target}.workspace_id", f"{target}.id"],
                ondelete="CASCADE",
                name=op.f(f"fk_conversation_follow_ups_workspace_id_{column}_{target}"),
            )
            for column, target in (
                ("conversation_id", "conversations"),
                ("answer_draft_id", "reply_drafts"),
                ("covers_through_message_id", "messages"),
                ("reply_draft_id", "reply_drafts"),
            )
        ],
        sa.CheckConstraint(
            "status IN ('scheduled', 'cancelled', 'skipped', 'drafted')",
            name=op.f("ck_conversation_follow_ups_status"),
        ),
        sa.CheckConstraint(
            "(status = 'drafted') = (reply_draft_id IS NOT NULL)",
            name=op.f("ck_conversation_follow_ups_drafted_reply"),
        ),
        sa.CheckConstraint(
            "status NOT IN ('cancelled', 'skipped') OR reason_code IS NOT NULL",
            name=op.f("ck_conversation_follow_ups_reason"),
        ),
        sa.CheckConstraint("due_at >= answered_at", name=op.f("ck_conversation_follow_ups_due_at")),
    )
    op.create_index(op.f("ix_conversation_follow_ups_workspace_id"), TABLE, ["workspace_id"])
    op.create_index(
        "uq_conversation_follow_ups_reply_draft_id",
        TABLE,
        ["reply_draft_id"],
        unique=True,
        postgresql_where=sa.text("reply_draft_id IS NOT NULL"),
    )
    op.execute(sa.text(f"ALTER TABLE {TABLE} ENABLE ROW LEVEL SECURITY"))
    op.execute(sa.text(f"ALTER TABLE {TABLE} FORCE ROW LEVEL SECURITY"))
    op.execute(
        sa.text(f"""CREATE POLICY tenant_isolation_policy ON {TABLE} FOR ALL
        USING (workspace_id = nullif(current_setting('app.workspace_id', true), '')::uuid)
        WITH CHECK (workspace_id = nullif(current_setting('app.workspace_id', true), '')::uuid)""")
    )
    for role in ("agentnest_app", "agentnest_worker", "agentnest_migrator"):
        op.execute(
            sa.text(f"""DO $$ BEGIN
            IF to_regrole('{role}') IS NOT NULL THEN
                GRANT SELECT, INSERT, UPDATE, DELETE ON {TABLE} TO {role};
            END IF;
        END $$;""")
        )


def downgrade() -> None:
    op.drop_table(TABLE)
