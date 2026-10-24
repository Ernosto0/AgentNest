"""General business categories (ADR-023): gym and pilates_studio merge into fitness.

Revision ID: 0018
Revises: 0017
"""

from alembic import op

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None

NEW = (
    "beauty_wellness",
    "food_beverage",
    "retail",
    "fitness",
    "health_clinic",
    "education",
    "hospitality",
    "services",
    "other",
)
OLD = ("gym", "pilates_studio", "other")


def _in(values: tuple[str, ...]) -> str:
    return f"business_category IN ({', '.join(repr(v) for v in values)})"


def upgrade() -> None:
    op.drop_constraint(op.f("ck_workspaces_business_category"), "workspaces", type_="check")
    op.execute(
        "UPDATE workspaces SET business_category = 'fitness'"
        " WHERE business_category IN ('gym', 'pilates_studio')"
    )
    op.create_check_constraint(op.f("ck_workspaces_business_category"), "workspaces", _in(NEW))


def downgrade() -> None:
    # Lossy: fitness cannot be split back; it returns as gym, everything else as other.
    op.drop_constraint(op.f("ck_workspaces_business_category"), "workspaces", type_="check")
    op.execute(
        "UPDATE workspaces SET business_category = CASE"
        " WHEN business_category = 'fitness' THEN 'gym' ELSE 'other' END"
        " WHERE business_category <> 'other'"
    )
    op.create_check_constraint(op.f("ck_workspaces_business_category"), "workspaces", _in(OLD))
