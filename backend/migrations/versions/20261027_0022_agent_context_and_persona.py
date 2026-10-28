"""Personality freshness and one-repair grounding budget.

Revision ID: 0022
Revises: 0021
"""

import sqlalchemy as sa
from alembic import op

revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "agent_steps",
        sa.Column(
            "captured_persona_version",
            sa.Integer(),
            nullable=False,
            server_default="1",
        ),
    )
    op.add_column(
        "agent_sessions",
        sa.Column(
            "validation_failures",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )


def downgrade() -> None:
    if op.get_bind().execute(sa.text("SELECT EXISTS (SELECT 1 FROM agent_sessions)")).scalar():
        raise RuntimeError("refusing to discard agent context evidence")
    op.drop_column("agent_sessions", "validation_failures")
    op.drop_column("agent_steps", "captured_persona_version")
