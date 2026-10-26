"""Versioned delegation request identity and agent approval subjects.

Revision ID: 0020
Revises: 0019
"""

import sqlalchemy as sa
from alembic import op

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("agent_delegations", sa.Column("client_request_id", sa.Uuid(), nullable=True))
    op.add_column("agent_actions", sa.Column("authorized_at", sa.DateTime(timezone=True)))
    op.create_index(
        "ix_agent_actions_daily_authority", "agent_actions",
        ["workspace_id", "social_account_id", "action_type", "authorized_at"],
    )
    op.create_unique_constraint(
        op.f("uq_agent_delegations_workspace_id_social_account_id_client_request_id"),
        "agent_delegations", ["workspace_id", "social_account_id", "client_request_id"],
    )
    op.drop_constraint(op.f("ck_approvals_action"), "approvals", type_="check")
    op.create_check_constraint(
        op.f("ck_approvals_action"), "approvals",
        "action IN ('command.update_fact', 'command.update_brand_voice', "
        "'command.cancel_content', 'reply.send', 'content.publish', 'comments.approve', "
        "'content.prepare', 'content.schedule', 'content.cancel')",
    )
    op.drop_constraint(op.f("ck_approvals_subject_type"), "approvals", type_="check")
    op.create_check_constraint(
        op.f("ck_approvals_subject_type"), "approvals",
        "subject_type IN ('owner_command', 'reply_draft', 'content_item', 'agent_action')",
    )


def downgrade() -> None:
    connection = op.get_bind()
    if connection.execute(sa.text(
        "SELECT EXISTS (SELECT 1 FROM approvals WHERE subject_type = 'agent_action' "
        "OR action IN ('comments.approve', 'content.prepare', 'content.schedule', "
        "'content.cancel')) OR EXISTS (SELECT 1 FROM agent_delegations "
        "WHERE client_request_id IS NOT NULL) OR EXISTS (SELECT 1 FROM agent_actions "
        "WHERE authorized_at IS NOT NULL)"
    )).scalar():
        raise RuntimeError("refusing to discard agent authorization evidence")
    op.drop_constraint(op.f("ck_approvals_subject_type"), "approvals", type_="check")
    op.create_check_constraint(
        op.f("ck_approvals_subject_type"), "approvals",
        "subject_type IN ('owner_command', 'reply_draft', 'content_item')",
    )
    op.drop_constraint(op.f("ck_approvals_action"), "approvals", type_="check")
    op.create_check_constraint(
        op.f("ck_approvals_action"), "approvals",
        "action IN ('command.update_fact', 'command.update_brand_voice', "
        "'command.cancel_content', 'reply.send', 'content.publish')",
    )
    op.drop_constraint(
        op.f("uq_agent_delegations_workspace_id_social_account_id_client_request_id"),
        "agent_delegations", type_="unique",
    )
    op.drop_column("agent_delegations", "client_request_id")
    op.drop_index("ix_agent_actions_daily_authority", table_name="agent_actions")
    op.drop_column("agent_actions", "authorized_at")
