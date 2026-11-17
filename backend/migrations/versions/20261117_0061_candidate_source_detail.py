"""Candidate import provenance. Revision 0061, parent 0060."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0061"
down_revision = "0060"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("fact_candidates", sa.Column("source_detail", postgresql.JSONB(), nullable=True))
    op.create_check_constraint(
        op.f("ck_fact_candidates_source_detail"),
        "fact_candidates",
        "source_detail IS NULL OR jsonb_typeof(source_detail) = 'object'",
    )


def downgrade() -> None:
    op.drop_constraint(op.f("ck_fact_candidates_source_detail"), "fact_candidates", type_="check")
    op.drop_column("fact_candidates", "source_detail")
