"""Add login throttling and session IP address for auth hardening.

Revision ID: 0033
Revises: 0032
Create Date: 2026-11-01 21:40:00.000000

P8-04 / ADR-025 §2:
- Adds ip_address to sessions table.
- Creates login_throttles table for per-IP and per-email throttling with exponential backoff.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0033"
down_revision: str | None = "0032"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Add ip_address column to sessions table
    op.add_column("sessions", sa.Column("ip_address", sa.Text(), nullable=True))

    # 2. Create login_throttles table
    op.create_table(
        "login_throttles",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("identifier_type", sa.Text(), nullable=False),
        sa.Column("identifier_hash", sa.Text(), nullable=False),
        sa.Column("failed_attempts", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("first_failed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_failed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_login_throttles")),
        sa.CheckConstraint(
            "identifier_type IN ('email', 'ip')",
            name=op.f("ck_login_throttles_identifier_type"),
        ),
        sa.UniqueConstraint(
            "identifier_type", "identifier_hash", name=op.f("uq_login_throttles_identifier_type_identifier_hash")
        ),
    )
    op.create_index(
        op.f("ix_login_throttles_locked_until"),
        "login_throttles",
        ["locked_until"],
        unique=False,
    )

    # 3. Grant runtime privileges if roles exist
    op.execute(
        sa.text(
            """
            DO $$
            BEGIN
                IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'agentnest_app') THEN
                    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.login_throttles TO agentnest_app;
                END IF;
                IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'agentnest_worker') THEN
                    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.login_throttles TO agentnest_worker;
                END IF;
            END
            $$;
            """
        )
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_login_throttles_locked_until"), table_name="login_throttles")
    op.drop_table("login_throttles")
    op.drop_column("sessions", "ip_address")
