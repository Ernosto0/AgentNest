"""Private owner questions and versioned information answers. Revision 0025."""

import sqlalchemy as sa
from alembic import op

revision = "0025"
down_revision = "0024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    CREATE TABLE owner_questions (
      id uuid PRIMARY KEY, workspace_id uuid NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
      social_account_id uuid NOT NULL, thread_id uuid NOT NULL, session_id uuid NOT NULL,
      customer_identity_id uuid NOT NULL, source_message_id uuid, source_cursor bigint NOT NULL,
      source_hash text NOT NULL, knowledge_fence text NOT NULL,
      ownership_generation bigint NOT NULL, deletion_generation bigint NOT NULL,
      required_info text NOT NULL, visibility text NOT NULL, continuation_key text NOT NULL,
      body text, state text NOT NULL DEFAULT 'pending', version bigint NOT NULL DEFAULT 1,
      answer_id uuid, holding_action_id uuid, created_at timestamptz NOT NULL,
      expires_at timestamptz NOT NULL,
      UNIQUE(workspace_id,id), UNIQUE(workspace_id,social_account_id,thread_id,id),
      UNIQUE(workspace_id,continuation_key),
      FOREIGN KEY(workspace_id,social_account_id,thread_id)
        REFERENCES agent_threads(workspace_id,social_account_id,id),
      FOREIGN KEY(workspace_id,thread_id,session_id)
        REFERENCES agent_sessions(workspace_id,thread_id,id),
      FOREIGN KEY(workspace_id,social_account_id,customer_identity_id)
        REFERENCES customer_identities(workspace_id,social_account_id,id),
      FOREIGN KEY(workspace_id,social_account_id,source_message_id)
        REFERENCES messages(workspace_id,social_account_id,id),
      CHECK(state IN ('pending','answered','expired','cancelled')),
      CHECK(visibility IN ('customer_reply','private_business')),
      CHECK(version >= 1 AND source_cursor >= 1)
    );
    CREATE TABLE owner_answers (
      id uuid PRIMARY KEY, workspace_id uuid NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
      social_account_id uuid NOT NULL, thread_id uuid NOT NULL, question_id uuid NOT NULL,
      version bigint NOT NULL, kind text NOT NULL, body text,
      author_user_id uuid NOT NULL REFERENCES users(id), author_role text NOT NULL,
      client_request_id uuid NOT NULL, request_hash text NOT NULL, candidate_id uuid,
      created_at timestamptz NOT NULL, expires_at timestamptz NOT NULL,
      UNIQUE(workspace_id,id), UNIQUE(workspace_id,question_id,id),
      UNIQUE(workspace_id,question_id,client_request_id),
      UNIQUE(workspace_id,question_id,version),
      FOREIGN KEY(workspace_id,social_account_id,thread_id,question_id)
        REFERENCES owner_questions(workspace_id,social_account_id,thread_id,id),
      CHECK(kind IN ('answer','proposal','cancel')), CHECK(version >= 1)
    );
    CREATE INDEX ix_owner_questions_recovery ON owner_questions(state,expires_at);
    CREATE INDEX ix_owner_questions_scope ON owner_questions(workspace_id,social_account_id,id);
    CREATE INDEX ix_owner_answers_question ON owner_answers(workspace_id,question_id);
    """)
    op.add_column("fact_candidates", sa.Column("owner_answer_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_owner_questions_answer",
        "owner_questions",
        "owner_answers",
        ["workspace_id", "id", "answer_id"],
        ["workspace_id", "question_id", "id"],
    )
    op.create_foreign_key(
        "fk_owner_questions_holding_action",
        "owner_questions",
        "agent_actions",
        ["workspace_id", "social_account_id", "holding_action_id"],
        ["workspace_id", "social_account_id", "id"],
    )
    op.create_foreign_key(
        "fk_owner_answers_candidate",
        "owner_answers",
        "fact_candidates",
        ["workspace_id", "candidate_id"],
        ["workspace_id", "id"],
    )
    op.create_foreign_key(
        "fk_fact_candidates_owner_answer",
        "fact_candidates",
        "owner_answers",
        ["workspace_id", "owner_answer_id"],
        ["workspace_id", "id"],
    )
    op.drop_constraint(op.f("ck_fact_candidates_source_type"), "fact_candidates", type_="check")
    op.create_check_constraint(
        op.f("ck_fact_candidates_source_type"),
        "fact_candidates",
        "source_type IN "
        "('staff_proposal','pasted_text','instagram_profile','website','owner_answer')",
    )


def downgrade() -> None:
    if op.get_bind().scalar(sa.text("SELECT EXISTS(SELECT 1 FROM owner_questions)")):
        raise RuntimeError("refusing to discard owner question evidence")
    op.drop_constraint("fk_owner_questions_answer", "owner_questions", type_="foreignkey")
    op.drop_constraint("fk_owner_questions_holding_action", "owner_questions", type_="foreignkey")
    op.drop_constraint("fk_owner_answers_candidate", "owner_answers", type_="foreignkey")
    op.drop_constraint("fk_fact_candidates_owner_answer", "fact_candidates", type_="foreignkey")
    op.drop_column("fact_candidates", "owner_answer_id")
    op.drop_constraint(op.f("ck_fact_candidates_source_type"), "fact_candidates", type_="check")
    op.create_check_constraint(
        op.f("ck_fact_candidates_source_type"),
        "fact_candidates",
        "source_type IN ('staff_proposal','pasted_text','instagram_profile','website')",
    )
    op.drop_table("owner_answers")
    op.drop_table("owner_questions")
