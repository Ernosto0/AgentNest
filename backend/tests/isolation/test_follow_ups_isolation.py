import uuid
from datetime import timedelta

import pytest
from sqlalchemy import insert, select, text, update
from sqlalchemy.exc import IntegrityError, ProgrammingError
from sqlalchemy.orm import Session

from app.core.clock import FrozenClock
from app.core.db import clear_tenant_context, set_tenant_context
from app.inbox import follow_up
from app.inbox.models import ConversationFollowUp
from app.inbox.payloads import FollowUpCheckPayload
from app.integrations.instagram.models import SocialAccount
from tests.factories import knowledge_ctx
from tests.helpers.reporting import Builder
from tests.isolation.conftest import TwoWorkspaces
from tests.isolation.test_delegation_suggestions_isolation import as_role


def seed(session: Session, world: TwoWorkspaces) -> ConversationFollowUp:
    set_tenant_context(session, world.b.id)
    account = session.scalars(
        select(SocialAccount).where(SocialAccount.workspace_id == world.b.id)
    ).first()
    assert account is not None
    builder = Builder(session, world.b, world.b_owner, simulated=False, account=account)
    now = FrozenClock().now()
    conversation = builder.conversation(now)
    inbound = builder.message(conversation, "inbound", now)
    answer = builder.draft(
        conversation, inbound, source="ai", decision="approval_required", created_at=now
    )
    row = ConversationFollowUp(
        workspace_id=world.b.id,
        conversation_id=conversation.id,
        answer_draft_id=answer.id,
        covers_through_message_id=inbound.id,
        answered_at=now,
        due_at=now + timedelta(hours=6),
        status="scheduled",
    )
    session.add(row)
    session.commit()
    return row


def test_forced_rls_and_policy(db_session: Session) -> None:
    assert db_session.execute(
        text(
            "SELECT relrowsecurity, relforcerowsecurity FROM pg_class "
            "WHERE relname='conversation_follow_ups' "
            "AND relnamespace='public'::regnamespace"
        )
    ).one() == (True, True)
    assert (
        db_session.scalar(
            text(
                "SELECT count(*) FROM pg_policies WHERE tablename='conversation_follow_ups' "
                "AND policyname='tenant_isolation_policy'"
            )
        )
        == 1
    )


@pytest.mark.parametrize("role", ["agentnest_app", "agentnest_worker"])
def test_runtime_tenant_isolation(
    db_session: Session, two_workspaces: TwoWorkspaces, role: str
) -> None:
    row = seed(db_session, two_workspaces)
    row_id, answer_id = row.id, row.answer_draft_id
    values = {
        column.name: getattr(row, column.name) for column in ConversationFollowUp.__table__.columns
    }
    values["id"] = uuid.uuid4()
    db_session.expunge_all()
    clear_tenant_context(db_session)
    with as_role(db_session, role):
        assert db_session.scalars(select(ConversationFollowUp)).all() == []
    set_tenant_context(db_session, two_workspaces.a.id)
    with as_role(db_session, role):
        assert (
            db_session.scalar(
                select(ConversationFollowUp.id).where(ConversationFollowUp.id == row_id)
            )
            is None
        )
        result = db_session.execute(
            update(ConversationFollowUp)
            .where(ConversationFollowUp.id == row_id)
            .values(status="skipped", reason_code="TEST")
        )
        assert result.rowcount == 0
        with pytest.raises(ProgrammingError) as refused, db_session.begin_nested():
            db_session.execute(insert(ConversationFollowUp).values(**values))
        assert refused.value.orig.sqlstate == "42501"
    # The same malicious payload must be a no-op even with a privileged test connection.
    follow_up.check(
        db_session,
        FrozenClock(),
        knowledge_ctx(two_workspaces.a, two_workspaces.a_owner, "owner"),
        FollowUpCheckPayload(follow_up_id=row_id, answer_draft_id=answer_id),
    )
    set_tenant_context(db_session, two_workspaces.b.id)
    assert db_session.get(ConversationFollowUp, row_id).status == "scheduled"


def test_composite_foreign_keys(db_session: Session, two_workspaces: TwoWorkspaces) -> None:
    row = seed(db_session, two_workspaces)
    values = {
        column.name: getattr(row, column.name) for column in ConversationFollowUp.__table__.columns
    }
    values.update(id=uuid.uuid4(), workspace_id=two_workspaces.a.id)
    set_tenant_context(db_session, two_workspaces.a.id)
    with pytest.raises(IntegrityError), db_session.begin_nested():
        db_session.execute(insert(ConversationFollowUp).values(**values))


def test_foreign_settings_are_404(two_workspaces: TwoWorkspaces) -> None:
    world = two_workspaces
    url = f"/api/v1/workspaces/{world.b.id}/follow-up-settings"
    assert world.a_client.get(url).status_code == 404
    assert (
        world.a_client.put(
            url,
            headers=world.a_headers,
            json={"enabled": True, "hours": 6, "text": {"tr": "", "en": ""}},
        ).status_code
        == 404
    )
