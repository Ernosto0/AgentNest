"""WhatsApp window anchor and delivery metadata. Revision 0071, parent 0070."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0071"
down_revision = "0070"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "channel_links", sa.Column("last_inbound_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "notification_deliveries",
        sa.Column(
            "delivery_metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
    )
    op.create_index(
        "ix_notification_deliveries_wamid",
        "notification_deliveries",
        ["workspace_id", sa.text("(delivery_metadata->>'wamid')")],
    )


def downgrade() -> None:
    op.drop_index("ix_notification_deliveries_wamid", table_name="notification_deliveries")
    op.drop_column("notification_deliveries", "delivery_metadata")
    op.drop_column("channel_links", "last_inbound_at")
