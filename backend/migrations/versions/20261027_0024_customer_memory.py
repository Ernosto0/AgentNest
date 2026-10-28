"""Customer memory and source generation fences. Revision 0024 follows 0023."""

import sqlalchemy as sa
from alembic import op

revision = "0024"
down_revision = "0023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_messages_workspace_account_id", "messages", ["workspace_id", "social_account_id", "id"]
    )
    op.execute("""
    CREATE TABLE customer_identities (
      id uuid PRIMARY KEY, workspace_id uuid NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
      social_account_id uuid NOT NULL, provider_subject_hash text NOT NULL,
      evidence_kind text NOT NULL,
      generation bigint NOT NULL DEFAULT 0, revision bigint NOT NULL DEFAULT 0,
      source_cutoff timestamptz, created_at timestamptz NOT NULL,
      UNIQUE(workspace_id,id), UNIQUE(workspace_id,social_account_id,id),
      UNIQUE(workspace_id,social_account_id,provider_subject_hash),
      FOREIGN KEY(workspace_id,social_account_id) REFERENCES social_accounts(workspace_id,id),
      CHECK(generation >= 0 AND revision >= 0)
    );
    CREATE TABLE customer_memories (
      id uuid PRIMARY KEY, workspace_id uuid NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
      social_account_id uuid NOT NULL, customer_identity_id uuid NOT NULL,
      topic text NOT NULL, kind text NOT NULL, body text, version bigint NOT NULL DEFAULT 1,
      source_cutoff timestamptz, updated_at timestamptz NOT NULL, expires_at timestamptz NOT NULL,
      UNIQUE(workspace_id,id), UNIQUE(workspace_id,social_account_id,customer_identity_id,id),
      UNIQUE(workspace_id,social_account_id,customer_identity_id,topic),
      FOREIGN KEY(workspace_id,social_account_id,customer_identity_id)
        REFERENCES customer_identities(workspace_id,social_account_id,id),
      CHECK(version >= 1), CHECK(kind IN ('preference','customer_claim','open_goal')),
      CHECK(topic IN ('size','schedule','service','language','contact'))
    );
    CREATE TABLE customer_memory_versions (
      id uuid PRIMARY KEY, workspace_id uuid NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
      social_account_id uuid NOT NULL, customer_identity_id uuid NOT NULL, memory_id uuid NOT NULL,
      version bigint NOT NULL, body text, provenance text NOT NULL,
      author_user_id uuid REFERENCES users(id), created_at timestamptz NOT NULL,
      UNIQUE(workspace_id,id), UNIQUE(workspace_id,memory_id,version),
      FOREIGN KEY(workspace_id,social_account_id,customer_identity_id,memory_id)
        REFERENCES customer_memories(workspace_id,social_account_id,customer_identity_id,id)
    );
    CREATE TABLE customer_memory_sources (
      id uuid PRIMARY KEY, workspace_id uuid NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
      social_account_id uuid NOT NULL, customer_identity_id uuid NOT NULL, memory_id uuid NOT NULL,
      message_id uuid, source_key text NOT NULL, memory_version bigint NOT NULL,
      removed boolean NOT NULL DEFAULT false, observed_at timestamptz NOT NULL,
      UNIQUE(workspace_id,id), UNIQUE(workspace_id,memory_id,source_key),
      FOREIGN KEY(workspace_id,social_account_id,customer_identity_id,memory_id)
        REFERENCES customer_memories(workspace_id,social_account_id,customer_identity_id,id),
      FOREIGN KEY(workspace_id,social_account_id,message_id)
        REFERENCES messages(workspace_id,social_account_id,id)
    );
    CREATE TABLE customer_summary_versions (
      id uuid PRIMARY KEY, workspace_id uuid NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
      social_account_id uuid NOT NULL, customer_identity_id uuid NOT NULL, thread_id uuid NOT NULL,
      version bigint NOT NULL, generation bigint NOT NULL, revision bigint NOT NULL,
      source_cursor bigint NOT NULL, query_hash text NOT NULL, body text,
      created_at timestamptz NOT NULL,
      UNIQUE(workspace_id,id), UNIQUE(workspace_id,thread_id,version),
      FOREIGN KEY(workspace_id,social_account_id,customer_identity_id)
        REFERENCES customer_identities(workspace_id,social_account_id,id),
      FOREIGN KEY(workspace_id,social_account_id,thread_id)
        REFERENCES agent_threads(workspace_id,social_account_id,id)
    );
    CREATE INDEX ix_customer_memories_expiry ON customer_memories(expires_at)
      WHERE body IS NOT NULL;
    CREATE TABLE customer_source_fences (
      id uuid PRIMARY KEY, workspace_id uuid NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
      social_account_id uuid NOT NULL, customer_identity_id uuid NOT NULL, source_key text NOT NULL,
      UNIQUE(workspace_id,id),
      UNIQUE(workspace_id,social_account_id,customer_identity_id,source_key),
      FOREIGN KEY(workspace_id,social_account_id,customer_identity_id)
        REFERENCES customer_identities(workspace_id,social_account_id,id)
    );
    CREATE INDEX ix_memory_sources_message
      ON customer_memory_sources(workspace_id,social_account_id,message_id);
    """)
    op.create_foreign_key(
        "fk_agent_threads_customer_identity",
        "agent_threads",
        "customer_identities",
        ["workspace_id", "social_account_id", "customer_identity_id"],
        ["workspace_id", "social_account_id", "id"],
    )
    for table in (
        "customer_identities",
        "customer_memories",
        "customer_memory_versions",
        "customer_memory_sources",
        "customer_summary_versions",
        "customer_source_fences",
    ):
        op.create_index(f"ix_{table}_workspace_id", table, ["workspace_id"])


def downgrade() -> None:
    if op.get_bind().scalar(sa.text("SELECT EXISTS(SELECT 1 FROM customer_identities)")):
        raise RuntimeError("refusing to discard customer memory privacy evidence")
    op.drop_constraint("fk_agent_threads_customer_identity", "agent_threads", type_="foreignkey")
    for table in (
        "customer_source_fences",
        "customer_summary_versions",
        "customer_memory_sources",
        "customer_memory_versions",
        "customer_memories",
        "customer_identities",
    ):
        op.drop_table(table)
    op.drop_constraint("uq_messages_workspace_account_id", "messages", type_="unique")
