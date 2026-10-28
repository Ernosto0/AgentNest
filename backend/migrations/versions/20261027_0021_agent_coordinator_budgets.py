"""Durable coordinator activation reservations.

Revision ID: 0021
Revises: 0020
"""

import sqlalchemy as sa
from alembic import op

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    from sqlalchemy.dialects.postgresql import JSONB

    op.add_column("agent_steps", sa.Column("read_checkpoint", JSONB()))
    for name in ("activation_cursor", "activation_steps", "activation_tools", "reserved_tokens"):
        op.add_column(
            "agent_sessions", sa.Column(name, sa.BigInteger(), nullable=False, server_default="0")
        )
    op.add_column("agent_sessions", sa.Column("activation_started_at", sa.DateTime(timezone=True)))
    op.add_column("agent_sessions", sa.Column("outcome_code", sa.Text()))


def downgrade() -> None:
    if op.get_bind().execute(sa.text("SELECT EXISTS (SELECT 1 FROM agent_sessions)")).scalar():
        raise RuntimeError("refusing to discard coordinator budget evidence")
    op.drop_column("agent_steps", "read_checkpoint")
    for name in (
        "outcome_code",
        "activation_started_at",
        "reserved_tokens",
        "activation_tools",
        "activation_steps",
        "activation_cursor",
    ):
        op.drop_column("agent_sessions", name)
