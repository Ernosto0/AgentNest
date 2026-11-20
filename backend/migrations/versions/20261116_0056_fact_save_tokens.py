"""Single-use Telegram tokens for "save this answer as a verified fact" (D-05).

- ``fact_save_tokens``: one row per offered button. Only the SHA-256 of the token is stored. A token
  is bound to one fact candidate and one user, expires and is used at most once. Forced RLS on
  ``app.workspace_id``.
- ``resolve_fact_save_token_by_hash``: SECURITY DEFINER lookup used by the Telegram callback, which
  does not know the workspace yet (same pattern as ``resolve_action_token_by_hash``).

Revision ID: 0056
Revises: 0055
Create Date: 2026-11-16 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0056"
down_revision: str | None = "0055"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "fact_save_tokens"


def upgrade() -> None:
    op.create_table(
        TABLE,
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.Text(), nullable=False),
        sa.Column("candidate_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_fact_save_tokens")),
        sa.UniqueConstraint("workspace_id", "id", name=op.f("uq_fact_save_tokens_workspace_id_id")),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name=op.f("fk_fact_save_tokens_workspace_id_workspaces"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "candidate_id"],
            ["fact_candidates.workspace_id", "fact_candidates.id"],
            name=op.f("fk_fact_save_tokens_workspace_id_fact_candidates"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_fact_save_tokens_user_id_users"),
            ondelete="CASCADE",
        ),
    )
    op.create_index(op.f("ix_fact_save_tokens_token_hash"), TABLE, ["token_hash"], unique=True)
    op.create_index(op.f("ix_fact_save_tokens_workspace_id"), TABLE, ["workspace_id"])
    op.create_index("ix_fact_save_tokens_candidate", TABLE, ["workspace_id", "candidate_id"])
    op.create_index("ix_fact_save_tokens_expires_at", TABLE, ["expires_at"])

    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    schema = bind.execute(sa.text("SELECT current_schema()")).scalar_one() or "public"
    q_schema = '"' + str(schema).replace('"', '""') + '"'
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
    op.execute(
        sa.text(
            f"""
            CREATE OR REPLACE FUNCTION resolve_fact_save_token_by_hash(p_token_hash text)
            RETURNS TABLE (id uuid, workspace_id uuid)
            LANGUAGE sql
            SECURITY DEFINER
            SET search_path = {q_schema}, pg_temp
            STABLE
            AS $$
                SELECT t.id, t.workspace_id
                FROM fact_save_tokens t
                WHERE t.token_hash = p_token_hash
                LIMIT 1;
            $$;
            """
        )
    )
    op.execute(sa.text("GRANT EXECUTE ON FUNCTION resolve_fact_save_token_by_hash(text) TO PUBLIC"))
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
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(sa.text("DROP FUNCTION IF EXISTS resolve_fact_save_token_by_hash(text)"))
    op.drop_table(TABLE)
