"""Human Agent message tag on reply drafts. Revision 0091, parent 0090."""

import sqlalchemy as sa
from alembic import op

revision = "0091"
down_revision = "0090"
branch_labels = None
depends_on = None

CHECK = "ck_reply_drafts_message_tag_human_only"


def _active_schema_sql() -> str:
    bind = op.get_bind()
    schema = bind.execute(sa.text("SELECT current_schema()")).scalar_one() or "public"
    return '"' + str(schema).replace('"', '""') + '"'


def _expired_drafts_function(*, tagged_wait: bool) -> None:
    """The expiry sweep's discovery. A tagged draft waits for the 7-day window: its conversation
    must be 6 days older than the 24-hour cutoff before it is retired."""
    q_schema = _active_schema_sql()
    extra = (
        "AND (rd.message_tag IS NULL OR c.last_inbound_at <= p_cutoff - interval '6 days')"
        if tagged_wait
        else ""
    )
    op.execute(
        sa.text(
            f"""
            CREATE OR REPLACE FUNCTION discover_expired_reply_draft_ids(
                p_cutoff timestamptz,
                p_limit int DEFAULT 100
            )
            RETURNS TABLE (
                id uuid,
                workspace_id uuid
            )
            LANGUAGE sql
            SECURITY DEFINER
            SET search_path = {q_schema}, pg_temp
            STABLE
            AS $$
                SELECT rd.id, rd.workspace_id
                FROM reply_drafts rd
                JOIN conversations c
                  ON c.workspace_id = rd.workspace_id
                 AND c.id = rd.conversation_id
                WHERE rd.status IN ('pending_approval', 'needs_human', 'queued')
                  AND c.last_inbound_at <= p_cutoff
                  {extra}
                ORDER BY rd.created_at, rd.id
                LIMIT p_limit;
            $$;
            """
        )
    )


def upgrade() -> None:
    op.add_column("reply_drafts", sa.Column("message_tag", sa.Text(), nullable=True))
    op.create_check_constraint(
        op.f(CHECK),
        "reply_drafts",
        "message_tag IS NULL OR (message_tag = 'HUMAN_AGENT' AND source = 'owner' "
        "AND origin = 'legacy' AND created_by_actor_type = 'user')",
    )
    op.add_column("sim_sent_messages", sa.Column("message_tag", sa.Text(), nullable=True))
    _expired_drafts_function(tagged_wait=True)


def downgrade() -> None:
    # A tagged draft cannot be represented without the column: refuse to drop live evidence.
    bind = op.get_bind()
    if bind.execute(
        sa.text("SELECT EXISTS (SELECT 1 FROM reply_drafts WHERE message_tag IS NOT NULL)")
    ).scalar_one():
        raise RuntimeError("reply drafts with a message tag exist; remove them before downgrading")
    _expired_drafts_function(tagged_wait=False)
    op.drop_column("sim_sent_messages", "message_tag")
    op.drop_constraint(op.f(CHECK), "reply_drafts", type_="check")
    op.drop_column("reply_drafts", "message_tag")
