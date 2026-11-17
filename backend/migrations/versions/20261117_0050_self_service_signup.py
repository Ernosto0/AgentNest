"""Self-service signup: email verification and versioned terms acceptance on users.

Revision ID: 0050
Revises: 0049
Create Date: 2026-11-17 09:00:00.000000

P-10: ``email_verified`` defaults to true, so every existing user (CLI, seed, invite) stays
verified and nobody is locked out; only ``POST /auth/register`` creates unverified users. The
verification token is stored as a hash, like password reset and invite tokens. No consent is
invented for existing users: ``accepted_terms_version`` and ``terms_accepted_at`` stay NULL.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0050"
down_revision: str | None = "0049"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TOKEN_UNIQUE = "uq_users_verification_token_hash"


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("email_verified", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.add_column("users", sa.Column("email_verified_at", sa.DateTime(timezone=True)))
    op.add_column("users", sa.Column("accepted_terms_version", sa.Text()))
    op.add_column("users", sa.Column("terms_accepted_at", sa.DateTime(timezone=True)))
    op.add_column("users", sa.Column("verification_token_hash", sa.LargeBinary()))
    op.add_column("users", sa.Column("verification_expires_at", sa.DateTime(timezone=True)))
    op.create_unique_constraint(_TOKEN_UNIQUE, "users", ["verification_token_hash"])
    op.execute("UPDATE users SET email_verified_at = created_at")


def downgrade() -> None:
    op.drop_constraint(_TOKEN_UNIQUE, "users", type_="unique")
    for column in (
        "verification_expires_at",
        "verification_token_hash",
        "terms_accepted_at",
        "accepted_terms_version",
        "email_verified_at",
        "email_verified",
    ):
        op.drop_column("users", column)
