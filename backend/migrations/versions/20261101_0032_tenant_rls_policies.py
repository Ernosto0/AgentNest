"""Add PostgreSQL Row-Level Security (RLS) policies on all Category C tenant tables.

Revision ID: 0032
Revises: 0031
Create Date: 2026-11-01 21:20:00.000000

P8-03 / ADR-025 §1.3:
Enforces FORCE ROW LEVEL SECURITY and tenant_isolation_policy on all 49 strictly
workspace-scoped Category C tables.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0032"
down_revision: str | None = "0031"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CATEGORY_C_TABLES: tuple[str, ...] = (
    "account_agents",
    "agent_actions",
    "agent_delegations",
    "agent_events",
    "agent_owner_tasks",
    "agent_runs",
    "agent_sessions",
    "agent_steps",
    "agent_threads",
    "approvals",
    "approved_answers",
    "automation_policies",
    "business_facts",
    "content_items",
    "conversations",
    "customer_identities",
    "customer_memories",
    "customer_memory_sources",
    "customer_memory_versions",
    "customer_source_fences",
    "customer_summary_versions",
    "daily_reports",
    "fact_candidates",
    "fact_references",
    "fact_versions",
    "media_assets",
    "messages",
    "notifications",
    "operations",
    "owner_answers",
    "owner_commands",
    "owner_questions",
    "private_reply_opportunities",
    "public_comment_actions",
    "public_comments",
    "public_media",
    "public_threads",
    "reply_drafts",
    "report_items",
    "report_source_gaps",
    "sim_comment_effects",
    "sim_containers",
    "sim_failure_rules",
    "sim_inbound_messages",
    "sim_private_replies",
    "sim_public_comments",
    "sim_published_media",
    "sim_sent_messages",
    "social_accounts",
)


def upgrade() -> None:
    for tbl in CATEGORY_C_TABLES:
        op.execute(sa.text(f"ALTER TABLE public.{tbl} ENABLE ROW LEVEL SECURITY"))
        op.execute(sa.text(f"ALTER TABLE public.{tbl} FORCE ROW LEVEL SECURITY"))
        op.execute(
            sa.text(
                f"""
                CREATE POLICY tenant_isolation_policy ON public.{tbl}
                    FOR ALL
                    USING (workspace_id = nullif(current_setting('app.workspace_id', true), '')::uuid)
                    WITH CHECK (workspace_id = nullif(current_setting('app.workspace_id', true), '')::uuid)
                """
            )
        )


def downgrade() -> None:
    for tbl in CATEGORY_C_TABLES:
        op.execute(sa.text(f"DROP POLICY IF EXISTS tenant_isolation_policy ON public.{tbl}"))
        op.execute(sa.text(f"ALTER TABLE public.{tbl} NO FORCE ROW LEVEL SECURITY"))
        op.execute(sa.text(f"ALTER TABLE public.{tbl} DISABLE ROW LEVEL SECURITY"))
