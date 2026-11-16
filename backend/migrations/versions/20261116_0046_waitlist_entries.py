"""Add the pilot waitlist table for the public landing form.

Revision ID: 0046
Revises: 0045
Create Date: 2026-11-16 12:00:00.000000

P-06: ``POST /api/v1/waitlist`` stores one row per normalized email. The table is global (no
workspace), holds personal data and is cleaned by the retention job.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0046"
down_revision: str | None = "0045"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "waitlist_entries",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.Text(), nullable=False),
        sa.Column("email_normalized", sa.Text(), nullable=False),
        sa.Column("business_name", sa.Text(), nullable=True),
        sa.Column("category", sa.Text(), nullable=True),
        sa.Column("instagram_handle", sa.Text(), nullable=True),
        sa.Column("city", sa.Text(), nullable=True),
        sa.Column("locale", sa.Text(), server_default="tr", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_waitlist_entries")),
        sa.UniqueConstraint("email_normalized", name=op.f("uq_waitlist_entries_email_normalized")),
        sa.CheckConstraint("locale IN ('tr', 'en')", name=op.f("ck_waitlist_entries_locale")),
    )

    op.execute(
        sa.text(
            """
            DO $$
            BEGIN
                IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'agentnest_app') THEN
                    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE waitlist_entries TO agentnest_app;
                END IF;
                IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'agentnest_worker') THEN
                    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE waitlist_entries TO agentnest_worker;
                END IF;
            END
            $$;
            """
        )
    )


def downgrade() -> None:
    op.drop_table("waitlist_entries")
