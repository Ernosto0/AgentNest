"""Thread ownership fences for agent DM cutover.

Revision ID: 0023
Revises: 0022
"""

import sqlalchemy as sa
from alembic import op

revision = "0023"
down_revision = "0022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table, column in (
        ("account_agents", "cutover_generation"),
        ("agent_threads", "ownership_generation"),
        ("agent_steps", "captured_ownership_generation"),
        ("agent_actions", "ownership_generation"),
    ):
        op.add_column(table, sa.Column(column, sa.BigInteger(), nullable=False, server_default="0"))


def downgrade() -> None:
    if (
        op.get_bind()
        .execute(
            sa.text(
                "SELECT EXISTS (SELECT 1 FROM agent_steps) OR EXISTS (SELECT 1 FROM agent_actions) OR EXISTS (SELECT 1 FROM account_agents WHERE cutover_generation <> 0)"
            )
        )
        .scalar()
    ):
        raise RuntimeError("refusing to discard DM ownership evidence")
    op.drop_column("agent_actions", "ownership_generation")
    op.drop_column("agent_steps", "captured_ownership_generation")
    op.drop_column("agent_threads", "ownership_generation")
    op.drop_column("account_agents", "cutover_generation")
