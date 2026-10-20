"""phase 5 mock capabilities (data fix)

The code used the capability name ``content_publish`` while the documents name
``publish_feed_image`` and ``publish_story_image`` (plan G4, integrations.md §3.2). Existing
mock accounts get the documented names, keeping the value they had; nothing else changes.

Revision ID: 0011
Revises: 0010
Create Date: 2026-10-20 12:40:00.000000
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Exposed as constants so a test can run exactly the statements the migration runs.
UPGRADE_SQL = """
UPDATE social_accounts
SET capabilities = (capabilities - 'content_publish') || jsonb_build_object(
    'publish_feed_image',
    COALESCE(capabilities -> 'publish_feed_image', capabilities -> 'content_publish', 'true'::jsonb),
    'publish_story_image',
    COALESCE(capabilities -> 'publish_story_image', capabilities -> 'content_publish', 'true'::jsonb)
)
WHERE provider_kind = 'mock'
"""

DOWNGRADE_SQL = """
UPDATE social_accounts
SET capabilities = (capabilities - 'publish_feed_image' - 'publish_story_image') || jsonb_build_object(
    'content_publish',
    COALESCE(capabilities -> 'publish_feed_image', 'true'::jsonb)
)
WHERE provider_kind = 'mock'
"""


def upgrade() -> None:
    op.execute(UPGRADE_SQL)


def downgrade() -> None:
    op.execute(DOWNGRADE_SQL)
