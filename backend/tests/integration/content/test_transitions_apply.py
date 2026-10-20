"""``content.transitions.apply``: the conditional update and its audit entry (INV-12)."""

import pytest
from sqlalchemy import select, update

from app.audit.models import AuditLog
from app.content import transitions
from app.content.models import ContentItem
from app.core.errors import AppError
from tests.helpers.content import make_item
from tests.helpers.env import Env


def audits(env: Env, item: ContentItem) -> list[AuditLog]:
    return list(
        env.session.scalars(
            select(AuditLog)
            .where(AuditLog.resource_id == item.id, AuditLog.resource_type == "content_item")
            .order_by(AuditLog.occurred_at, AuditLog.id)
        )
    )


def test_a_transition_changes_the_status_and_writes_one_audit_entry(env: Env) -> None:
    item = make_item(env, status="scheduled")
    env.clock.advance(minutes=5)

    transitions.apply(
        env.session, env.clock, env.ctx(env.owner), item, "hold", reason="FACT_CHANGED"
    )

    assert (item.status, item.hold_reason) == ("on_hold", "FACT_CHANGED")
    assert item.updated_at == env.clock.now()
    (entry,) = audits(env, item)
    assert entry.action == "content.on_hold"
    assert entry.metadata_["from"] == "scheduled"
    assert entry.metadata_["event"] == "hold"
    assert entry.metadata_["reason"] == "FACT_CHANGED"
    assert entry.workspace_id == env.workspace.id


def test_a_status_that_changed_underneath_is_a_conflict(env: Env) -> None:
    """The update is conditional on the expected status: a lost update cannot happen."""
    item = make_item(env, status="scheduled")
    env.session.execute(update(ContentItem).where(ContentItem.id == item.id).values(status="draft"))

    with pytest.raises(AppError) as error:
        transitions.apply(env.session, env.clock, env.ctx(env.owner), item, "hold", reason="X")

    assert error.value.code == "CONFLICT_STATE"
    assert audits(env, item) == []  # nothing was audited for a transition that did not happen


def test_an_event_the_table_does_not_know_changes_nothing(env: Env) -> None:
    item = make_item(env, status="published")
    with pytest.raises(AppError) as error:
        transitions.apply(env.session, env.clock, env.ctx(env.owner), item, "edit", caption="x")
    assert error.value.code == "CONFLICT_STATE"
    env.session.refresh(item)
    assert (item.status, item.caption, item.version) == ("published", None, 1)
    assert audits(env, item) == []


def test_edit_and_reapprove_bump_the_version_and_clear_the_old_reasons(env: Env) -> None:
    item = make_item(
        env, status="on_hold", hold_reason="FACT_CHANGED", last_error_code="X", rejection_note="n"
    )
    ctx = env.ctx(env.owner)

    env.clock.advance(seconds=1)
    transitions.apply(env.session, env.clock, ctx, item, "reapprove")
    assert (item.status, item.version, item.hold_reason) == ("scheduled", 2, None)
    assert item.last_error_code == "X"  # a re-approval does not touch the rest

    env.clock.advance(seconds=1)
    transitions.apply(env.session, env.clock, ctx, item, "hold", reason="ACCOUNT_UNAVAILABLE")
    env.clock.advance(seconds=1)
    transitions.apply(env.session, env.clock, ctx, item, "edit", caption="Yeni")
    assert (item.status, item.version, item.caption) == ("draft", 3, "Yeni")
    assert (item.hold_reason, item.last_error_code, item.rejection_note) == (None, None, None)
    assert [a.action for a in audits(env, item)] == [
        "content.scheduled",
        "content.on_hold",
        "content.updated",
    ]


def test_a_failure_records_its_error_code_and_an_expiry_its_reason(env: Env) -> None:
    ctx = env.ctx(env.owner)
    failing = make_item(env, status="publishing")
    transitions.apply(env.session, env.clock, ctx, failing, "fail", reason="MEDIA_REJECTED")
    assert (failing.status, failing.last_error_code) == ("failed", "MEDIA_REJECTED")

    waiting = make_item(env, status="pending_approval")
    transitions.apply(env.session, env.clock, ctx, waiting, "expire", reason="APPROVAL_EXPIRED")
    assert (waiting.status, waiting.hold_reason) == ("draft", "APPROVAL_EXPIRED")


def test_columns_that_a_transition_must_not_set_are_refused(env: Env) -> None:
    item = make_item(env, status="draft")
    for column in ("status", "version", "workspace_id", "created_by_user_id", "id"):
        with pytest.raises(ValueError, match="not settable"):
            transitions.apply(
                env.session, env.clock, env.ctx(env.owner), item, "cancel", **{column: 1}
            )
    assert item.status == "draft"


def test_a_transition_in_another_workspace_context_finds_no_row(env: Env) -> None:
    """The update carries the workspace id: a foreign context cannot move the item (INV-01)."""
    from tests.factories import knowledge_ctx, workspace_with_members

    other, users = workspace_with_members(env.session, name="Başka")
    item = make_item(env, status="draft")
    with pytest.raises(AppError) as error:
        transitions.apply(
            env.session, env.clock, knowledge_ctx(other, users["owner"], "owner"), item, "cancel"
        )
    assert error.value.code == "CONFLICT_STATE"
    env.session.refresh(item)
    assert item.status == "draft"
