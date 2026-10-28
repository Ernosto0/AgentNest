"""Disconnect cancels only waiting effects and preserves reconciliation until safe erasure."""

from datetime import timedelta

import pytest
from sqlalchemy import select

from app.approvals.models import Approval
from app.audit.models import AuditLog
from app.core.errors import AppError
from app.inbox.models import Conversation, InboundEvent, Message, ReplyDraft
from app.integrations.instagram.models import OAuthState, SocialAccount
from app.jobs.models import Job
from app.jobs.testing import run_due_jobs
from app.knowledge.models import ApprovedAnswer, FactReference
from app.operations import accounts, oauth_service
from app.operations.models import Operation
from app.operations.resolution import set_operation
from tests.factories import create_workspace
from tests.helpers.content import make_item, publish_job


def op_for(inbox, draft, status="retry_wait"):
    op = Operation(
        workspace_id=inbox.env.workspace.id,
        social_account_id=inbox.account.id,
        operation_type="send_reply",
        idempotency_key=f"send_reply:{draft.id}",
        subject_type="reply_draft",
        subject_id=draft.id,
        provider_kind="mock",
        status=status,
        attempts=1,
        max_attempts=6,
        is_simulated=True,
    )
    inbox.session.add(op)
    inbox.session.flush()
    draft.operation_id = op.id
    return op


def test_full_cascade_pending_approval_queued_send_and_scheduled_retry_content(inbox):
    inbox.deliver_and_process("hello", customer="first")
    pending = inbox.make_draft(customer="first")
    inbox.deliver_and_process("hello", customer="second")
    queued = inbox.make_draft("queued", customer="second")
    waiting = op_for(inbox, queued)
    job = Job(
        workspace_id=inbox.env.workspace.id,
        job_type="send_reply",
        payload={"reply_draft_id": str(queued.id)},
        run_at=inbox.clock.now() + timedelta(hours=1),
        max_attempts=6,
        dedup_key=f"send_reply:{queued.id}",
    )
    inbox.session.add(job)
    items = []
    for status in ("scheduled", "retry_scheduled"):
        item = make_item(inbox.env, status=status, social_account_id=inbox.account.id)
        pubjob = publish_job(inbox.env, item)
        pubop = Operation(
            workspace_id=inbox.env.workspace.id,
            social_account_id=inbox.account.id,
            operation_type="publish_content",
            idempotency_key=pubjob.dedup_key,
            subject_type="content_item",
            subject_id=item.id,
            provider_kind="mock",
            status="retry_wait",
            attempts=1,
            max_attempts=5,
            is_simulated=True,
        )
        inbox.session.add(pubop)
        items.append((item, pubjob, pubop))
    inbox.session.commit()
    response = inbox.env.call(
        inbox.env.owner, "POST", f"/social-accounts/{inbox.account.id}/disconnect"
    )
    assert response.status_code == 200
    inbox.session.expire_all()
    assert (
        inbox.refreshed(pending).status == "cancelled"
        and inbox.refreshed(queued).status == "cancelled"
    )
    approval = inbox.session.get(Approval, pending.approval_id)
    assert (approval.status, approval.cancel_reason) == ("cancelled", "ACCOUNT_DISCONNECTED")
    assert inbox.session.get(Job, job.id).status == "cancelled"
    assert inbox.session.get(Operation, waiting.id).status == "cancelled"
    for item, pubjob, pubop in items:
        inbox.session.refresh(item)
        assert (item.status, item.hold_reason) == ("on_hold", "ACCOUNT_UNAVAILABLE")
        assert inbox.session.get(Job, pubjob.id).status == "cancelled"
        assert inbox.session.get(Operation, pubop.id).status == "cancelled"
    assert inbox.session.scalar(select(AuditLog.id).where(AuditLog.action == "content.on_hold"))


def test_token_wipe_invalidates_pending_oauth_and_can_be_repeated_with_delete(inbox):
    inbox.deliver_and_process("hello")
    inbox.account.provider_kind = "meta"
    inbox.account.token_ciphertext = b"encrypted"
    inbox.account.token_key_id = "k1"
    inbox.account.token_expires_at = inbox.clock.now() + timedelta(days=5)
    inbox.account.token_refreshed_at = inbox.clock.now()
    state = OAuthState(
        workspace_id=inbox.env.workspace.id,
        user_id=inbox.env.owner.user.id,
        state_hash=b"a" * 32,
        purpose="reconnect",
        social_account_id=inbox.account.id,
        expires_at=inbox.clock.now() + timedelta(minutes=10),
    )
    inbox.session.add(state)
    inbox.session.commit()
    accounts.disconnect(
        inbox.session, inbox.clock, inbox.env.ctx(inbox.env.owner), inbox.account.id
    )
    assert all(
        getattr(inbox.account, key) is None
        for key in ("token_ciphertext", "token_key_id", "token_expires_at", "token_refreshed_at")
    )
    inbox.session.refresh(state)
    assert state.invalidated_at == inbox.clock.now()
    # Later explicit erasure is audited once; repeated erasure has identical effects.
    for _ in range(2):
        accounts.disconnect(
            inbox.session,
            inbox.clock,
            inbox.env.ctx(inbox.env.owner),
            inbox.account.id,
            delete_conversation_data=True,
        )
    logs = list(
        inbox.session.scalars(
            select(AuditLog).where(AuditLog.action == "social_account.disconnected")
        )
    )
    # The query intentionally has no ordering; frozen occurred_at values do not
    # establish chronology. Assert the exact two distinct requests and idempotency.
    assert len(logs) == 2 and sorted(r.metadata_["delete_conversation_data"] for r in logs) == [
        False,
        True,
    ]


def test_wipe_removes_cycles_fact_references_payload_and_preserves_foreign_history(inbox):
    facts = inbox.seed_facts()
    inbox.deliver_and_process("hello")
    draft = inbox.make_draft("sent", with_approval=False)
    message = inbox.messages()[0]
    message.reply_draft_id = draft.id
    fact = next(iter(facts.values()))
    ref = FactReference(
        workspace_id=inbox.env.workspace.id,
        fact_id=fact.id,
        fact_version=fact.current_version,
        referrer_type="reply_draft",
        referrer_id=draft.id,
    )
    answer = ApprovedAnswer(
        workspace_id=inbox.env.workspace.id,
        title="Saved answer",
        intent="pricing",
        answer_template="hello",
        language="tr",
        created_from_message_id=message.id,
        created_by_user_id=inbox.env.owner.user.id,
    )
    inbox.session.add_all([ref, answer])
    other = create_workspace(inbox.session)
    account = SocialAccount(
        workspace_id=other.id,
        provider_kind="mock",
        external_account_id="foreign",
        status="connected",
    )
    inbox.session.add(account)
    inbox.session.flush()
    foreign = Conversation(
        workspace_id=other.id, social_account_id=account.id, customer_external_id="foreign-customer"
    )
    inbox.session.add(foreign)
    inbox.session.commit()
    retained_audits = set(inbox.session.scalars(select(AuditLog.id)))
    draft_id, message_id, ref_id = draft.id, message.id, ref.id
    accounts.disconnect(
        inbox.session,
        inbox.clock,
        inbox.env.ctx(inbox.env.owner),
        inbox.account.id,
        delete_conversation_data=True,
    )
    inbox.session.expire_all()
    assert inbox.session.get(ReplyDraft, draft_id) is None
    assert inbox.session.get(Message, message_id) is None
    assert inbox.session.get(FactReference, ref_id) is None
    assert inbox.session.get(Conversation, foreign.id) is not None
    assert inbox.session.get(ApprovedAnswer, answer.id).created_from_message_id is None
    assert all(
        row.payload is None
        for row in inbox.session.scalars(
            select(InboundEvent).where(InboundEvent.social_account_id == inbox.account.id)
        )
    )
    assert retained_audits <= set(inbox.session.scalars(select(AuditLog.id)))


@pytest.mark.parametrize("status", ["in_progress", "outcome_unknown"])
def test_uncertain_send_defers_erasure_until_terminal_and_blocks_account_reuse(inbox, status):
    inbox.deliver_and_process("hello")
    draft = inbox.make_draft(
        "sending" if status == "in_progress" else "outcome_unknown", with_approval=False
    )
    op = op_for(inbox, draft, status)
    draft_id = draft.id
    inbox.session.commit()
    accounts.disconnect(
        inbox.session,
        inbox.clock,
        inbox.env.ctx(inbox.env.owner),
        inbox.account.id,
        delete_conversation_data=True,
    )
    inbox.session.refresh(op)
    assert op.status == status and inbox.session.get(ReplyDraft, draft.id) is not None
    job = inbox.session.scalar(select(Job).where(Job.job_type == "delete_account_conversations"))
    assert job is not None and job.status == "queued"
    cfg = inbox.settings.model_copy(update={"instagram_enabled_providers": "meta"})
    with pytest.raises(AppError, match="CONFLICT_STATE"):
        oauth_service.start_connect(inbox.session, inbox.clock, inbox.env.ctx(inbox.env.owner), cfg)
    inbox.session.rollback()
    for _ in range(4):
        run_due_jobs(inbox.clock, session_factory=inbox.factory)
        inbox.clock.advance(minutes=5)
    inbox.session.expire_all()
    job = inbox.session.get(Job, job.id)
    assert job.status == "queued" and job.attempts == 0
    set_operation(inbox.clock, op, "fail", code="OUTCOME_UNCONFIRMED")
    inbox.session.commit()
    run_due_jobs(inbox.clock, session_factory=inbox.factory)
    inbox.session.expire_all()
    assert inbox.session.get(Job, job.id).status == "succeeded"
    assert inbox.session.get(ReplyDraft, draft_id) is None
    assert inbox.session.get(Operation, op.id).status == "failed"


def test_foreign_disconnect_404_preserves_tokens(inbox):
    other = create_workspace(inbox.session)
    account = SocialAccount(
        workspace_id=other.id,
        provider_kind="meta",
        external_account_id="foreign",
        status="connected",
        token_ciphertext=b"encrypted",
    )
    inbox.session.add(account)
    inbox.session.commit()
    response = inbox.env.call(
        inbox.env.owner,
        "POST",
        f"/social-accounts/{account.id}/disconnect",
        json={"delete_conversation_data": True},
    )
    assert response.status_code == 404
    inbox.session.refresh(account)
    assert account.token_ciphertext == b"encrypted" and account.status == "connected"


def test_new_history_after_prior_erasure_audits_new_request_once(inbox):
    inbox.deliver_and_process("hello")
    ctx = inbox.env.ctx(inbox.env.owner)
    accounts.disconnect(
        inbox.session, inbox.clock, ctx, inbox.account.id, delete_conversation_data=True
    )
    # A newly authorized connection can deliberately reuse the disconnected account row.
    accounts.transition_account(
        inbox.session, inbox.clock, ctx, inbox.account, "connected", reauthorized=True
    )
    inbox.session.commit()
    inbox.deliver_and_process("new history", mid="new-history")
    accounts.disconnect(inbox.session, inbox.clock, ctx, inbox.account.id)
    for _ in range(2):
        accounts.disconnect(
            inbox.session, inbox.clock, ctx, inbox.account.id, delete_conversation_data=True
        )
    audits = list(
        inbox.session.scalars(
            select(AuditLog).where(AuditLog.action == "social_account.disconnected")
        )
    )
    assert len(audits) == 3
    assert sum(row.metadata_["delete_conversation_data"] for row in audits) == 2
