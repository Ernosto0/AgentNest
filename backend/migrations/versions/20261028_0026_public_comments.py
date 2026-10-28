"""Account-scoped public comments. Synthetic ingestion only. Revision 0026."""

import sqlalchemy as sa
from alembic import op

revision = "0026"
down_revision = "0025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint(op.f("ck_inbound_events_event_type"), "inbound_events", type_="check")
    op.create_check_constraint(
        "event_type",
        "inbound_events",
        "event_type IN ('message','echo','delete','reaction','read','postback','other','comment')",
    )
    op.drop_constraint(op.f("ck_inbound_events_ignore_reason"), "inbound_events", type_="check")
    op.create_check_constraint(
        "ignore_reason",
        "inbound_events",
        "ignore_reason IS NULL OR ignore_reason IN "
        "('UNKNOWN_ACCOUNT','ACCOUNT_DISCONNECTED','UNSUPPORTED_EVENT','PUBLIC_SOURCE_CONFLICT')",
    )
    op.execute("ALTER TABLE agent_steps ADD COLUMN captured_public_version bigint")
    op.execute("""

CREATE TABLE public_media (
	social_account_id UUID NOT NULL,
	external_id TEXT NOT NULL,
	caption TEXT,
	state TEXT NOT NULL,
	ownership_state TEXT NOT NULL,
	provider_version BIGINT NOT NULL,
	version BIGINT NOT NULL,
	provider_timestamp TIMESTAMP WITH TIME ZONE,
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
	is_simulated BOOLEAN NOT NULL,
	id UUID NOT NULL,
	workspace_id UUID NOT NULL,
	CONSTRAINT pk_public_media PRIMARY KEY (id),
	CONSTRAINT uq_public_media_workspace_id_id UNIQUE (workspace_id, id),
CONSTRAINT uq_public_media_workspace_id_social_account_id_id UNIQUE (workspace_id,
social_account_id, id),
CONSTRAINT fk_public_media_workspace_id_social_account_id_social_accounts FOREIGN
KEY(workspace_id, social_account_id) REFERENCES social_accounts (workspace_id, id),
CONSTRAINT uq_public_media_social_account_id_external_id UNIQUE (social_account_id,
external_id),
	CONSTRAINT ck_public_media_state CHECK (state IN ('unknown','visible','deleted')),
CONSTRAINT fk_public_media_workspace_id_workspaces FOREIGN KEY(workspace_id) REFERENCES
workspaces (id) ON DELETE CASCADE
)

;
CREATE INDEX ix_public_media_workspace_id ON public_media (workspace_id);

CREATE TABLE public_threads (
	social_account_id UUID NOT NULL,
	media_id UUID NOT NULL,
	root_external_id TEXT NOT NULL,
	id UUID NOT NULL,
	workspace_id UUID NOT NULL,
	CONSTRAINT pk_public_threads PRIMARY KEY (id),
	CONSTRAINT uq_public_threads_workspace_id_id UNIQUE (workspace_id, id),
CONSTRAINT uq_public_threads_workspace_id_social_account_id_id UNIQUE (workspace_id,
social_account_id, id),
CONSTRAINT fk_public_threads_workspace_id_social_account_id_social_5ea6 FOREIGN
KEY(workspace_id, social_account_id) REFERENCES social_accounts (workspace_id, id),
CONSTRAINT uq_public_threads_social_account_id_root_external_id UNIQUE (social_account_id,
root_external_id),
CONSTRAINT uq_public_threads_workspace_id_social_account_id_media_id_id UNIQUE (workspace_id,
social_account_id, media_id, id),
CONSTRAINT fk_public_threads_workspace_id_social_account_id_media__cc2c FOREIGN
KEY(workspace_id, social_account_id, media_id) REFERENCES public_media (workspace_id,
social_account_id, id),
CONSTRAINT fk_public_threads_workspace_id_workspaces FOREIGN KEY(workspace_id) REFERENCES
workspaces (id) ON DELETE CASCADE
)

;
CREATE INDEX ix_public_threads_workspace_id ON public_threads (workspace_id);

CREATE TABLE public_comments (
	social_account_id UUID NOT NULL,
	media_id UUID NOT NULL,
	thread_id UUID NOT NULL,
	external_id TEXT NOT NULL,
	parent_id UUID,
	author_external_id TEXT,
	text TEXT,
	state TEXT NOT NULL,
	version BIGINT NOT NULL,
	provider_version BIGINT NOT NULL,
	provider_timestamp TIMESTAMP WITH TIME ZONE,
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
	is_owner BOOLEAN NOT NULL,
	is_simulated BOOLEAN NOT NULL,
	id UUID NOT NULL,
	workspace_id UUID NOT NULL,
	CONSTRAINT pk_public_comments PRIMARY KEY (id),
	CONSTRAINT uq_public_comments_workspace_id_id UNIQUE (workspace_id, id),
CONSTRAINT uq_public_comments_workspace_id_social_account_id_id UNIQUE (workspace_id,
social_account_id, id),
CONSTRAINT fk_public_comments_workspace_id_social_account_id_socia_0319 FOREIGN
KEY(workspace_id, social_account_id) REFERENCES social_accounts (workspace_id, id),
CONSTRAINT uq_public_comments_social_account_id_external_id UNIQUE (social_account_id,
external_id),
CONSTRAINT uq_public_comments_workspace_id_social_account_id_media_e7ff UNIQUE (workspace_id,
social_account_id, media_id, thread_id, id),
CONSTRAINT fk_public_comments_workspace_id_social_account_id_media_4f1a FOREIGN
KEY(workspace_id, social_account_id, media_id, thread_id) REFERENCES public_threads
(workspace_id, social_account_id, media_id, id),
CONSTRAINT fk_public_comments_workspace_id_social_account_id_media_d1d7 FOREIGN
KEY(workspace_id, social_account_id, media_id, thread_id, parent_id) REFERENCES
public_comments (workspace_id, social_account_id, media_id, thread_id, id),
	CONSTRAINT ck_public_comments_state CHECK (state IN ('unknown','visible','hidden','deleted')),
CONSTRAINT fk_public_comments_workspace_id_workspaces FOREIGN KEY(workspace_id) REFERENCES
workspaces (id) ON DELETE CASCADE
)

;
CREATE INDEX ix_public_comments_workspace_id ON public_comments (workspace_id);

CREATE TABLE sim_public_comments (
	social_account_id UUID NOT NULL,
	external_id TEXT NOT NULL,
	value JSONB,
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
	id UUID NOT NULL,
	workspace_id UUID NOT NULL,
	CONSTRAINT pk_sim_public_comments PRIMARY KEY (id),
	CONSTRAINT uq_sim_public_comments_workspace_id_id UNIQUE (workspace_id, id),
CONSTRAINT uq_sim_public_comments_workspace_id_social_account_id_id UNIQUE (workspace_id,
social_account_id, id),
CONSTRAINT fk_sim_public_comments_workspace_id_social_account_id_s_bf79 FOREIGN
KEY(workspace_id, social_account_id) REFERENCES social_accounts (workspace_id, id),
CONSTRAINT uq_sim_public_comments_social_account_id_external_id UNIQUE (social_account_id,
external_id),
CONSTRAINT fk_sim_public_comments_workspace_id_workspaces FOREIGN KEY(workspace_id) REFERENCES
workspaces (id) ON DELETE CASCADE
)

;
CREATE INDEX ix_sim_public_comments_workspace_id ON sim_public_comments (workspace_id);
ALTER TABLE public_media ADD CONSTRAINT ck_public_media_versions
CHECK(version >= 1 AND provider_version >= 0);
ALTER TABLE public_comments ADD CONSTRAINT ck_public_comments_versions
CHECK(version >= 0 AND provider_version >= 0);
CREATE INDEX ix_public_threads_media_page
ON public_threads(workspace_id,social_account_id,media_id,id);
CREATE INDEX ix_public_comments_thread_page
ON public_comments(workspace_id,social_account_id,thread_id,id);
ALTER TABLE agent_threads ADD COLUMN public_thread_id uuid; ALTER TABLE agent_threads ADD
CONSTRAINT fk_agent_threads_public_thread FOREIGN KEY
(workspace_id,social_account_id,public_thread_id) REFERENCES
public_threads(workspace_id,social_account_id,id);""")


def downgrade() -> None:
    if op.get_bind().scalar(
        sa.text("""
        SELECT EXISTS(SELECT 1 FROM public_media)
            OR EXISTS(SELECT 1 FROM inbound_events WHERE event_type='comment')
    """)
    ):
        raise RuntimeError("0026 downgrade requires explicit public-source archival/erasure")
    op.execute("DELETE FROM inbound_events WHERE event_type = 'comment'")
    op.drop_constraint(op.f("ck_inbound_events_event_type"), "inbound_events", type_="check")
    op.create_check_constraint(
        "event_type",
        "inbound_events",
        "event_type IN ('message','echo','delete','reaction','read','postback','other')",
    )
    op.drop_constraint(op.f("ck_inbound_events_ignore_reason"), "inbound_events", type_="check")
    op.create_check_constraint(
        "ignore_reason",
        "inbound_events",
        "ignore_reason IS NULL OR ignore_reason IN "
        "('UNKNOWN_ACCOUNT','ACCOUNT_DISCONNECTED','UNSUPPORTED_EVENT')",
    )
    op.drop_column("agent_steps", "captured_public_version")
    op.drop_column("agent_threads", "public_thread_id")
    op.drop_table("sim_public_comments")
    op.drop_table("public_comments")
    op.drop_table("public_threads")
    op.drop_table("public_media")
