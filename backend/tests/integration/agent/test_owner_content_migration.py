"""The additive content-intent migration preserves tasks and refuses evidence loss."""

import uuid

import pytest
from alembic import command
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.agent import owner_tasks
from app.agent.models import AccountAgent, AgentAction, AgentSession, OwnerTask
from app.integrations.instagram.models import SocialAccount
from tests.factories import add_member, create_user, create_workspace, knowledge_ctx
from tests.integration.agent.test_migration import prior_schema

__all__ = ["prior_schema"]


def test_populated_task_upgrade_and_evidence_guarded_downgrade(prior_schema, clock):
    config, engine = prior_schema
    command.upgrade(config, "head")
    with Session(engine, expire_on_commit=False) as db:
        workspace = create_workspace(db)
        user = create_user(db)
        add_member(db, workspace, user)
        social = SocialAccount(
            workspace_id=workspace.id, provider_kind="mock", external_account_id=uuid.uuid4().hex
        )
        db.add(social)
        db.flush()
        account = db.scalar(select(AccountAgent).where(AccountAgent.social_account_id == social.id))
        account.controller_mode, account.state = "agent", "active"
        task = owner_tasks.submit(
            db,
            clock,
            knowledge_ctx(workspace, user, "owner"),
            social.id,
            "Keep this task",
            uuid.uuid4(),
        )
        assert task.read_refs == {} and task.answers == []
        goal = AgentSession(
            workspace_id=workspace.id,
            thread_id=task.thread_id,
            initiating_event_cursor=1,
            goal_key=str(task.id),
        )
        db.add(goal)
        db.flush()
        action = AgentAction(
            workspace_id=workspace.id,
            social_account_id=social.id,
            thread_id=task.thread_id,
            session_id=goal.id,
            intent_key="prepare",
            action_type="content.prepare",
            target_ref=str(task.id),
            payload_hash="a" * 64,
            initiating_cursor=1,
            content_intent={"request": "evidence"},
        )
        db.add(action)
        db.commit()
        with pytest.raises(RuntimeError, match="content intent archival"):
            command.downgrade(config, "0029")
        db.delete(action)
        task.clarification = "Which image?"
        db.commit()
        with pytest.raises(RuntimeError, match="owner continuation archival"):
            command.downgrade(config, "0029")
        task.clarification = None
        db.commit()
        command.downgrade(config, "0029")
        command.upgrade(config, "0030")
        db.expire_all()
        restored = db.get(OwnerTask, task.id)
        assert restored.request_text == "Keep this task"
        assert restored.read_refs == {} and restored.answers == []
        assert db.scalar(text("SELECT version_num FROM alembic_version")) == "0030"
