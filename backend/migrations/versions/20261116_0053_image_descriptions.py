"""Photos and screenshots: ``message_image_descriptions`` and the ``describe_image`` task (F-03).

One row per image attachment (the first few of a message), created ``pending`` when the message is
stored and finished by the ``describe_message_image`` job (``succeeded`` with a short description,
the text visible in the picture and a kind, or ``failed`` with a reason code). The description and
the visible text are a machine's reading of customer content: untrusted, erased by the same paths
as message text. Composite FK to ``messages`` (cascade), forced RLS on ``app.workspace_id``.

Also lets ``agent_runs.task`` hold ``describe_image``.

Revision ID: 0053
Revises: 0052
Create Date: 2026-11-16 18:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0053"
down_revision: str | None = "0052"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "message_image_descriptions"

_TASKS_BEFORE = (
    "'interpret_command', 'draft_reply', 'draft_content', "
    "'extract_fact_candidates', 'account_agent_step', 'narrate_command_result'"
)


def upgrade() -> None:
    op.drop_constraint(op.f("ck_agent_runs_task"), "agent_runs", type_="check")
    op.create_check_constraint(
        op.f("ck_agent_runs_task"),
        "agent_runs",
        f"task IN ({_TASKS_BEFORE}, 'describe_image')",
    )

    op.create_table(
        TABLE,
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("message_id", sa.Uuid(), nullable=False),
        sa.Column("attachment_index", sa.Integer(), server_default="0", nullable=False),
        sa.Column("status", sa.Text(), server_default="pending", nullable=False),
        sa.Column("reason_code", sa.Text(), nullable=True),
        sa.Column("source", sa.Text(), server_default="image_description", nullable=False),
        sa.Column("looks_like", sa.Text(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("visible_text", sa.Text(), nullable=True),
        sa.Column("injection_suspected", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("provider", sa.Text(), nullable=True),
        sa.Column("model", sa.Text(), nullable=True),
        sa.Column("media_type", sa.Text(), nullable=True),
        sa.Column("image_bytes", sa.Integer(), nullable=True),
        sa.Column("agent_run_id", sa.Uuid(), nullable=True),
        sa.Column("is_simulated", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("erased_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'succeeded', 'failed')",
            name=op.f("ck_message_image_descriptions_status"),
        ),
        sa.CheckConstraint(
            "source = 'image_description'", name=op.f("ck_message_image_descriptions_source")
        ),
        sa.CheckConstraint(
            "attachment_index >= 0", name=op.f("ck_message_image_descriptions_attachment_index")
        ),
        sa.CheckConstraint(
            "(status = 'failed') = (reason_code IS NOT NULL)",
            name=op.f("ck_message_image_descriptions_reason_code"),
        ),
        sa.CheckConstraint(
            "looks_like IS NULL OR looks_like IN "
            "('product', 'price_screenshot', 'location', 'other')",
            name=op.f("ck_message_image_descriptions_looks_like"),
        ),
        sa.CheckConstraint(
            "status <> 'succeeded' OR (provider IS NOT NULL AND model IS NOT NULL)",
            name=op.f("ck_message_image_descriptions_succeeded_has_provider"),
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "message_id"],
            ["messages.workspace_id", "messages.id"],
            name=op.f("fk_message_image_descriptions_workspace_id_messages"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name=op.f("fk_message_image_descriptions_workspace_id_workspaces"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_message_image_descriptions")),
        sa.UniqueConstraint(
            "workspace_id", "id", name=op.f("uq_message_image_descriptions_workspace_id_id")
        ),
        sa.UniqueConstraint(
            "workspace_id",
            "message_id",
            "attachment_index",
            name="uq_message_image_descriptions_message_attachment",
        ),
    )
    op.create_index(op.f("ix_message_image_descriptions_workspace_id"), TABLE, ["workspace_id"])
    op.create_index("ix_message_image_descriptions_status", TABLE, ["status"])
    op.create_index(
        "ix_message_image_descriptions_workspace_created", TABLE, ["workspace_id", "created_at"]
    )

    op.execute(sa.text(f"ALTER TABLE {TABLE} ENABLE ROW LEVEL SECURITY"))
    op.execute(sa.text(f"ALTER TABLE {TABLE} FORCE ROW LEVEL SECURITY"))
    op.execute(
        sa.text(
            f"""
            CREATE POLICY tenant_isolation_policy ON {TABLE} FOR ALL
            USING (workspace_id = nullif(current_setting('app.workspace_id', true), '')::uuid)
            WITH CHECK (workspace_id = nullif(current_setting('app.workspace_id', true), '')::uuid)
            """
        )
    )
    for role in ("pivoris_app", "pivoris_worker", "pivoris_migrator"):
        op.execute(
            sa.text(
                f"""
                DO $$ BEGIN
                    IF to_regrole('{role}') IS NOT NULL THEN
                        GRANT SELECT, INSERT, UPDATE, DELETE ON {TABLE} TO {role};
                    END IF;
                END $$;
                """
            )
        )


def downgrade() -> None:
    op.drop_table(TABLE)
    op.execute(sa.text("DELETE FROM agent_runs WHERE task = 'describe_image'"))
    op.drop_constraint(op.f("ck_agent_runs_task"), "agent_runs", type_="check")
    op.create_check_constraint(
        op.f("ck_agent_runs_task"),
        "agent_runs",
        f"task IN ({_TASKS_BEFORE})",
    )
