"""phase 7.5 agent core records

Revision ID: 0019
Revises: 0018
Create Date: 2026-10-26 12:33:24.372130
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = '0019'
down_revision: str | None = '0018'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # The DM thread FK needs this account-scoped target before agent_threads is created.
    op.create_unique_constraint(
        op.f('uq_conversations_workspace_id_social_account_id_id'),
        'conversations', ['workspace_id', 'social_account_id', 'id'],
    )
    op.create_unique_constraint(
        op.f('uq_operations_workspace_id_social_account_id_id'),
        'operations', ['workspace_id', 'social_account_id', 'id'],
    )
    op.create_table('account_agents',
    sa.Column('social_account_id', sa.Uuid(), nullable=False),
    sa.Column('controller_mode', sa.Text(), server_default='legacy', nullable=False),
    sa.Column('state', sa.Text(), server_default='inactive', nullable=False),
    sa.Column('controller_epoch', sa.BigInteger(), server_default='0', nullable=False),
    sa.Column('config_version', sa.Integer(), server_default='1', nullable=False),
    sa.Column('persona_version', sa.Integer(), server_default='1', nullable=False),
    sa.Column('goals', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
    sa.Column('persona', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('workspace_id', sa.Uuid(), nullable=False),
    sa.CheckConstraint("controller_mode IN ('legacy', 'agent')", name=op.f('ck_account_agents_controller_mode')),
    sa.CheckConstraint("state IN ('inactive', 'active', 'paused')", name=op.f('ck_account_agents_state')),
    sa.CheckConstraint('config_version >= 1 AND persona_version >= 1', name=op.f('ck_account_agents_versions')),
    sa.CheckConstraint('controller_epoch >= 0', name=op.f('ck_account_agents_controller_epoch')),
    sa.ForeignKeyConstraint(['workspace_id', 'social_account_id'], ['social_accounts.workspace_id', 'social_accounts.id'], name=op.f('fk_account_agents_workspace_id_social_account_id_social_accounts'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], name=op.f('fk_account_agents_workspace_id_workspaces'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_account_agents')),
    sa.UniqueConstraint('workspace_id', 'id', name=op.f('uq_account_agents_workspace_id_id')),
    sa.UniqueConstraint('workspace_id', 'social_account_id', name=op.f('uq_account_agents_workspace_id_social_account_id'))
    )
    op.create_index(op.f('ix_account_agents_workspace_id'), 'account_agents', ['workspace_id'], unique=False)
    op.create_table('agent_delegations',
    sa.Column('social_account_id', sa.Uuid(), nullable=False),
    sa.Column('version', sa.Integer(), nullable=False),
    sa.Column('grantor_user_id', sa.Uuid(), nullable=False),
    sa.Column('policy', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('policy_hash', sa.Text(), nullable=False),
    sa.Column('effective_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('workspace_id', sa.Uuid(), nullable=False),
    sa.CheckConstraint("policy_hash ~ '^[0-9a-f]{64}$'", name=op.f('ck_agent_delegations_policy_hash')),
    sa.CheckConstraint('version >= 1', name=op.f('ck_agent_delegations_version')),
    sa.ForeignKeyConstraint(['grantor_user_id'], ['users.id'], name=op.f('fk_agent_delegations_grantor_user_id_users')),
    sa.ForeignKeyConstraint(['workspace_id', 'social_account_id'], ['account_agents.workspace_id', 'account_agents.social_account_id'], name=op.f('fk_agent_delegations_workspace_id_social_account_id_account_agents'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], name=op.f('fk_agent_delegations_workspace_id_workspaces'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_agent_delegations')),
    sa.UniqueConstraint('workspace_id', 'id', name=op.f('uq_agent_delegations_workspace_id_id')),
    sa.UniqueConstraint('workspace_id', 'social_account_id', 'version', name=op.f('uq_agent_delegations_workspace_id_social_account_id_version'))
    )
    op.create_index(op.f('ix_agent_delegations_workspace_id'), 'agent_delegations', ['workspace_id'], unique=False)
    op.create_index('uq_agent_delegations_current', 'agent_delegations', ['workspace_id', 'social_account_id'], unique=True, postgresql_where=sa.text('revoked_at IS NULL'))
    op.create_table('agent_threads',
    sa.Column('social_account_id', sa.Uuid(), nullable=False),
    sa.Column('surface', sa.Text(), nullable=False),
    sa.Column('source_ref', sa.Text(), nullable=False),
    sa.Column('dm_conversation_id', sa.Uuid(), nullable=True),
    sa.Column('customer_identity_id', sa.Uuid(), nullable=True),
    sa.Column('state', sa.Text(), server_default='queued', nullable=False),
    sa.Column('handling_mode', sa.Text(), server_default='agent', nullable=False),
    sa.Column('thread_version', sa.BigInteger(), server_default='1', nullable=False),
    sa.Column('event_cursor', sa.BigInteger(), server_default='0', nullable=False),
    sa.Column('controller_epoch', sa.BigInteger(), server_default='0', nullable=False),
    sa.Column('deletion_generation', sa.BigInteger(), server_default='0', nullable=False),
    sa.Column('current_goal_key', sa.Text(), nullable=True),
    sa.Column('last_activity_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('workspace_id', sa.Uuid(), nullable=False),
    sa.CheckConstraint("handling_mode IN ('agent', 'human')", name=op.f('ck_agent_threads_handling_mode')),
    sa.CheckConstraint("state IN ('queued', 'running', 'waiting_customer', 'waiting_owner', 'waiting_approval', 'waiting_operation', 'sleeping', 'completed', 'cancelled', 'failed')", name=op.f('ck_agent_threads_state')),
    sa.CheckConstraint("surface IN ('dm', 'comment', 'owner_task')", name=op.f('ck_agent_threads_surface')),
    sa.CheckConstraint('thread_version >= 1 AND event_cursor >= 0 AND controller_epoch >= 0 AND deletion_generation >= 0', name=op.f('ck_agent_threads_versions')),
    sa.ForeignKeyConstraint(['workspace_id', 'social_account_id', 'dm_conversation_id'], ['conversations.workspace_id', 'conversations.social_account_id', 'conversations.id'], name=op.f('fk_agent_threads_workspace_id_social_account_id_dm_conversation_id_conversations')),
    sa.ForeignKeyConstraint(['workspace_id', 'social_account_id'], ['account_agents.workspace_id', 'account_agents.social_account_id'], name=op.f('fk_agent_threads_workspace_id_social_account_id_account_agents'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], name=op.f('fk_agent_threads_workspace_id_workspaces'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_agent_threads')),
    sa.UniqueConstraint('workspace_id', 'id', name=op.f('uq_agent_threads_workspace_id_id')),
    sa.UniqueConstraint('workspace_id', 'social_account_id', 'id', name=op.f('uq_agent_threads_workspace_id_social_account_id_id')),
    sa.UniqueConstraint('workspace_id', 'social_account_id', 'surface', 'source_ref', name=op.f('uq_agent_threads_workspace_id_social_account_id_surface_source_ref'))
    )
    op.create_index('ix_agent_threads_account_state_activity', 'agent_threads', ['workspace_id', 'social_account_id', 'state', 'last_activity_at'], unique=False)
    op.create_index(op.f('ix_agent_threads_workspace_id'), 'agent_threads', ['workspace_id'], unique=False)
    op.create_table('agent_events',
    sa.Column('social_account_id', sa.Uuid(), nullable=False),
    sa.Column('thread_id', sa.Uuid(), nullable=False),
    sa.Column('cursor', sa.BigInteger(), nullable=False),
    sa.Column('kind', sa.Text(), nullable=False),
    sa.Column('source_kind', sa.Text(), nullable=False),
    sa.Column('source_key', sa.Text(), nullable=False),
    sa.Column('source_id', sa.Text(), nullable=True),
    sa.Column('source_version', sa.BigInteger(), server_default='1', nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('workspace_id', sa.Uuid(), nullable=False),
    sa.CheckConstraint('cursor >= 1 AND source_version >= 1', name=op.f('ck_agent_events_versions')),
    sa.ForeignKeyConstraint(['workspace_id', 'social_account_id', 'thread_id'], ['agent_threads.workspace_id', 'agent_threads.social_account_id', 'agent_threads.id'], name=op.f('fk_agent_events_workspace_id_social_account_id_thread_id_agent_threads'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], name=op.f('fk_agent_events_workspace_id_workspaces'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_agent_events')),
    sa.UniqueConstraint('workspace_id', 'id', name=op.f('uq_agent_events_workspace_id_id')),
    sa.UniqueConstraint('workspace_id', 'social_account_id', 'source_kind', 'source_key', name=op.f('uq_agent_events_workspace_id_social_account_id_source_kind_source_key')),
    sa.UniqueConstraint('workspace_id', 'thread_id', 'cursor', name=op.f('uq_agent_events_workspace_id_thread_id_cursor')),
    sa.UniqueConstraint('workspace_id', 'thread_id', 'id', name=op.f('uq_agent_events_workspace_id_thread_id_id'))
    )
    op.create_index('ix_agent_events_thread_cursor', 'agent_events', ['workspace_id', 'thread_id', 'cursor'], unique=False)
    op.create_index(op.f('ix_agent_events_workspace_id'), 'agent_events', ['workspace_id'], unique=False)
    op.create_table('agent_sessions',
    sa.Column('thread_id', sa.Uuid(), nullable=False),
    sa.Column('initiating_event_cursor', sa.BigInteger(), nullable=False),
    sa.Column('goal_key', sa.Text(), nullable=False),
    sa.Column('status', sa.Text(), server_default='queued', nullable=False),
    sa.Column('version', sa.BigInteger(), server_default='1', nullable=False),
    sa.Column('model_steps', sa.Integer(), server_default='0', nullable=False),
    sa.Column('tool_calls', sa.Integer(), server_default='0', nullable=False),
    sa.Column('input_tokens', sa.BigInteger(), server_default='0', nullable=False),
    sa.Column('output_tokens', sa.BigInteger(), server_default='0', nullable=False),
    sa.Column('cost_microusd', sa.BigInteger(), server_default='0', nullable=False),
    sa.Column('deadline_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('wake_kind', sa.Text(), nullable=True),
    sa.Column('wake_ref', sa.Text(), nullable=True),
    sa.Column('wake_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('workspace_id', sa.Uuid(), nullable=False),
    sa.CheckConstraint("status IN ('queued', 'running', 'waiting_customer', 'waiting_owner', 'waiting_approval', 'waiting_operation', 'sleeping', 'completed', 'cancelled', 'failed')", name=op.f('ck_agent_sessions_status')),
    sa.CheckConstraint('model_steps >= 0 AND tool_calls >= 0 AND input_tokens >= 0 AND output_tokens >= 0 AND cost_microusd >= 0', name=op.f('ck_agent_sessions_usage')),
    sa.CheckConstraint('version >= 1 AND initiating_event_cursor >= 0', name=op.f('ck_agent_sessions_versions')),
    sa.ForeignKeyConstraint(['workspace_id', 'thread_id'], ['agent_threads.workspace_id', 'agent_threads.id'], name=op.f('fk_agent_sessions_workspace_id_thread_id_agent_threads'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], name=op.f('fk_agent_sessions_workspace_id_workspaces'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_agent_sessions')),
    sa.UniqueConstraint('workspace_id', 'id', name=op.f('uq_agent_sessions_workspace_id_id')),
    sa.UniqueConstraint('workspace_id', 'thread_id', 'goal_key', name=op.f('uq_agent_sessions_workspace_id_thread_id_goal_key')),
    sa.UniqueConstraint('workspace_id', 'thread_id', 'id', name=op.f('uq_agent_sessions_workspace_id_thread_id_id'))
    )
    op.create_index(op.f('ix_agent_sessions_workspace_id'), 'agent_sessions', ['workspace_id'], unique=False)
    op.create_index('uq_agent_sessions_active_thread', 'agent_sessions', ['workspace_id', 'thread_id'], unique=True, postgresql_where=sa.text("status IN ('queued', 'running', 'waiting_customer', 'waiting_owner', 'waiting_approval', 'waiting_operation', 'sleeping')"))
    op.create_table('agent_actions',
    sa.Column('thread_id', sa.Uuid(), nullable=False),
    sa.Column('social_account_id', sa.Uuid(), nullable=False),
    sa.Column('session_id', sa.Uuid(), nullable=False),
    sa.Column('intent_key', sa.Text(), nullable=False),
    sa.Column('action_type', sa.Text(), nullable=False),
    sa.Column('payload_ref', sa.Uuid(), nullable=True),
    sa.Column('payload_hash', sa.Text(), nullable=False),
    sa.Column('version', sa.Integer(), server_default='1', nullable=False),
    sa.Column('target_ref', sa.Text(), nullable=False),
    sa.Column('initiating_event_id', sa.Uuid(), nullable=True),
    sa.Column('initiating_cursor', sa.BigInteger(), nullable=False),
    sa.Column('status', sa.Text(), server_default='proposed', nullable=False),
    sa.Column('delegation_version', sa.Integer(), nullable=True),
    sa.Column('policy_grant', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('approval_id', sa.Uuid(), nullable=True),
    sa.Column('operation_id', sa.Uuid(), nullable=True),
    sa.Column('execute_before', sa.DateTime(timezone=True), nullable=True),
    sa.Column('outcome_code', sa.Text(), nullable=True),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('workspace_id', sa.Uuid(), nullable=False),
    sa.CheckConstraint("payload_hash ~ '^[0-9a-f]{64}$'", name=op.f('ck_agent_actions_payload_hash')),
    sa.CheckConstraint("status IN ('proposed', 'waiting_approval', 'authorized', 'queued', 'in_progress', 'succeeded', 'failed', 'outcome_unknown', 'cancelled')", name=op.f('ck_agent_actions_status')),
    sa.CheckConstraint('version >= 1 AND initiating_cursor >= 0', name=op.f('ck_agent_actions_versions')),
    sa.ForeignKeyConstraint(['workspace_id', 'approval_id'], ['approvals.workspace_id', 'approvals.id'], name=op.f('fk_agent_actions_workspace_id_approval_id_approvals')),
    sa.ForeignKeyConstraint(['workspace_id', 'social_account_id', 'operation_id'], ['operations.workspace_id', 'operations.social_account_id', 'operations.id'], name=op.f('fk_agent_actions_workspace_id_social_account_id_operation_id_operations')),
    sa.ForeignKeyConstraint(['workspace_id', 'thread_id', 'initiating_event_id'], ['agent_events.workspace_id', 'agent_events.thread_id', 'agent_events.id'], name=op.f('fk_agent_actions_workspace_id_thread_id_initiating_event_id_agent_events')),
    sa.ForeignKeyConstraint(['workspace_id', 'thread_id', 'session_id'], ['agent_sessions.workspace_id', 'agent_sessions.thread_id', 'agent_sessions.id'], name=op.f('fk_agent_actions_workspace_id_thread_id_session_id_agent_sessions')),
    sa.ForeignKeyConstraint(['workspace_id', 'social_account_id', 'thread_id'], ['agent_threads.workspace_id', 'agent_threads.social_account_id', 'agent_threads.id'], name=op.f('fk_agent_actions_workspace_id_social_account_id_thread_id_agent_threads'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], name=op.f('fk_agent_actions_workspace_id_workspaces'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_agent_actions')),
    sa.UniqueConstraint('workspace_id', 'id', name=op.f('uq_agent_actions_workspace_id_id')),
    sa.UniqueConstraint('workspace_id', 'social_account_id', 'id', name=op.f('uq_agent_actions_workspace_id_social_account_id_id')),
    sa.UniqueConstraint('workspace_id', 'thread_id', 'intent_key', name=op.f('uq_agent_actions_workspace_id_thread_id_intent_key'))
    )
    op.create_index(op.f('ix_agent_actions_workspace_id'), 'agent_actions', ['workspace_id'], unique=False)
    op.create_table('agent_steps',
    sa.Column('session_id', sa.Uuid(), nullable=False),
    sa.Column('sequence', sa.Integer(), nullable=False),
    sa.Column('status', sa.Text(), server_default='claimed', nullable=False),
    sa.Column('claim_token', sa.Uuid(), nullable=False),
    sa.Column('lease_expires_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('captured_cursor', sa.BigInteger(), nullable=False),
    sa.Column('captured_epoch', sa.BigInteger(), nullable=False),
    sa.Column('captured_policy_version', sa.Integer(), nullable=True),
    sa.Column('captured_deletion_generation', sa.BigInteger(), nullable=False),
    sa.Column('model_version', sa.Text(), nullable=True),
    sa.Column('prompt_version', sa.Text(), nullable=True),
    sa.Column('tool_version', sa.Text(), nullable=True),
    sa.Column('input_ref', sa.Text(), nullable=True),
    sa.Column('output_ref', sa.Text(), nullable=True),
    sa.Column('reserved_tokens', sa.BigInteger(), server_default='0', nullable=False),
    sa.Column('input_tokens', sa.BigInteger(), server_default='0', nullable=False),
    sa.Column('output_tokens', sa.BigInteger(), server_default='0', nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('workspace_id', sa.Uuid(), nullable=False),
    sa.CheckConstraint("status IN ('claimed', 'model_pending', 'model_done', 'dispatched', 'consumed', 'stale', 'abandoned', 'failed')", name=op.f('ck_agent_steps_status')),
    sa.CheckConstraint('reserved_tokens >= 0 AND input_tokens >= 0 AND output_tokens >= 0', name=op.f('ck_agent_steps_usage')),
    sa.CheckConstraint('sequence >= 1 AND captured_cursor >= 0 AND captured_epoch >= 0 AND captured_deletion_generation >= 0', name=op.f('ck_agent_steps_versions')),
    sa.ForeignKeyConstraint(['workspace_id', 'session_id'], ['agent_sessions.workspace_id', 'agent_sessions.id'], name=op.f('fk_agent_steps_workspace_id_session_id_agent_sessions'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], name=op.f('fk_agent_steps_workspace_id_workspaces'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_agent_steps')),
    sa.UniqueConstraint('claim_token', name=op.f('uq_agent_steps_claim_token')),
    sa.UniqueConstraint('workspace_id', 'id', name=op.f('uq_agent_steps_workspace_id_id')),
    sa.UniqueConstraint('workspace_id', 'session_id', 'sequence', name=op.f('uq_agent_steps_workspace_id_session_id_sequence'))
    )
    op.create_index(op.f('ix_agent_steps_workspace_id'), 'agent_steps', ['workspace_id'], unique=False)
    op.add_column('agent_runs', sa.Column('agent_step_id', sa.Uuid(), nullable=True))
    op.drop_constraint(op.f('ck_agent_runs_task'), 'agent_runs', type_='check')
    op.create_check_constraint(
        op.f('ck_agent_runs_task'), 'agent_runs',
        "task IN ('interpret_command', 'draft_reply', 'draft_content', "
        "'extract_fact_candidates', 'account_agent_step')",
    )
    op.create_index(op.f('ix_agent_runs_agent_step_id'), 'agent_runs', ['agent_step_id'], unique=False)
    op.create_foreign_key(op.f('fk_agent_runs_workspace_id_agent_step_id_agent_steps'), 'agent_runs', 'agent_steps', ['workspace_id', 'agent_step_id'], ['workspace_id', 'id'])
    op.add_column('content_items', sa.Column('origin', sa.Text(), server_default='legacy', nullable=False))
    op.add_column('content_items', sa.Column('agent_action_id', sa.Uuid(), nullable=True))
    op.create_check_constraint(op.f('ck_content_items_origin'), 'content_items',
                               "origin IN ('legacy', 'agent')")
    op.create_check_constraint(op.f('ck_content_items_agent_origin'), 'content_items',
        "(origin = 'legacy' AND agent_action_id IS NULL) OR "
        "(origin = 'agent' AND agent_action_id IS NOT NULL AND social_account_id IS NOT NULL)")
    op.create_foreign_key(op.f('fk_content_items_workspace_id_social_account_id_agent_action_id_agent_actions'), 'content_items', 'agent_actions', ['workspace_id', 'social_account_id', 'agent_action_id'], ['workspace_id', 'social_account_id', 'id'])
    op.add_column('reply_drafts', sa.Column('origin', sa.Text(), server_default='legacy', nullable=False))
    op.add_column('reply_drafts', sa.Column('agent_action_id', sa.Uuid(), nullable=True))
    op.create_check_constraint(op.f('ck_reply_drafts_origin'), 'reply_drafts',
                               "origin IN ('legacy', 'agent')")
    op.create_check_constraint(op.f('ck_reply_drafts_agent_origin'), 'reply_drafts',
        "(origin = 'legacy' AND agent_action_id IS NULL) OR "
        "(origin = 'agent' AND agent_action_id IS NOT NULL)")
    op.create_foreign_key(op.f('fk_reply_drafts_workspace_id_agent_action_id_agent_actions'), 'reply_drafts', 'agent_actions', ['workspace_id', 'agent_action_id'], ['workspace_id', 'id'])
    # Existing accounts retain legacy handling. No row grants authority.
    op.execute(
        "INSERT INTO account_agents (id, workspace_id, social_account_id, controller_mode, state) "
        "SELECT gen_random_uuid(), workspace_id, id, 'legacy', 'inactive' FROM social_accounts"
    )
    op.execute("""
        CREATE FUNCTION initialize_account_agent() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            INSERT INTO account_agents (id, workspace_id, social_account_id, controller_mode, state)
            VALUES (gen_random_uuid(), NEW.workspace_id, NEW.id, 'legacy', 'inactive');
            RETURN NEW;
        END; $$
    """)
    op.execute("""
        CREATE TRIGGER social_accounts_initialize_agent
        AFTER INSERT ON social_accounts FOR EACH ROW EXECUTE FUNCTION initialize_account_agent()
    """)


def downgrade() -> None:
    connection = op.get_bind()
    evidence = connection.execute(sa.text(
        "SELECT EXISTS (SELECT 1 FROM agent_delegations) OR "
        "EXISTS (SELECT 1 FROM agent_threads) OR EXISTS (SELECT 1 FROM agent_events) OR "
        "EXISTS (SELECT 1 FROM agent_sessions) OR EXISTS (SELECT 1 FROM agent_steps) OR "
        "EXISTS (SELECT 1 FROM agent_actions) OR "
        "EXISTS (SELECT 1 FROM agent_runs WHERE agent_step_id IS NOT NULL "
        "OR task = 'account_agent_step') OR "
        "EXISTS (SELECT 1 FROM reply_drafts WHERE agent_action_id IS NOT NULL) OR "
        "EXISTS (SELECT 1 FROM content_items WHERE agent_action_id IS NOT NULL) OR "
        "EXISTS (SELECT 1 FROM account_agents WHERE controller_mode <> 'legacy' "
        "OR state <> 'inactive' OR controller_epoch <> 0 OR config_version <> 1 "
        "OR persona_version <> 1 OR goals <> '{}'::jsonb OR persona <> '{}'::jsonb)"
    )).scalar_one()
    if evidence:
        raise RuntimeError('agent evidence must be preserved before downgrading 0019')
    op.execute('DROP TRIGGER social_accounts_initialize_agent ON social_accounts')
    op.execute('DROP FUNCTION initialize_account_agent()')
    op.drop_constraint(op.f('fk_reply_drafts_workspace_id_agent_action_id_agent_actions'), 'reply_drafts', type_='foreignkey')
    op.drop_constraint(op.f('ck_reply_drafts_agent_origin'), 'reply_drafts', type_='check')
    op.drop_constraint(op.f('ck_reply_drafts_origin'), 'reply_drafts', type_='check')
    op.drop_column('reply_drafts', 'agent_action_id')
    op.drop_column('reply_drafts', 'origin')
    op.drop_constraint(op.f('fk_content_items_workspace_id_social_account_id_agent_action_id_agent_actions'), 'content_items', type_='foreignkey')
    op.drop_constraint(op.f('ck_content_items_agent_origin'), 'content_items', type_='check')
    op.drop_constraint(op.f('ck_content_items_origin'), 'content_items', type_='check')
    op.drop_column('content_items', 'agent_action_id')
    op.drop_column('content_items', 'origin')
    op.drop_constraint(op.f('fk_agent_runs_workspace_id_agent_step_id_agent_steps'), 'agent_runs', type_='foreignkey')
    op.drop_constraint(op.f('ck_agent_runs_task'), 'agent_runs', type_='check')
    op.create_check_constraint(
        op.f('ck_agent_runs_task'), 'agent_runs',
        "task IN ('interpret_command', 'draft_reply', 'draft_content', 'extract_fact_candidates')",
    )
    op.drop_index(op.f('ix_agent_runs_agent_step_id'), table_name='agent_runs')
    op.drop_column('agent_runs', 'agent_step_id')
    op.drop_index(op.f('ix_agent_steps_workspace_id'), table_name='agent_steps')
    op.drop_table('agent_steps')
    op.drop_index(op.f('ix_agent_actions_workspace_id'), table_name='agent_actions')
    op.drop_table('agent_actions')
    op.drop_constraint(op.f('uq_operations_workspace_id_social_account_id_id'), 'operations', type_='unique')
    op.drop_index('uq_agent_sessions_active_thread', table_name='agent_sessions', postgresql_where=sa.text("status IN ('queued', 'running', 'waiting_customer', 'waiting_owner', 'waiting_approval', 'waiting_operation', 'sleeping')"))
    op.drop_index(op.f('ix_agent_sessions_workspace_id'), table_name='agent_sessions')
    op.drop_table('agent_sessions')
    op.drop_index(op.f('ix_agent_events_workspace_id'), table_name='agent_events')
    op.drop_index('ix_agent_events_thread_cursor', table_name='agent_events')
    op.drop_table('agent_events')
    op.drop_index(op.f('ix_agent_threads_workspace_id'), table_name='agent_threads')
    op.drop_index('ix_agent_threads_account_state_activity', table_name='agent_threads')
    op.drop_table('agent_threads')
    op.drop_constraint(op.f('uq_conversations_workspace_id_social_account_id_id'), 'conversations', type_='unique')
    op.drop_index('uq_agent_delegations_current', table_name='agent_delegations', postgresql_where=sa.text('revoked_at IS NULL'))
    op.drop_index(op.f('ix_agent_delegations_workspace_id'), table_name='agent_delegations')
    op.drop_table('agent_delegations')
    op.drop_index(op.f('ix_account_agents_workspace_id'), table_name='account_agents')
    op.drop_table('account_agents')
