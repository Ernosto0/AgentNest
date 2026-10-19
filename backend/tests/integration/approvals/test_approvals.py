"""Approvals: request, decide, expire, cancel, execute (workflows.md §D, ADR-014)."""

import uuid
from datetime import timedelta
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.approvals import service
from app.approvals.jobs import ExpireApprovalsPayload, expire_approvals
from app.approvals.models import Approval
from app.audit import service as audit
from app.core.canonical import payload_hash
from app.core.errors import AppError
from app.jobs.registry import JobContext
from app.notifications.models import Notification
from tests.helpers.env import Env, Role
from tests.integration.approvals.conftest import FakeSubject

PAYLOAD = {"fact_id": str(uuid.UUID(int=7)), "from_version": 1, "new_value": {"amount": "7000.00"}}
SUMMARY = {"label": "Aylık üyelik", "old_formatted": "6.000 ₺", "new_formatted": "7.000 ₺"}


def request_approval(
    env: Env,
    *,
    requester: Role | None = None,
    kind: str = "confirmation",
    subject_id: uuid.UUID | None = None,
    expires_in: timedelta = timedelta(minutes=30),
    required_permission: str = "knowledge.verify",
    execute_before: Any = None,
    payload: dict[str, Any] | None = None,
) -> Approval:
    approval = service.request(
        env.session,
        env.clock,
        env.ctx(requester or env.owner),
        kind=kind,
        action="command.update_fact",
        subject_type="owner_command",
        subject_id=subject_id or uuid.uuid4(),
        subject_version=1,
        payload=payload or PAYLOAD,
        summary=SUMMARY,
        required_permission=required_permission,
        expires_at=env.clock.now() + expires_in,
        execute_before=execute_before,
    )
    env.session.commit()
    return approval


def decide(env: Env, role: Role, approval: Approval, decision: str = "approve", **kw: Any) -> Any:
    return service.decide(
        env.session,
        env.clock,
        env.ctx(role),
        approval.id,
        decision=decision,
        payload_hash=kw.pop("payload_hash", approval.payload_hash),
        **kw,
    )


def error_code(env: Env, role: Role, approval: Approval, **kw: Any) -> str:
    with pytest.raises(AppError) as info:
        decide(env, role, approval, **kw)
    return info.value.code


def audit_actions(env: Env) -> list[str]:
    return [e.action for e in audit.list_entries(env.session, workspace_id=env.workspace.id)]


# --- request -------------------------------------------------------------------------------


def test_request_binds_the_exact_payload_and_audits(env: Env, subject: FakeSubject) -> None:
    approval = request_approval(env)
    assert approval.status == "pending" and approval.kind == "confirmation"
    assert approval.payload_hash == payload_hash(PAYLOAD)
    assert approval.requested_by_actor_id == str(env.owner.user.id)
    assert approval.summary == SUMMARY
    assert "approval.requested" in audit_actions(env)


def test_a_different_payload_has_a_different_hash(env: Env, subject: FakeSubject) -> None:
    first = request_approval(env)
    second = request_approval(env, payload={**PAYLOAD, "new_value": {"amount": "7500.00"}})
    assert first.payload_hash != second.payload_hash


def test_only_one_pending_approval_per_subject(env: Env, subject: FakeSubject) -> None:
    subject_id = uuid.uuid4()
    request_approval(env, subject_id=subject_id)
    with pytest.raises(AppError) as info:
        request_approval(env, subject_id=subject_id)
    assert info.value.code == "CONFLICT_STATE"


def test_a_confirmation_notifies_nobody(env: Env, subject: FakeSubject) -> None:
    request_approval(env)
    assert env.session.scalars(select(Notification)).all() == []


def test_an_authorization_notifies_those_who_may_decide_it(env: Env, subject: FakeSubject) -> None:
    approval = request_approval(env, kind="authorization", requester=env.staff)
    notified = {n.recipient_user_id for n in env.session.scalars(select(Notification))}
    assert notified == {env.owner.user.id, env.manager.user.id}  # not staff
    note = env.session.scalars(select(Notification)).first()
    assert note is not None and note.type == "approval.requested"
    assert note.subject_id == approval.id and note.dedup_key == f"approval:{approval.id}"


# --- decide: success -----------------------------------------------------------------------


def test_approve_sets_the_decision_and_runs_the_callback_once(
    env: Env, subject: FakeSubject
) -> None:
    approval = request_approval(env)
    decided = decide(env, env.owner, approval, note="ok")
    assert decided.status == "approved"
    assert decided.decided_by_user_id == env.owner.user.id
    assert decided.decided_at == env.clock.now()
    assert (decided.decision_channel, decided.decision_note) == ("web", "ok")
    assert subject.decided == [("approved", approval.id)]
    assert "approval.approved" in audit_actions(env)


def test_reject_runs_the_callback_with_rejected(env: Env, subject: FakeSubject) -> None:
    approval = request_approval(env)
    assert decide(env, env.manager, approval, "reject").status == "rejected"
    assert subject.decided == [("rejected", approval.id)]
    assert "approval.rejected" in audit_actions(env)


def test_a_manager_may_decide_an_owners_confirmation(env: Env, subject: FakeSubject) -> None:
    approval = request_approval(env, requester=env.owner)
    assert decide(env, env.manager, approval).status == "approved"


# --- decide: refusals ----------------------------------------------------------------------


def test_a_wrong_payload_hash_is_stale_and_changes_nothing(env: Env, subject: FakeSubject) -> None:
    approval = request_approval(env)
    assert error_code(env, env.owner, approval, payload_hash="0" * 64) == "APPROVAL_STALE"
    env.session.refresh(approval)
    assert approval.status == "pending" and subject.decided == []


def test_a_changed_subject_version_makes_the_approval_stale(env: Env, subject: FakeSubject) -> None:
    approval = request_approval(env)
    subject.version = 2  # the subject was edited after the approval was requested
    assert error_code(env, env.owner, approval) == "APPROVAL_STALE"
    assert subject.decided == []


def test_a_double_decision_is_a_conflict_and_has_no_second_effect(
    env: Env, subject: FakeSubject
) -> None:
    approval = request_approval(env)
    decide(env, env.owner, approval)
    assert error_code(env, env.owner, approval) == "APPROVAL_ALREADY_DECIDED"
    assert error_code(env, env.manager, approval, decision="reject") == "APPROVAL_ALREADY_DECIDED"
    assert len(subject.decided) == 1


def test_an_expired_approval_is_marked_expired_and_refused(env: Env, subject: FakeSubject) -> None:
    approval = request_approval(env, requester=env.manager)
    env.clock.advance(minutes=31)
    assert error_code(env, env.owner, approval) == "APPROVAL_EXPIRED"
    env.session.refresh(approval)
    assert approval.status == "expired"  # the expiry itself was saved even though we answered 409
    assert subject.decided == [("expired", approval.id)]
    note = env.session.scalars(select(Notification)).one()
    assert (note.type, note.recipient_user_id) == ("approval.expired", env.manager.user.id)
    assert "approval.expired" in audit_actions(env)


def test_staff_cannot_decide_an_authorization(env: Env, subject: FakeSubject) -> None:
    approval = request_approval(env, kind="authorization", requester=env.owner)
    assert error_code(env, env.staff, approval) == "FORBIDDEN"
    assert subject.decided == []


def test_staff_cannot_decide_someone_elses_confirmation(env: Env, subject: FakeSubject) -> None:
    approval = request_approval(env, requester=env.owner)
    assert error_code(env, env.staff, approval) == "FORBIDDEN"


def test_staff_may_decide_their_own_confirmation(env: Env, subject: FakeSubject) -> None:
    approval = request_approval(env, requester=env.staff)
    assert decide(env, env.staff, approval).status == "approved"


def test_a_system_actor_can_never_approve(env: Env, subject: FakeSubject) -> None:
    from tests.factories import knowledge_ctx

    approval = request_approval(env)
    system = knowledge_ctx(env.workspace)  # no user: the system actor
    with pytest.raises(AppError) as info:
        service.decide(
            env.session, env.clock, system, approval.id, decision="approve",
            payload_hash=approval.payload_hash,
        )  # fmt: skip
    assert info.value.code == "FORBIDDEN"


def test_an_unknown_decision_value_is_a_validation_error(env: Env, subject: FakeSubject) -> None:
    approval = request_approval(env)
    assert error_code(env, env.owner, approval, decision="yes") == "VALIDATION_FAILED"


def test_a_failing_callback_rolls_the_whole_decision_back(env: Env, subject: FakeSubject) -> None:
    approval = request_approval(env)
    subject.fail = True
    with pytest.raises(RuntimeError):
        decide(env, env.owner, approval)
    env.session.expire_all()
    stored = env.session.get(Approval, approval.id)
    assert stored is not None and stored.status == "pending"  # no half-state
    assert stored.decided_by_user_id is None and stored.decided_at is None
    assert "approval.approved" not in audit_actions(env)
    subject.fail = False
    assert decide(env, env.owner, stored).status == "approved"  # still decidable afterwards


# --- cancel --------------------------------------------------------------------------------


def test_cancel_for_subject_cancels_the_pending_approval_with_a_reason(
    env: Env, subject: FakeSubject
) -> None:
    subject_id = uuid.uuid4()
    approval = request_approval(env, subject_id=subject_id)
    assert service.cancel_for_subject(
        env.session, env.clock, env.ctx(env.owner), "owner_command", subject_id, "SUBJECT_EDITED"
    )
    env.session.commit()
    env.session.refresh(approval)
    assert (approval.status, approval.cancel_reason) == ("cancelled", "SUBJECT_EDITED")
    assert error_code(env, env.owner, approval) == "APPROVAL_ALREADY_DECIDED"
    assert "approval.cancelled" in audit_actions(env)


def test_cancel_for_subject_without_a_pending_approval_is_a_no_op(
    env: Env, subject: FakeSubject
) -> None:
    assert not service.cancel_for_subject(
        env.session, env.clock, env.ctx(env.owner), "owner_command", uuid.uuid4(), "X"
    )


def test_a_new_approval_is_possible_after_cancelling(env: Env, subject: FakeSubject) -> None:
    subject_id = uuid.uuid4()
    request_approval(env, subject_id=subject_id)
    service.cancel_for_subject(
        env.session, env.clock, env.ctx(env.owner), "owner_command", subject_id, "SUPERSEDED"
    )
    env.session.commit()
    assert request_approval(env, subject_id=subject_id).status == "pending"


# --- execution eligibility -----------------------------------------------------------------


def test_assert_executable_requires_an_approved_matching_unexpired_approval(
    env: Env, subject: FakeSubject
) -> None:
    approval = request_approval(env, execute_before=env.clock.now() + timedelta(hours=1))
    ctx = env.ctx(env.owner)

    with pytest.raises(AppError) as info:  # pending is not executable
        service.assert_executable(env.session, env.clock, ctx, approval.id, 1)
    assert info.value.code == "CONFLICT_STATE"

    decide(env, env.owner, approval)
    operation = uuid.uuid4()
    ok = service.assert_executable(
        env.session, env.clock, ctx, approval.id, 1, operation_id=operation
    )
    assert ok.operation_id == operation

    with pytest.raises(AppError) as stale:  # the subject changed after approval
        service.assert_executable(env.session, env.clock, ctx, approval.id, 2)
    assert stale.value.code == "APPROVAL_STALE"

    with pytest.raises(AppError) as consumed:  # one approval authorises one operation
        service.assert_executable(
            env.session, env.clock, ctx, approval.id, 1, operation_id=uuid.uuid4()
        )
    assert consumed.value.code == "CONFLICT_STATE"
    # a retry of the *same* operation stays covered
    service.assert_executable(env.session, env.clock, ctx, approval.id, 1, operation_id=operation)

    env.clock.advance(hours=2)
    with pytest.raises(AppError) as late:
        service.assert_executable(env.session, env.clock, ctx, approval.id, 1)
    assert late.value.code == "APPROVAL_EXPIRED"


@pytest.mark.parametrize("final", ["reject", "cancel", "expire"])
def test_only_an_approved_approval_is_executable(
    env: Env, subject: FakeSubject, final: str
) -> None:
    subject_id = uuid.uuid4()
    approval = request_approval(env, subject_id=subject_id)
    if final == "reject":
        decide(env, env.owner, approval, "reject")
    elif final == "cancel":
        service.cancel_for_subject(
            env.session, env.clock, env.ctx(env.owner), "owner_command", subject_id, "X"
        )
    else:
        env.clock.advance(hours=1)
        service.expire_due_in_workspace(env.session, env.clock, env.ctx(env.owner))
    with pytest.raises(AppError) as info:
        service.assert_executable(env.session, env.clock, env.ctx(env.owner), approval.id, 1)
    assert info.value.code == "CONFLICT_STATE"


# --- expiry sweep --------------------------------------------------------------------------


def _job(factory: sessionmaker[Session], env: Env) -> JobContext:
    return JobContext(
        job_id=uuid.uuid4(),
        job_type="expire_approvals",
        workspace_id=None,
        correlation_id=None,
        payload=ExpireApprovalsPayload(),
        attempt=1,
        max_attempts=1,
        session_factory=factory,
        clock=env.clock,
        _heartbeat=lambda: None,
    )


def test_the_sweep_expires_only_due_approvals_and_notifies(
    env: Env, subject: FakeSubject, shared_session_factory: sessionmaker[Session]
) -> None:
    due = request_approval(env, requester=env.manager, expires_in=timedelta(minutes=5))
    later = request_approval(env, requester=env.manager, expires_in=timedelta(minutes=50))
    env.clock.advance(minutes=10)

    expire_approvals(_job(shared_session_factory, env))
    env.session.expire_all()

    assert (
        env.session.get(Approval, due.id).status,
        env.session.get(Approval, later.id).status,
    ) == (  # type: ignore[union-attr]
        "expired",
        "pending",
    )
    assert subject.decided == [("expired", due.id)]


def test_one_failing_callback_does_not_block_the_other_expiries(
    env: Env, subject: FakeSubject, shared_session_factory: sessionmaker[Session]
) -> None:
    first = request_approval(env, expires_in=timedelta(minutes=1))
    second = request_approval(env, expires_in=timedelta(minutes=2))
    env.clock.advance(minutes=10)
    original = subject.on_decided
    calls = []

    def flaky(session: Any, clock: Any, ctx: Any, approval: Approval) -> None:
        calls.append(approval.id)
        if len(calls) == 1:
            raise RuntimeError("boom")
        original(session, clock, ctx, approval)

    subject.on_decided = flaky  # type: ignore[method-assign]
    from app.approvals import callbacks

    with callbacks.callbacks_snapshot(clear=True):
        callbacks.register(
            "owner_command", flaky, current_version=lambda *_: 1, status_of=lambda *_: "x"
        )
        expire_approvals(_job(shared_session_factory, env))
    env.session.expire_all()
    statuses = sorted(
        s
        for (s,) in env.session.execute(
            select(Approval.status).where(Approval.id.in_([first.id, second.id]))
        )
    )
    assert statuses == ["expired", "pending"]  # the failed one stays pending for the next sweep


def test_the_sweep_ignores_approvals_decided_in_the_meantime(
    env: Env, subject: FakeSubject, shared_session_factory: sessionmaker[Session]
) -> None:
    approval = request_approval(env, expires_in=timedelta(minutes=5))
    decide(env, env.owner, approval)
    env.clock.advance(minutes=10)
    expire_approvals(_job(shared_session_factory, env))
    env.session.refresh(approval)
    assert approval.status == "approved"
    assert subject.decided == [("approved", approval.id)]
