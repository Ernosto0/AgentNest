"""Persist scoped enquiry evidence on the original customer message. Revision 0102."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0102"
down_revision: str | None = "0101"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("messages", sa.Column("agent_enquiry_intent", sa.Text(), nullable=True))
    op.create_check_constraint(
        op.f("ck_messages_agent_enquiry_intent"),
        "messages",
        "agent_enquiry_intent IS NULL OR agent_enquiry_intent IN ('pricing', 'booking')",
    )


def downgrade() -> None:
    op.drop_constraint(op.f("ck_messages_agent_enquiry_intent"), "messages", type_="check")
    op.drop_column("messages", "agent_enquiry_intent")
