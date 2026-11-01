"""RLS bootstrap functions and narrow pre-context security-definer helpers (P8-03 / ADR-025 §1.4)."""

from alembic import op
import sqlalchemy as sa

revision = "0031"
down_revision = "0030"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Webhook social account resolution by external account id
    op.execute(
        sa.text(
            """
            CREATE OR REPLACE FUNCTION public.resolve_social_account_by_external(
                p_provider_kind text,
                p_external_account_id text
            )
            RETURNS TABLE (
                id uuid,
                workspace_id uuid,
                status text,
                provider_kind text,
                external_account_id text
            )
            LANGUAGE sql
            SECURITY DEFINER
            SET search_path = public, pg_temp
            STABLE
            AS $$
                SELECT sa.id, sa.workspace_id, sa.status, sa.provider_kind, sa.external_account_id
                FROM public.social_accounts sa
                WHERE sa.provider_kind = p_provider_kind
                  AND sa.external_account_id = p_external_account_id
                ORDER BY (sa.status = 'disconnected'), sa.created_at DESC
                LIMIT 1;
            $$;

            GRANT EXECUTE ON FUNCTION public.resolve_social_account_by_external(text, text) TO PUBLIC;
            """
        )
    )

    # 2. Invite resolution by token hash (bytea)
    op.execute(
        sa.text(
            """
            CREATE OR REPLACE FUNCTION public.resolve_invite_by_token_hash(
                p_token_hash bytea
            )
            RETURNS TABLE (
                id uuid,
                workspace_id uuid,
                role text,
                expires_at timestamptz,
                revoked_at timestamptz,
                accepted_at timestamptz
            )
            LANGUAGE sql
            SECURITY DEFINER
            SET search_path = public, pg_temp
            STABLE
            AS $$
                SELECT i.id, i.workspace_id, i.role, i.expires_at, i.revoked_at, i.accepted_at
                FROM public.invites i
                WHERE i.token_hash = p_token_hash
                LIMIT 1;
            $$;

            GRANT EXECUTE ON FUNCTION public.resolve_invite_by_token_hash(bytea) TO PUBLIC;
            """
        )
    )

    # 3. OAuth state resolution by state hash (bytea)
    op.execute(
        sa.text(
            """
            CREATE OR REPLACE FUNCTION public.resolve_oauth_state_by_hash(
                p_state_hash bytea
            )
            RETURNS TABLE (
                id uuid,
                workspace_id uuid,
                user_id uuid,
                expires_at timestamptz,
                invalidated_at timestamptz,
                used_at timestamptz
            )
            LANGUAGE sql
            SECURITY DEFINER
            SET search_path = public, pg_temp
            STABLE
            AS $$
                SELECT s.id, s.workspace_id, s.user_id, s.expires_at, s.invalidated_at, s.used_at
                FROM public.oauth_states s
                WHERE s.state_hash = p_state_hash
                LIMIT 1;
            $$;

            GRANT EXECUTE ON FUNCTION public.resolve_oauth_state_by_hash(bytea) TO PUBLIC;
            """
        )
    )

    # 4. Periodic discovery: due approvals
    op.execute(
        sa.text(
            """
            CREATE OR REPLACE FUNCTION public.discover_expired_approval_ids(
                p_now timestamptz,
                p_limit int DEFAULT 100
            )
            RETURNS TABLE (
                id uuid,
                workspace_id uuid
            )
            LANGUAGE sql
            SECURITY DEFINER
            SET search_path = public, pg_temp
            STABLE
            AS $$
                SELECT a.id, a.workspace_id
                FROM public.approvals a
                WHERE a.status = 'pending'
                  AND a.expires_at <= p_now
                ORDER BY a.expires_at, a.id
                LIMIT p_limit;
            $$;

            GRANT EXECUTE ON FUNCTION public.discover_expired_approval_ids(timestamptz, int) TO PUBLIC;
            """
        )
    )

    # 5. Periodic discovery: due reply drafts (24h messaging window)
    op.execute(
        sa.text(
            """
            CREATE OR REPLACE FUNCTION public.discover_expired_reply_draft_ids(
                p_cutoff timestamptz,
                p_limit int DEFAULT 100
            )
            RETURNS TABLE (
                id uuid,
                workspace_id uuid
            )
            LANGUAGE sql
            SECURITY DEFINER
            SET search_path = public, pg_temp
            STABLE
            AS $$
                SELECT rd.id, rd.workspace_id
                FROM public.reply_drafts rd
                JOIN public.conversations c
                  ON c.workspace_id = rd.workspace_id
                 AND c.id = rd.conversation_id
                WHERE rd.status IN ('pending_approval', 'needs_human', 'queued')
                  AND c.last_inbound_at <= p_cutoff
                ORDER BY rd.created_at, rd.id
                LIMIT p_limit;
            $$;

            GRANT EXECUTE ON FUNCTION public.discover_expired_reply_draft_ids(timestamptz, int) TO PUBLIC;
            """
        )
    )

    # 6. Periodic discovery: due owner command clarifications
    op.execute(
        sa.text(
            """
            CREATE OR REPLACE FUNCTION public.discover_expired_command_ids(
                p_now timestamptz,
                p_limit int DEFAULT 100
            )
            RETURNS TABLE (
                id uuid,
                workspace_id uuid
            )
            LANGUAGE sql
            SECURITY DEFINER
            SET search_path = public, pg_temp
            STABLE
            AS $$
                SELECT c.id, c.workspace_id
                FROM public.owner_commands c
                WHERE c.status = 'needs_clarification'
                  AND c.expires_at <= p_now
                ORDER BY c.expires_at, c.id
                LIMIT p_limit;
            $$;

            GRANT EXECUTE ON FUNCTION public.discover_expired_command_ids(timestamptz, int) TO PUBLIC;
            """
        )
    )

    # 7. Periodic discovery: stuck operations
    op.execute(
        sa.text(
            """
            CREATE OR REPLACE FUNCTION public.discover_stuck_operations(
                p_cutoff timestamptz,
                p_limit int DEFAULT 100
            )
            RETURNS TABLE (
                id uuid,
                workspace_id uuid,
                subject_type text,
                status text
            )
            LANGUAGE sql
            SECURITY DEFINER
            SET search_path = public, pg_temp
            STABLE
            AS $$
                SELECT o.id, o.workspace_id, o.subject_type, o.status
                FROM public.operations o
                WHERE o.status IN ('in_progress', 'outcome_unknown')
                  AND o.updated_at <= p_cutoff
                ORDER BY o.updated_at, o.id
                LIMIT p_limit;
            $$;

            GRANT EXECUTE ON FUNCTION public.discover_stuck_operations(timestamptz, int) TO PUBLIC;
            """
        )
    )

    # 8. Periodic discovery: stuck agent sessions
    op.execute(
        sa.text(
            """
            CREATE OR REPLACE FUNCTION public.discover_stuck_agent_sessions(
                p_cutoff timestamptz,
                p_limit int DEFAULT 100
            )
            RETURNS TABLE (
                id uuid,
                workspace_id uuid
            )
            LANGUAGE sql
            SECURITY DEFINER
            SET search_path = public, pg_temp
            STABLE
            AS $$
                SELECT s.id, s.workspace_id
                FROM public.agent_sessions s
                WHERE s.status = 'active'
                  AND s.updated_at <= p_cutoff
                ORDER BY s.updated_at, s.id
                LIMIT p_limit;
            $$;

            GRANT EXECUTE ON FUNCTION public.discover_stuck_agent_sessions(timestamptz, int) TO PUBLIC;
            """
        )
    )


def downgrade() -> None:
    op.execute(sa.text("DROP FUNCTION IF EXISTS public.discover_stuck_agent_sessions(timestamptz, int)"))
    op.execute(sa.text("DROP FUNCTION IF EXISTS public.discover_stuck_operations(timestamptz, int)"))
    op.execute(sa.text("DROP FUNCTION IF EXISTS public.discover_expired_command_ids(timestamptz, int)"))
    op.execute(sa.text("DROP FUNCTION IF EXISTS public.discover_expired_reply_draft_ids(timestamptz, int)"))
    op.execute(sa.text("DROP FUNCTION IF EXISTS public.discover_expired_approval_ids(timestamptz, int)"))
    op.execute(sa.text("DROP FUNCTION IF EXISTS public.resolve_oauth_state_by_hash(bytea)"))
    op.execute(sa.text("DROP FUNCTION IF EXISTS public.resolve_invite_by_token_hash(bytea)"))
    op.execute(sa.text("DROP FUNCTION IF EXISTS public.resolve_social_account_by_external(text, text)"))
