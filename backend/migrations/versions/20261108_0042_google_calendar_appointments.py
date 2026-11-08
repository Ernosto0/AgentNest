"""Google Calendar integration and appointments tables.

Revision ID: 0042
Revises: 0041
Create Date: 2026-11-08 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0042"
down_revision: str | None = "0041"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "calendar_connections",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("provider_kind", sa.Text(), nullable=False),
        sa.Column("external_account_id", sa.Text(), nullable=False),
        sa.Column("account_email", sa.Text(), nullable=True),
        sa.Column("calendar_id", sa.Text(), nullable=False, server_default="primary"),
        sa.Column("calendar_summary", sa.Text(), nullable=True),
        sa.Column("calendar_timezone", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default="connected"),
        sa.Column(
            "capabilities",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "granted_scopes",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.Column(
            "default_slot_duration_minutes",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("30"),
        ),
        sa.Column("token_ciphertext", sa.LargeBinary(), nullable=True),
        sa.Column("refresh_token_ciphertext", sa.LargeBinary(), nullable=True),
        sa.Column("token_key_id", sa.Text(), nullable=True),
        sa.Column("token_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("token_refreshed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "consecutive_failures",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("degraded_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failure_window_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_code", sa.Text(), nullable=True),
        sa.Column("connected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("disconnected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_calendar_connections")),
        sa.UniqueConstraint(
            "workspace_id", "id", name=op.f("uq_calendar_connections_workspace_id_id")
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name=op.f("fk_calendar_connections_workspace_id_workspaces"),
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "provider_kind IN ('mock', 'google')",
            name=op.f("ck_calendar_connections_provider_kind"),
        ),
        sa.CheckConstraint(
            "status IN ('connected', 'needs_reauth', 'degraded', 'disconnected')",
            name=op.f("ck_calendar_connections_status"),
        ),
        sa.CheckConstraint(
            "consecutive_failures >= 0",
            name=op.f("ck_calendar_connections_consecutive_failures"),
        ),
        sa.CheckConstraint(
            "default_slot_duration_minutes >= 15 AND default_slot_duration_minutes <= 240",
            name=op.f("ck_calendar_connections_slot_duration_range"),
        ),
        sa.CheckConstraint(
            "provider_kind = 'google' OR (token_ciphertext IS NULL AND refresh_token_ciphertext IS NULL)",
            name=op.f("ck_calendar_connections_mock_no_token"),
        ),
    )
    op.create_index(
        op.f("ix_calendar_connections_workspace_id"),
        "calendar_connections",
        ["workspace_id"],
        unique=False,
    )
    op.create_index(
        "uq_calendar_connections_active_workspace",
        "calendar_connections",
        ["workspace_id"],
        unique=True,
        postgresql_where=sa.text("status <> 'disconnected'"),
    )

    op.create_table(
        "calendar_oauth_states",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("state_hash", sa.LargeBinary(), nullable=False),
        sa.Column("purpose", sa.Text(), nullable=False),
        sa.Column("calendar_connection_id", sa.Uuid(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("invalidated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_calendar_oauth_states")),
        sa.UniqueConstraint(
            "workspace_id", "id", name=op.f("uq_calendar_oauth_states_workspace_id_id")
        ),
        sa.UniqueConstraint(
            "state_hash", name=op.f("uq_calendar_oauth_states_state_hash")
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name=op.f("fk_calendar_oauth_states_workspace_id_workspaces"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_calendar_oauth_states_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "calendar_connection_id"],
            ["calendar_connections.workspace_id", "calendar_connections.id"],
            name=op.f(
                "fk_calendar_oauth_states_workspace_id_calendar_connection_id_calendar_connections"
            ),
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "purpose IN ('connect', 'reconnect')",
            name=op.f("ck_calendar_oauth_states_purpose"),
        ),
        sa.CheckConstraint(
            "(purpose = 'connect' AND calendar_connection_id IS NULL) OR "
            "(purpose = 'reconnect' AND calendar_connection_id IS NOT NULL)",
            name=op.f("ck_calendar_oauth_states_purpose_connection"),
        ),
    )
    op.create_index(
        op.f("ix_calendar_oauth_states_workspace_id"),
        "calendar_oauth_states",
        ["workspace_id"],
        unique=False,
    )

    op.create_table(
        "calendar_appointments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("calendar_connection_id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=True),
        sa.Column("customer_identity_id", sa.Uuid(), nullable=True),
        sa.Column("external_event_id", sa.Text(), nullable=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("customer_name", sa.Text(), nullable=True),
        sa.Column("customer_contact", sa.Text(), nullable=True),
        sa.Column("start_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("timezone", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="scheduled"),
        sa.Column("created_by_source", sa.Text(), nullable=False),
        sa.Column(
            "is_simulated",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "version",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("1"),
        ),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancellation_reason", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_calendar_appointments")),
        sa.UniqueConstraint(
            "workspace_id", "id", name=op.f("uq_calendar_appointments_workspace_id_id")
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name=op.f("fk_calendar_appointments_workspace_id_workspaces"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "calendar_connection_id"],
            ["calendar_connections.workspace_id", "calendar_connections.id"],
            name=op.f(
                "fk_calendar_appointments_workspace_id_calendar_connection_id_calendar_connections"
            ),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "conversation_id"],
            ["conversations.workspace_id", "conversations.id"],
            name=op.f("fk_calendar_appointments_workspace_id_conversation_id_conversations"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "customer_identity_id"],
            ["customer_identities.workspace_id", "customer_identities.id"],
            name=op.f(
                "fk_calendar_appointments_workspace_id_customer_identity_id_customer_identities"
            ),
            ondelete="SET NULL",
        ),
        sa.CheckConstraint(
            "status IN ('scheduled', 'cancelled', 'completed')",
            name=op.f("ck_calendar_appointments_status"),
        ),
        sa.CheckConstraint(
            "created_by_source IN ('customer', 'owner', 'owner_task')",
            name=op.f("ck_calendar_appointments_created_by_source"),
        ),
        sa.CheckConstraint(
            "end_at > start_at",
            name=op.f("ck_calendar_appointments_valid_interval"),
        ),
        sa.CheckConstraint(
            "version >= 1",
            name=op.f("ck_calendar_appointments_positive_version"),
        ),
    )
    op.create_index(
        op.f("ix_calendar_appointments_workspace_id"),
        "calendar_appointments",
        ["workspace_id"],
        unique=False,
    )
    op.create_index(
        "ix_calendar_appointments_workspace_window",
        "calendar_appointments",
        ["workspace_id", "status", "start_at", "end_at"],
        unique=False,
    )
    op.create_index(
        "ix_calendar_appointments_customer",
        "calendar_appointments",
        ["workspace_id", "customer_identity_id", "start_at"],
        unique=False,
    )

    op.create_table(
        "sim_calendar_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("calendar_connection_id", sa.Uuid(), nullable=False),
        sa.Column("external_event_id", sa.Text(), nullable=False),
        sa.Column("operation_key", sa.Text(), nullable=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("start_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="confirmed"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sim_calendar_events")),
        sa.UniqueConstraint(
            "workspace_id", "id", name=op.f("uq_sim_calendar_events_workspace_id_id")
        ),
        sa.UniqueConstraint(
            "calendar_connection_id",
            "external_event_id",
            name=op.f("uq_sim_calendar_events_calendar_connection_id_external_event_id"),
        ),
        sa.UniqueConstraint(
            "calendar_connection_id",
            "operation_key",
            name=op.f("uq_sim_calendar_events_calendar_connection_id_operation_key"),
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name=op.f("fk_sim_calendar_events_workspace_id_workspaces"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "calendar_connection_id"],
            ["calendar_connections.workspace_id", "calendar_connections.id"],
            name=op.f(
                "fk_sim_calendar_events_workspace_id_calendar_connection_id_calendar_connections"
            ),
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "status IN ('confirmed', 'cancelled')",
            name=op.f("ck_sim_calendar_events_status"),
        ),
        sa.CheckConstraint(
            "end_at > start_at",
            name=op.f("ck_sim_calendar_events_valid_interval"),
        ),
    )
    op.create_index(
        op.f("ix_sim_calendar_events_workspace_id"),
        "sim_calendar_events",
        ["workspace_id"],
        unique=False,
    )
    op.create_index(
        "ix_sim_calendar_events_window",
        "sim_calendar_events",
        ["calendar_connection_id", "status", "start_at", "end_at"],
        unique=False,
    )

    op.drop_constraint(op.f("ck_operations_operation_type"), "operations", type_="check")
    op.create_check_constraint(
        "operation_type",
        "operations",
        "operation_type IN ('send_reply','publish_content','refresh_token',"
        "'comment_reply','comment_hide','comment_unhide','comment_delete',"
        "'comment_private_reply','calendar_create_event','calendar_update_event',"
        "'calendar_cancel_event')",
    )
    op.drop_constraint(op.f("ck_operations_provider_kind"), "operations", type_="check")
    op.create_check_constraint(
        "provider_kind",
        "operations",
        "provider_kind IN ('mock', 'meta', 'google')",
    )

    op.drop_constraint(op.f("ck_approvals_action"), "approvals", type_="check")
    op.create_check_constraint(
        op.f("ck_approvals_action"),
        "approvals",
        "action IN ('command.update_fact', 'command.update_brand_voice', "
        "'command.cancel_content', 'reply.send', 'content.publish', 'comments.approve', "
        "'content.prepare', 'content.schedule', 'content.cancel', "
        "'calendar.book', 'calendar.reschedule', 'calendar.cancel')",
    )
    op.drop_constraint(op.f("ck_approvals_subject_type"), "approvals", type_="check")
    op.create_check_constraint(
        op.f("ck_approvals_subject_type"),
        "approvals",
        "subject_type IN ('owner_command', 'reply_draft', 'content_item', 'agent_action', "
        "'calendar_appointment')",
    )

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        for table in (
            "calendar_connections",
            "calendar_oauth_states",
            "calendar_appointments",
            "sim_calendar_events",
        ):
            op.execute(sa.text(f"ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY"))
            op.execute(sa.text(f"ALTER TABLE public.{table} FORCE ROW LEVEL SECURITY"))
            op.execute(
                sa.text(
                    f"""
                    CREATE POLICY tenant_isolation_policy ON public.{table}
                        FOR ALL
                        USING (workspace_id = nullif(current_setting('app.workspace_id', true), '')::uuid)
                        WITH CHECK (workspace_id = nullif(current_setting('app.workspace_id', true), '')::uuid)
                    """
                )
            )

        op.execute(
            sa.text(
                """
                CREATE OR REPLACE FUNCTION public.resolve_calendar_oauth_state_by_hash(
                    p_state_hash bytea
                )
                RETURNS TABLE (
                    id uuid,
                    workspace_id uuid,
                    user_id uuid,
                    purpose text,
                    calendar_connection_id uuid,
                    expires_at timestamptz,
                    used_at timestamptz,
                    invalidated_at timestamptz
                )
                LANGUAGE sql
                SECURITY DEFINER
                SET search_path = public, pg_temp
                STABLE
                AS $$
                    SELECT s.id, s.workspace_id, s.user_id, s.purpose,
                           s.calendar_connection_id, s.expires_at, s.used_at, s.invalidated_at
                    FROM public.calendar_oauth_states s
                    WHERE s.state_hash = p_state_hash
                    LIMIT 1;
                $$;

                GRANT EXECUTE ON FUNCTION public.resolve_calendar_oauth_state_by_hash(bytea) TO PUBLIC;
                """
            )
        )

        op.execute(
            """
            DO $$
            BEGIN
                IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'agentnest_app') THEN
                    GRANT USAGE ON SCHEMA public TO agentnest_app;
                    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE
                        public.calendar_connections,
                        public.calendar_oauth_states,
                        public.calendar_appointments,
                        public.sim_calendar_events
                    TO agentnest_app;
                END IF;
                IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'agentnest_worker') THEN
                    GRANT USAGE ON SCHEMA public TO agentnest_worker;
                    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE
                        public.calendar_connections,
                        public.calendar_oauth_states,
                        public.calendar_appointments,
                        public.sim_calendar_events
                    TO agentnest_worker;
                END IF;
                IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'agentnest_migrator') THEN
                    GRANT ALL ON TABLE
                        public.calendar_connections,
                        public.calendar_oauth_states,
                        public.calendar_appointments,
                        public.sim_calendar_events
                    TO agentnest_migrator;
                END IF;
            END $$;
            """
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(
            sa.text("DROP FUNCTION IF EXISTS public.resolve_calendar_oauth_state_by_hash(bytea)")
        )
        for table in (
            "sim_calendar_events",
            "calendar_appointments",
            "calendar_oauth_states",
            "calendar_connections",
        ):
            op.execute(
                sa.text(f"DROP POLICY IF EXISTS tenant_isolation_policy ON public.{table}")
            )
            op.execute(sa.text(f"ALTER TABLE public.{table} NO FORCE ROW LEVEL SECURITY"))
            op.execute(sa.text(f"ALTER TABLE public.{table} DISABLE ROW LEVEL SECURITY"))

    op.drop_constraint(op.f("ck_approvals_subject_type"), "approvals", type_="check")
    op.create_check_constraint(
        op.f("ck_approvals_subject_type"),
        "approvals",
        "subject_type IN ('owner_command', 'reply_draft', 'content_item', 'agent_action')",
    )
    op.drop_constraint(op.f("ck_approvals_action"), "approvals", type_="check")
    op.create_check_constraint(
        op.f("ck_approvals_action"),
        "approvals",
        "action IN ('command.update_fact', 'command.update_brand_voice', "
        "'command.cancel_content', 'reply.send', 'content.publish', 'comments.approve', "
        "'content.prepare', 'content.schedule', 'content.cancel')",
    )
    op.drop_constraint(op.f("ck_operations_provider_kind"), "operations", type_="check")
    op.create_check_constraint(
        "provider_kind",
        "operations",
        "provider_kind IN ('mock', 'meta')",
    )
    op.drop_constraint(op.f("ck_operations_operation_type"), "operations", type_="check")
    op.create_check_constraint(
        "operation_type",
        "operations",
        "operation_type IN ('send_reply','publish_content','refresh_token',"
        "'comment_reply','comment_hide','comment_unhide','comment_delete','comment_private_reply')",
    )

    op.drop_index("ix_sim_calendar_events_window", table_name="sim_calendar_events")
    op.drop_index(op.f("ix_sim_calendar_events_workspace_id"), table_name="sim_calendar_events")
    op.drop_table("sim_calendar_events")

    op.drop_index("ix_calendar_appointments_customer", table_name="calendar_appointments")
    op.drop_index("ix_calendar_appointments_workspace_window", table_name="calendar_appointments")
    op.drop_index(
        op.f("ix_calendar_appointments_workspace_id"), table_name="calendar_appointments"
    )
    op.drop_table("calendar_appointments")

    op.drop_index(
        op.f("ix_calendar_oauth_states_workspace_id"), table_name="calendar_oauth_states"
    )
    op.drop_table("calendar_oauth_states")

    op.drop_index(
        "uq_calendar_connections_active_workspace",
        table_name="calendar_connections",
        postgresql_where=sa.text("status <> 'disconnected'"),
    )
    op.drop_index(
        op.f("ix_calendar_connections_workspace_id"), table_name="calendar_connections"
    )
    op.drop_table("calendar_connections")
