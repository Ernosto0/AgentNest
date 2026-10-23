"""Allow separately deduplicated message-unsend webhook events.

Revision ID: 0016
Revises: 0015
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0016"
down_revision: str | None = "0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OLD_TYPES = "'message', 'echo', 'reaction', 'read', 'postback', 'other'"


def _replace(types: str) -> None:
    op.drop_constraint(op.f("ck_inbound_events_event_type"), "inbound_events", type_="check")
    op.create_check_constraint(
        op.f("ck_inbound_events_event_type"), "inbound_events", f"event_type IN ({types})"
    )


def upgrade() -> None:
    _replace(OLD_TYPES + ", 'delete'")


def downgrade() -> None:
    if op.get_bind().scalar(
        sa.text("SELECT EXISTS (SELECT 1 FROM inbound_events WHERE event_type = 'delete')")
    ):
        raise RuntimeError("Cannot downgrade: message deletion webhook events must be preserved.")
    _replace(OLD_TYPES)
