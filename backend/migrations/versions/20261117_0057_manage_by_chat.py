"""Confirmed management command actions. Revision 0057, parent 0056."""

from alembic import op

revision = "0057"
down_revision = "0056"
branch_labels = None
depends_on = None

OLD = (
    "command.update_fact",
    "command.update_brand_voice",
    "command.cancel_content",
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
NEW = (*OLD, "command.reschedule_content", "command.pause_agent")


def constraint(actions: tuple[str, ...]) -> None:
    op.drop_constraint(op.f("ck_approvals_action"), "approvals", type_="check")
    op.create_check_constraint(op.f("ck_approvals_action"), "approvals", f"action IN {actions!r}")


def upgrade() -> None:
    constraint(NEW)


def downgrade() -> None:
    # Preserve approval history: refuses downgrade while new actions exist.
    constraint(OLD)
