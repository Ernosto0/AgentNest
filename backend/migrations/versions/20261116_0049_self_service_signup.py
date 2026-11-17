"""Self-service signup, verification and versioned legal acceptance.

Revision ID: 0049
Revises: 0048
"""

import sqlalchemy as sa
from alembic import op

revision = "0049"
down_revision = "0048"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Existing accounts and trusted CLI/seed provisioning must never be locked out.
    op.add_column("users", sa.Column("email_verified", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column("users", sa.Column("email_verified_at", sa.DateTime(timezone=True)))
    op.add_column("users", sa.Column("accepted_terms_version", sa.Text()))
    op.add_column("users", sa.Column("terms_accepted_at", sa.DateTime(timezone=True)))
    op.add_column("users", sa.Column("verification_token_hash", sa.LargeBinary()))
    op.add_column("users", sa.Column("verification_expires_at", sa.DateTime(timezone=True)))
    op.create_unique_constraint("uq_users_verification_token_hash", "users", ["verification_token_hash"])
    op.execute("UPDATE users SET email_verified_at = created_at")


def downgrade() -> None:
    op.drop_constraint("uq_users_verification_token_hash", "users", type_="unique")
    for column in ("verification_expires_at", "verification_token_hash", "terms_accepted_at", "accepted_terms_version", "email_verified_at", "email_verified"):
        op.drop_column("users", column)
