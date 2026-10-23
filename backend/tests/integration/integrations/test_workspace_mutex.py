"""The account mutex excludes peers without deadlocking tenant foreign-key inserts."""

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import OperationalError

from app.integrations.instagram.models import SocialAccount
from app.operations.accounts import lock_workspace
from tests.factories import create_workspace


@pytest.mark.commits
def test_workspace_mutex_excludes_other_mutex_but_allows_tenant_fk_insert(session_factory):
    with session_factory() as session:
        workspace_id = create_workspace(session).id
        session.commit()

    with session_factory() as owner, session_factory() as contender:
        lock_workspace(owner, workspace_id)
        contender.execute(text("SET LOCAL lock_timeout = '150ms'"))
        with pytest.raises(OperationalError) as exc:
            lock_workspace(contender, workspace_id)
        assert exc.value.orig.sqlstate == "55P03"
        contender.rollback()

        # Owner still holds its mutex. This FK insert takes KEY SHARE on Workspace.
        assert owner.in_transaction()
        contender.execute(text("SET LOCAL lock_timeout = '150ms'"))
        contender.add(
            SocialAccount(
                workspace_id=workspace_id,
                provider_kind="mock",
                external_account_id="concurrent-tenant-insert",
                status="connected",
            )
        )
        contender.commit()
        assert (
            owner.scalar(
                select(SocialAccount.id).where(
                    SocialAccount.workspace_id == workspace_id,
                )
            )
            is not None
        )
        owner.rollback()
