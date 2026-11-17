"""Confirmed price-card command action. Revision 0060, parent 0059."""

from alembic import op

revision = "0060"
down_revision = "0059"
branch_labels = None
depends_on = None

OLD = (
    "command.update_fact",
    "command.update_brand_voice",
    "command.cancel_content",
    "command.reschedule_content",
    "command.pause_agent",
    "reply.send",
    "content.publish",
    "comments.approve",
    "content.prepare",
    "content.schedule",
    "content.cancel",
    "calendar.book",
    "calendar.reschedule",
    "calendar.cancel",
)
NEW = (*OLD, "command.make_price_card")


def constraint(actions: tuple[str, ...]) -> None:
    op.drop_constraint(op.f("ck_approvals_action"), "approvals", type_="check")
    op.create_check_constraint(op.f("ck_approvals_action"), "approvals", f"action IN {actions!r}")


def upgrade() -> None:
    constraint(NEW)


def downgrade() -> None:
    # Preserve approval history: refuses downgrade while new actions exist.
    constraint(OLD)
