"""Opt-in real comment automation. Revision 0059, parent 0058."""

import sqlalchemy as sa
from alembic import op

revision = "0059"
down_revision = "0058"
branch_labels = None
depends_on = None

OLD = ("UNKNOWN_ACCOUNT", "ACCOUNT_DISCONNECTED", "UNSUPPORTED_EVENT", "PUBLIC_SOURCE_CONFLICT")


def constraint(reasons: tuple[str, ...]) -> None:
    op.drop_constraint(op.f("ck_inbound_events_ignore_reason"), "inbound_events", type_="check")
    op.create_check_constraint(
        op.f("ck_inbound_events_ignore_reason"),
        "inbound_events",
        f"ignore_reason IS NULL OR ignore_reason IN {reasons!r}",
    )


def upgrade() -> None:
    op.add_column(
        "social_accounts",
        sa.Column(
            "comment_automation_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    constraint((*OLD, "COMMENT_AUTOMATION_OFF"))


def downgrade() -> None:
    # Refuse to remove an ignore reason still present in historical evidence.
    constraint(OLD)
    op.drop_column("social_accounts", "comment_automation_enabled")
