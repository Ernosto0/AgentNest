"""WhatsApp owner channel: link channel, delivery channel, webhook dedup. Revision 0070, parent 0061."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0070"
down_revision = "0061"
branch_labels = None
depends_on = None

# Names and allowed values verified against a database migrated through 0061.
CHECKS = (
    ("channel_links", "ck_channel_links_channel", "channel", "'telegram'"),
    ("channel_link_codes", "ck_channel_link_codes_channel", "channel", "'telegram'"),
    (
        "notification_deliveries",
        "ck_notification_deliveries_channel",
        "channel",
        "'web', 'telegram', 'web_push'",
    ),
    (
        "approvals",
        "ck_approvals_decision_channel",
        "decision_channel",
        "'web', 'telegram', 'policy'",
    ),
    ("owner_commands", "ck_owner_commands_channel", "channel", "'web', 'telegram'"),
    (
        "agent_owner_tasks",
        "ck_agent_owner_tasks_ck_agent_owner_tasks_source_channel",
        "source_channel",
        "'api', 'telegram'",
    ),
)


def _checks(whatsapp: bool) -> None:
    for table, name, column, allowed in CHECKS:
        op.drop_constraint(op.f(name), table, type_="check")
        values = allowed + ", 'whatsapp'" if whatsapp else allowed
        expression = f"{column} IN ({values})"
        if column == "decision_channel":
            expression = f"{column} IS NULL OR {expression}"
        op.create_check_constraint(op.f(name), table, expression)


def upgrade() -> None:
    _checks(True)
    op.create_table(
        "whatsapp_webhook_events",
        sa.Column("message_id", sa.Text(), primary_key=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("wa_id_hash", sa.Text(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "status IN ('processed', 'ignored', 'failed')",
            name=op.f("ck_whatsapp_webhook_events_status"),
        ),
    )
    op.create_index(
        "ix_whatsapp_webhook_events_received_at", "whatsapp_webhook_events", ["received_at"]
    )
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        schema = bind.execute(sa.text("SELECT current_schema()")).scalar_one() or "public"
        q_schema = '"' + str(schema).replace('"', '""') + '"'
        for role in ("agentnest_app", "agentnest_worker"):
            op.execute(
                sa.text(f"""
                DO $$ BEGIN
                    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{role}') THEN
                        GRANT USAGE ON SCHEMA {q_schema} TO {role};
                        GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE whatsapp_webhook_events TO {role};
                    END IF;
                END $$;
            """)
            )


def downgrade() -> None:
    op.drop_table("whatsapp_webhook_events")
    # As in 0048, rows of the removed channel cannot satisfy the old constraint. Only link,
    # link-code and delivery rows can exist after this migration alone; approvals, commands and
    # owner tasks are never deleted here, so a downgrade fails loudly if one carries `whatsapp`.
    for table, _, column, _ in CHECKS[:3]:
        op.execute(sa.text(f"DELETE FROM {table} WHERE {column} = 'whatsapp'"))
    _checks(False)
