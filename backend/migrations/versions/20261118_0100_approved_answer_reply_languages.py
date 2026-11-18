"""Approved answers in the new reply languages. Revision 0100, parent 0091.

Downgrade fails loudly via the restored constraint if new-language rows exist.
"""

from alembic import op

revision = "0100"
down_revision = "0091"
branch_labels = None
depends_on = None


def _replace(expression: str) -> None:
    op.drop_constraint(op.f("ck_approved_answers_language"), "approved_answers", type_="check")
    op.create_check_constraint(op.f("ck_approved_answers_language"), "approved_answers", expression)


def upgrade() -> None:
    _replace("language IN ('tr', 'en', 'ru', 'de', 'ar')")


def downgrade() -> None:
    _replace("language IN ('tr', 'en')")
