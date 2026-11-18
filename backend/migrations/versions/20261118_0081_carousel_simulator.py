"""Carousel simulator. Revision 0081, parent 0080."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0081"
down_revision = "0080"
branch_labels = None
depends_on = None

# Snapshot the prior operation constraint; migrations must not import mutable app models.
OLD_OPERATIONS = (
    "send",
    "lookup",
    "echo",
    "create_container",
    "container_status",
    "publish",
    "refresh",
    "profile",
    "comment_reply",
    "comment_hide",
    "comment_unhide",
    "comment_delete",
    "comment_lookup",
    "comment_private_reply",
    "private_reply_lookup",
    "any",
)


def _checks(carousel: bool) -> None:
    op.drop_constraint(op.f("ck_sim_containers_media_type"), "sim_containers", type_="check")
    types = "'IMAGE', 'STORIES', 'CAROUSEL'" if carousel else "'IMAGE', 'STORIES'"
    op.create_check_constraint(
        op.f("ck_sim_containers_media_type"), "sim_containers", f"media_type IN ({types})"
    )
    op.drop_constraint(op.f("ck_sim_failure_rules_operation"), "sim_failure_rules", type_="check")
    operations = OLD_OPERATIONS + (
        ("create_carousel_item", "create_carousel_container") if carousel else ()
    )
    values = ", ".join(repr(v) for v in operations)
    op.create_check_constraint(
        op.f("ck_sim_failure_rules_operation"), "sim_failure_rules", f"operation IN ({values})"
    )


def upgrade() -> None:
    _checks(True)
    op.add_column(
        "sim_containers",
        sa.Column("is_carousel_item", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column("sim_containers", sa.Column("children", postgresql.JSONB(), nullable=True))
    op.alter_column("sim_containers", "media_url", nullable=True)
    op.add_column(
        "sim_failure_rules",
        sa.Column("skip_first", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_check_constraint(
        op.f("ck_sim_failure_rules_skip_first"), "sim_failure_rules", "skip_first >= 0"
    )


def downgrade() -> None:
    op.execute("DELETE FROM sim_containers WHERE media_type = 'CAROUSEL' OR is_carousel_item")
    op.execute(
        "DELETE FROM sim_failure_rules WHERE operation IN ('create_carousel_item', 'create_carousel_container')"
    )
    _checks(False)
    op.drop_constraint(op.f("ck_sim_failure_rules_skip_first"), "sim_failure_rules", type_="check")
    op.drop_column("sim_failure_rules", "skip_first")
    op.alter_column("sim_containers", "media_url", nullable=False)
    op.drop_column("sim_containers", "children")
    op.drop_column("sim_containers", "is_carousel_item")
