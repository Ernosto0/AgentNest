"""Story mentions (F-04): a thank-you template and its automation class.

- ``approved_answers.intent`` may now be ``story_mention``: the owner's one thank-you for a story
  mention (a template, never offered to the model).
- ``automation_policies.action_class`` may now be ``reply.story_mention``, so the thank-you is
  approval-required by default and can later be made automatic like any other reply class.

Both are replaced CHECK constraints; no table or row changes.

Revision ID: 0052
Revises: 0050
Create Date: 2026-11-16 12:00:00.000000
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0052"
down_revision: str | None = "0050"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

INTENT_CHECK = "ck_approved_answers_intent"
CLASS_CHECK = "ck_automation_policies_action_class"

INTENTS = (
    "greeting",
    "pricing",
    "hours",
    "location_contact",
    "services",
    "booking",
    "promotions",
    "faq",
)
CLASSES = (
    "reply.hours",
    "reply.location_contact",
    "reply.pricing",
    "reply.services",
    "reply.booking",
    "reply.promotions",
    "reply.general_faq",
    "content.publish",
)


def _in(column: str, values: Sequence[str]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


def _replace(table: str, name: str, column: str, values: Sequence[str]) -> None:
    op.drop_constraint(op.f(name), table, type_="check")
    op.create_check_constraint(op.f(name), table, _in(column, values))


def upgrade() -> None:
    _replace("approved_answers", INTENT_CHECK, "intent", (*INTENTS, "story_mention"))
    _replace(
        "automation_policies", CLASS_CHECK, "action_class", (*CLASSES, "reply.story_mention")
    )


def downgrade() -> None:
    op.execute("DELETE FROM approved_answers WHERE intent = 'story_mention'")
    op.execute("DELETE FROM automation_policies WHERE action_class = 'reply.story_mention'")
    _replace("approved_answers", INTENT_CHECK, "intent", INTENTS)
    _replace("automation_policies", CLASS_CHECK, "action_class", CLASSES)
