"""D-02: approval-ladder suggestions. A weekly job counts the owner's unchanged approvals per
topic and proposes automatic sending for the topics policy allows; the owner confirms through the
existing delegation preview and apply endpoints, or dismisses (a cool-down). Everything is audited.
"""

import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.agent import suggestions
from app.agent.models import AccountAgent, AgentDelegation, DelegationSuggestion
from app.approvals.models import Approval
from app.audit.service import list_entries
from app.core.canonical import payload_hash
from app.core.clock import FrozenClock
from app.inbox.approval_payload import approval_payload
from app.inbox.models import Conversation, Message, ReplyDraft
from app.integrations.instagram.models import SocialAccount
from app.jobs.models import Job
from app.jobs.testing import run_due_jobs
from app.notifications.models import Notification
from app.policy.models import AutomationPolicy
from app.policy.service import get_policies
from tests.helpers.env import Env, build_env
from tests.helpers.gym import seed_gym_facts

MIN = 20  # DELEGATION_SUGGESTION_MIN_UNCHANGED default


@pytest.fixture
def env(db_session: Session, make_client: Callable[[], TestClient], clock: FrozenClock) -> Env:
    return build_env(db_session, make_client, clock)


class Ladder:
    """A workspace that is ready for automation, with one connected (real, not simulated)
    account, and helpers that write the drafts and approvals an owner's weeks would leave."""

    def __init__(self, env: Env) -> None:
        self.env = env
        self.session = env.session
        self.clock = env.clock
        seed_gym_facts(self.session, env.workspace, env.clock)
        self.account = SocialAccount(
            workspace_id=env.workspace.id,
            provider_kind="meta",
            external_account_id=f"ig-{uuid.uuid4().hex[:8]}",
            status="connected",
            capabilities={"messaging": True},
        )
        self.session.add(self.account)
        self.session.flush()
        self.conversations: dict[tuple[uuid.UUID, str], tuple[Conversation, Message]] = {}
        self.session.commit()

    # --- building evidence ---

    def conversation(self, account: SocialAccount | None = None, customer: str = "c") -> Any:
        account = account or self.account
        key = (account.id, customer)
        if key not in self.conversations:
            conversation = Conversation(
                workspace_id=self.env.workspace.id,
                social_account_id=account.id,
                customer_external_id=customer,
                is_simulated=account.provider_kind == "mock",
            )
            self.session.add(conversation)
            self.session.flush()
            message = Message(
                workspace_id=self.env.workspace.id,
                conversation_id=conversation.id,
                social_account_id=account.id,
                direction="inbound",
                sender_kind="customer",
                text="soru",
                provider_timestamp=self.clock.now() - timedelta(days=40),
            )
            self.session.add(message)
            self.session.flush()
            self.conversations[key] = (conversation, message)
        return self.conversations[key]

    def draft(
        self,
        intent: str = "hours",
        *,
        approved: bool = True,
        channel: str = "web",
        edited: bool = False,
        rejected: bool = False,
        status: str = "sent",
        failure_code: str | None = None,
        simulated: bool = False,
        source: str = "ai",
        age_days: int = 3,
        account: SocialAccount | None = None,
        tamper_hash: bool = False,
        customer: str = "c",
    ) -> ReplyDraft:
        conversation, message = self.conversation(account, customer)
        created = self.clock.now() - timedelta(days=age_days)
        draft = ReplyDraft(
            workspace_id=self.env.workspace.id,
            conversation_id=conversation.id,
            covers_through_message_id=message.id,
            source=source,
            language="tr",
            intent=intent,
            text="Her gün 07:00-22:00 açığız.",
            decision="approval_required",
            decision_reasons=["OWNER_EDIT"] if edited else ["POLICY_REQUIRES_APPROVAL"],
            status="cancelled" if rejected else status,
            failure_code=failure_code,
            version=2 if edited else 1,
            created_by_actor_type="system",
            is_simulated=simulated,
            created_at=created,
        )
        self.session.add(draft)
        self.session.flush()
        if approved or rejected:
            digest = payload_hash(approval_payload(draft, conversation))
            self.session.add(
                Approval(
                    workspace_id=self.env.workspace.id,
                    kind="authorization",
                    action="reply.send",
                    subject_type="reply_draft",
                    subject_id=draft.id,
                    subject_version=draft.version,
                    payload_hash="0" * 64 if tamper_hash else digest,
                    summary={},
                    required_permission="reply.approve",
                    status="rejected" if rejected else "approved",
                    requested_by_actor_type="system",
                    decided_by_user_id=self.env.owner.user.id,
                    decided_at=created,
                    decision_channel=channel,
                    expires_at=created + timedelta(hours=1),
                    created_at=created,
                    is_simulated=simulated,
                )
            )
        self.session.flush()
        return draft

    def clean_week(self, intent: str = "hours", count: int = MIN, **kwargs: Any) -> None:
        for _ in range(count):
            self.draft(intent, **kwargs)
        self.session.commit()

    # --- reading ---

    def generate(self) -> DelegationSuggestion | None:
        row = suggestions.generate(self.session, self.clock, self.env.workspace.id)
        self.session.commit()
        return row

    def all(self) -> list[DelegationSuggestion]:
        self.session.expire_all()
        return list(
            self.session.scalars(
                select(DelegationSuggestion)
                .where(DelegationSuggestion.workspace_id == self.env.workspace.id)
                .order_by(DelegationSuggestion.week)
            )
        )

    def notifications(self) -> list[Notification]:
        self.session.expire_all()
        return list(
            self.session.scalars(
                select(Notification).where(
                    Notification.workspace_id == self.env.workspace.id,
                    Notification.type == "delegation_suggestion",
                )
            )
        )

    def mode(self, action_class: str = "reply.hours") -> str:
        self.session.expire_all()
        return get_policies(self.session, self.env.workspace.id)[action_class]

    def actions(self, action: str) -> int:
        self.session.expire_all()
        return len(list_entries(self.session, workspace_id=self.env.workspace.id, action=action))

    def next_week(self) -> None:
        self.clock.advance(timedelta(days=7))

    # --- the API ---

    def listed(self, role: str = "owner") -> Any:
        return self.env.call(getattr(self.env, role), "GET", "/delegation-suggestions")

    def agent_path(self, tail: str, account: SocialAccount | None = None) -> str:
        return f"/accounts/{(account or self.account).id}/agent/delegation/{tail}"

    def preview(self, change: dict[str, Any], role: str = "owner") -> Any:
        return self.env.call(
            getattr(self.env, role), "POST", self.agent_path("preview"), json=change
        )

    def apply(self, change: dict[str, Any], role: str = "owner") -> Any:
        return self.env.call(getattr(self.env, role), "POST", self.agent_path("apply"), json=change)

    def confirm(self) -> dict[str, Any]:
        """The owner's two clicks: preview, then apply, with the change the card carries."""
        [item] = self.listed().json()["items"]
        change = item["change"]
        assert self.preview(change).status_code == 200
        response = self.apply(change)
        assert response.status_code == 200, response.text
        return change  # type: ignore[no-any-return]


@pytest.fixture
def ladder(env: Env) -> Ladder:
    return Ladder(env)


# --- the evidence ----------------------------------------------------------------------------


def test_unchanged_web_and_telegram_approvals_are_counted_once_each(ladder: Ladder) -> None:
    ladder.draft(channel="web")
    ladder.draft(channel="telegram")
    ladder.session.commit()
    counts = suggestions.evidence(
        ladder.session, ladder.clock, ladder.env.workspace.id, ladder.account.id
    )
    assert counts["hours"] == {"unchanged": 2, "edited": 0, "rejected": 0, "failed": 0}


def test_only_exact_owner_approvals_of_sent_replies_are_positive_evidence(ladder: Ladder) -> None:
    ladder.draft(approved=False)  # sent with no approval on record
    ladder.draft(channel="policy")  # an automatic grant is not the owner's approval
    ladder.draft(tamper_hash=True)  # the approval does not bind this exact text
    ladder.draft(status="pending_approval")  # not sent
    ladder.draft(simulated=True)  # simulated is never evidence (INV-09)
    ladder.draft(source="owner")  # not the assistant's own wording
    ladder.draft(age_days=60)  # outside the window
    ladder.draft(intent="hours")  # the one that counts
    ladder.session.commit()
    counts = suggestions.evidence(
        ladder.session, ladder.clock, ladder.env.workspace.id, ladder.account.id
    )
    assert counts["hours"]["unchanged"] == 1


def test_edits_rejections_and_failures_are_counted_and_never_positive(ladder: Ladder) -> None:
    ladder.draft(edited=True)
    ladder.draft(rejected=True)
    ladder.draft(status="failed", failure_code="SEND_FAILED")
    ladder.draft(status="outcome_unknown")
    ladder.session.commit()
    counts = suggestions.evidence(
        ladder.session, ladder.clock, ladder.env.workspace.id, ladder.account.id
    )
    assert counts["hours"] == {"unchanged": 0, "edited": 1, "rejected": 1, "failed": 2}


def test_evidence_is_per_account(ladder: Ladder) -> None:
    other = SocialAccount(
        workspace_id=ladder.env.workspace.id,
        provider_kind="meta",
        external_account_id="ig-other",
        status="disconnected",  # one active account per workspace
    )
    ladder.session.add(other)
    ladder.session.flush()
    ladder.draft(account=other)
    ladder.session.commit()
    ws = ladder.env.workspace.id
    assert suggestions.evidence(ladder.session, ladder.clock, ws, ladder.account.id) == {}
    assert (
        suggestions.evidence(ladder.session, ladder.clock, ws, other.id)["hours"]["unchanged"] == 1
    )


# --- the weekly suggestion -------------------------------------------------------------------


def test_nineteen_unchanged_approvals_are_not_enough_and_twenty_are(ladder: Ladder) -> None:
    ladder.clean_week(count=MIN - 1)
    assert ladder.generate() is None
    assert ladder.all() == []
    ladder.draft()
    ladder.session.commit()
    row = ladder.generate()
    assert row is not None and row.status == "pending"
    assert (row.intent, row.action_class) == ("hours", "reply.hours")
    assert row.counts == {"unchanged": MIN, "edited": 0, "rejected": 0, "failed": 0}
    assert row.week == datetime(2026, 1, 12, tzinfo=UTC).date()  # Monday of the local week
    assert row.expires_at == ladder.clock.now() + timedelta(days=7)


@pytest.mark.parametrize(
    "spoiler",
    [
        {"edited": True},
        {"rejected": True},
        {"status": "failed", "failure_code": "SEND_FAILED"},
    ],
    ids=["edit", "rejection", "failure"],
)
def test_a_single_edit_rejection_or_failure_in_the_window_blocks_the_suggestion(
    ladder: Ladder, spoiler: dict[str, Any]
) -> None:
    ladder.clean_week(count=MIN + 5)
    ladder.draft(**spoiler)
    ladder.session.commit()
    assert ladder.generate() is None
    assert ladder.notifications() == []


@pytest.mark.parametrize(
    "intent", ["pricing", "booking", "promotions", "faq", "greeting", "complaint", "refund_request"]
)
def test_price_booking_promotion_faq_and_human_only_topics_are_never_suggested(
    ladder: Ladder, intent: str
) -> None:
    ladder.clean_week(intent, count=MIN + 10)
    assert ladder.generate() is None
    assert ladder.all() == []
    assert ladder.notifications() == []


def test_a_topic_the_owner_turned_off_or_already_automated_is_not_suggested(
    ladder: Ladder,
) -> None:
    ladder.clean_week("hours")
    ladder.clean_week("services")
    for action_class, mode in (("reply.hours", "off"), ("reply.services", "auto")):
        ladder.session.add(
            AutomationPolicy(
                workspace_id=ladder.env.workspace.id,
                action_class=action_class,
                mode=mode,
                updated_at=ladder.clock.now(),
            )
        )
    ladder.session.commit()
    assert ladder.generate() is None


def test_nothing_is_suggested_until_readiness_allows_automation(env: Env) -> None:
    ladder = Ladder(env)
    ladder.clean_week()
    from app.knowledge.models import BusinessFact

    ladder.session.query(BusinessFact).delete()  # the verified facts automation relies on
    ladder.session.commit()
    assert ladder.generate() is None


def test_simulated_accounts_are_never_suggested(env: Env) -> None:
    ladder = Ladder(env)
    ladder.account.provider_kind = "mock"
    ladder.session.commit()
    ladder.clean_week()
    assert ladder.generate() is None


def test_an_agent_controlled_account_is_not_suggested(ladder: Ladder) -> None:
    ladder.clean_week()
    agent = ladder.session.scalar(
        select(AccountAgent).where(AccountAgent.social_account_id == ladder.account.id)
    )
    assert agent is not None
    agent.controller_mode = "agent"
    ladder.session.commit()
    assert ladder.generate() is None


def test_one_suggestion_and_one_notification_per_workspace_per_week(ladder: Ladder) -> None:
    ladder.clean_week("hours")
    ladder.clean_week("services")
    ladder.clean_week("location_contact")
    first = ladder.generate()
    assert first is not None
    assert ladder.generate() is None  # a second run in the same week does nothing
    ladder.clock.advance(timedelta(days=2))
    assert ladder.generate() is None
    assert len(ladder.all()) == 1
    [notification] = ladder.notifications()
    assert notification.recipient_user_id == ladder.env.owner.user.id
    assert notification.subject_id == first.id
    assert notification.params == {"account_id": str(ladder.account.id), "intent": "hours"}
    assert ladder.actions("agent.delegation_suggested") == 1


def test_an_unanswered_suggestion_expires_and_the_next_week_may_suggest_again(
    ladder: Ladder,
) -> None:
    ladder.clean_week()
    first = ladder.generate()
    assert first is not None
    ladder.next_week()
    ladder.draft(age_days=0)  # keep the evidence fresh
    ladder.session.commit()
    second = ladder.generate()
    assert second is not None and second.id != first.id
    statuses = [row.status for row in ladder.all()]
    assert statuses == ["expired", "pending"]
    assert [item["id"] for item in ladder.listed().json()["items"]] == [str(second.id)]


def test_a_suggestion_is_created_by_the_owner_not_by_a_member_without_authority(
    ladder: Ladder,
) -> None:
    ladder.clean_week()
    ladder.generate()
    assert ladder.listed("manager").status_code == 403
    assert ladder.listed("staff").status_code == 403
    assert len(ladder.listed("owner").json()["items"]) == 1


# --- confirming through delegation preview and apply -----------------------------------------


def test_the_owner_confirms_through_delegation_preview_then_apply(ladder: Ladder) -> None:
    ladder.clean_week()
    row = ladder.generate()
    assert row is not None
    assert ladder.mode() == "approval"

    [item] = ladder.listed().json()["items"]
    assert item["intent"] == "hours" and item["action_class"] == "reply.hours"
    assert item["counts"]["unchanged"] == MIN
    change = item["change"]
    assert change["suggestion_id"] == str(row.id)

    preview = ladder.preview(change)
    assert preview.status_code == 200, preview.text
    assert preview.json()["automation_class"] == "reply.hours"
    assert preview.json()["changed_actions"] == []
    assert ladder.mode() == "approval"  # a preview changes nothing

    applied = ladder.apply(change)
    assert applied.status_code == 200, applied.text
    assert ladder.mode() == "auto"
    assert ladder.mode("reply.pricing") == "approval"  # only that topic
    assert ladder.mode("reply.services") == "approval"
    [stored] = ladder.all()
    assert stored.status == "accepted" and stored.decided_by_user_id == ladder.env.owner.user.id
    assert stored.cooldown_until is not None
    assert ladder.listed().json()["items"] == []

    assert ladder.actions("agent.delegation_suggested") == 1
    assert ladder.actions("agent.delegation_suggestion_previewed") == 1
    assert ladder.actions("agent.delegation_suggestion_accepted") == 1
    assert ladder.actions("policy.updated") == 1
    assert ladder.actions("agent.delegation_applied") == 1
    [delegation_audit] = list_entries(
        ladder.session, workspace_id=ladder.env.workspace.id, action="agent.delegation_applied"
    )
    assert delegation_audit.metadata_["changed_actions"] == []  # the agent's grant is unchanged
    delegation = ladder.session.scalar(
        select(AgentDelegation).where(AgentDelegation.social_account_id == ladder.account.id)
    )
    assert delegation is not None
    assert all(rule["mode"] == "off" for rule in delegation.policy["actions"].values())


def test_apply_without_a_preview_is_refused_and_changes_nothing(ladder: Ladder) -> None:
    ladder.clean_week()
    ladder.generate()
    [item] = ladder.listed().json()["items"]
    response = ladder.apply(item["change"])
    assert response.status_code == 409
    assert response.json()["params"]["reason"] == "suggestion_preview_required"
    assert ladder.mode() == "approval"
    assert ladder.all()[0].status == "pending"
    assert ladder.actions("agent.delegation_suggestion_accepted") == 0


def test_a_change_that_differs_from_the_suggestion_is_refused(ladder: Ladder) -> None:
    ladder.clean_week()
    ladder.generate()
    [item] = ladder.listed().json()["items"]
    change = item["change"]
    assert ladder.preview(change).status_code == 200
    tampered = {**change, "policy": {"actions": {**change["policy"]["actions"]}}}
    tampered["policy"]["actions"]["dm.send"] = {"mode": "automatic", "max_per_day": None}
    tampered["policy"]["actions"]["dm.send"]["sources"] = ["customer"]
    for call in (ladder.preview, ladder.apply):
        response = call(tampered)
        assert response.status_code == 409, response.text
    assert ladder.mode() == "approval"
    assert ladder.session.scalar(select(func.count(AgentDelegation.id))) == 0


def test_a_suggestion_cannot_be_used_on_another_account(ladder: Ladder) -> None:
    ladder.clean_week()
    ladder.generate()
    other = SocialAccount(
        workspace_id=ladder.env.workspace.id,
        provider_kind="meta",
        external_account_id="ig-second",
        status="disconnected",  # one active account per workspace
    )
    ladder.session.add(other)
    ladder.session.commit()
    [item] = ladder.listed().json()["items"]
    response = ladder.env.call(
        ladder.env.owner,
        "POST",
        ladder.agent_path("preview", other),
        json=item["change"],
    )
    assert response.status_code == 404
    assert ladder.mode() == "approval"


@pytest.mark.parametrize("role", ["manager", "staff"])
def test_only_the_owner_can_preview_or_apply(ladder: Ladder, role: str) -> None:
    ladder.clean_week()
    ladder.generate()
    [item] = ladder.listed().json()["items"]
    assert ladder.preview(item["change"], role).status_code == 403
    assert ladder.apply(item["change"], role).status_code == 403
    assert ladder.mode() == "approval"


def test_a_new_edit_after_the_suggestion_withdraws_it(ladder: Ladder) -> None:
    ladder.clean_week()
    ladder.generate()
    [item] = ladder.listed().json()["items"]
    assert ladder.preview(item["change"]).status_code == 200
    ladder.draft(edited=True, age_days=0)
    ladder.session.commit()
    response = ladder.apply(item["change"])
    assert response.status_code == 409
    assert response.json()["params"]["reason"] == "suggestion_ineligible"
    assert ladder.mode() == "approval"


def test_a_topic_changed_by_hand_in_the_meantime_withdraws_it(ladder: Ladder) -> None:
    ladder.clean_week()
    ladder.generate()
    [item] = ladder.listed().json()["items"]
    ladder.session.add(
        AutomationPolicy(
            workspace_id=ladder.env.workspace.id,
            action_class="reply.hours",
            mode="off",
            updated_at=ladder.clock.now(),
        )
    )
    ladder.session.commit()
    assert ladder.listed().json()["items"] == []
    assert ladder.preview(item["change"]).status_code == 409


def test_an_expired_suggestion_cannot_be_confirmed(ladder: Ladder) -> None:
    ladder.clean_week()
    ladder.generate()
    [item] = ladder.listed().json()["items"]
    assert ladder.preview(item["change"]).status_code == 200
    ladder.clock.advance(timedelta(days=8))
    response = ladder.apply(item["change"])
    assert response.status_code == 409
    assert response.json()["params"]["reason"] == "suggestion_not_pending"
    assert ladder.mode() == "approval"


def test_repeating_the_apply_is_idempotent(ladder: Ladder) -> None:
    ladder.clean_week()
    ladder.generate()
    change = ladder.confirm()
    again = ladder.apply(change)
    assert again.status_code == 200
    assert ladder.mode() == "auto"
    assert ladder.actions("agent.delegation_suggestion_accepted") == 1
    assert ladder.session.scalar(select(func.count(AgentDelegation.id))) == 1


def test_free_text_never_confirms_a_suggestion(ladder: Ladder) -> None:
    """There is no endpoint that accepts text, and a plain delegation apply with the
    suggestion's client request id but no suggestion id cannot accept it either."""
    ladder.clean_week()
    ladder.generate()
    [item] = ladder.listed().json()["items"]
    plain = {k: v for k, v in item["change"].items() if k != "suggestion_id"}
    assert ladder.apply(plain).status_code == 200  # an ordinary (no-op) delegation save
    assert ladder.mode() == "approval"
    assert ladder.all()[0].status == "pending"


# --- dismissing, and the cool-down -----------------------------------------------------------


def test_dismissing_records_a_cooldown_and_audits_it(ladder: Ladder) -> None:
    ladder.clean_week()
    row = ladder.generate()
    assert row is not None
    response = ladder.env.call(
        ladder.env.owner, "POST", f"/delegation-suggestions/{row.id}/dismiss"
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "dismissed"
    assert datetime.fromisoformat(body["cooldown_until"]) == ladder.clock.now() + timedelta(days=30)
    assert ladder.mode() == "approval"
    assert ladder.listed().json()["items"] == []
    assert ladder.actions("agent.delegation_suggestion_dismissed") == 1

    again = ladder.env.call(ladder.env.owner, "POST", f"/delegation-suggestions/{row.id}/dismiss")
    assert again.status_code == 200
    assert (
        ladder.actions("agent.delegation_suggestion_dismissed") == 1
    )  # a repeat is not a second one


def test_a_dismissed_topic_stays_silent_for_the_cooldown_then_may_return(ladder: Ladder) -> None:
    ladder.clean_week()
    row = ladder.generate()
    assert row is not None
    ladder.env.call(ladder.env.owner, "POST", f"/delegation-suggestions/{row.id}/dismiss")

    for _ in range(4):  # four more weeks, 28 days: inside the 30-day cool-down
        ladder.next_week()
        ladder.draft(age_days=0)
        ladder.session.commit()
        assert ladder.generate() is None
    assert len(ladder.all()) == 1
    assert len(ladder.notifications()) == 1

    ladder.next_week()  # day 35: the cool-down is over
    ladder.clean_week(age_days=0)  # and the window holds fresh evidence again
    again = ladder.generate()
    assert again is not None and again.id != row.id


def test_a_dismissal_silences_only_that_topic(ladder: Ladder) -> None:
    ladder.clean_week("hours")
    ladder.clean_week("services")
    row = ladder.generate()
    assert row is not None and row.intent == "hours"
    ladder.env.call(ladder.env.owner, "POST", f"/delegation-suggestions/{row.id}/dismiss")
    ladder.next_week()
    ladder.draft("hours", age_days=0)
    ladder.draft("services", age_days=0)
    ladder.session.commit()
    nxt = ladder.generate()
    assert nxt is not None and nxt.intent == "services"


def test_an_accepted_topic_is_not_proposed_again_straight_after_the_owner_reverts_it(
    ladder: Ladder,
) -> None:
    ladder.clean_week()
    ladder.generate()
    ladder.confirm()
    policy = ladder.session.get(AutomationPolicy, (ladder.env.workspace.id, "reply.hours"))
    assert policy is not None
    policy.mode = "approval"
    ladder.session.commit()
    ladder.next_week()
    ladder.draft(age_days=0)
    ladder.session.commit()
    assert ladder.generate() is None


def test_a_decided_suggestion_cannot_be_dismissed_and_a_dismissed_one_cannot_be_confirmed(
    ladder: Ladder,
) -> None:
    ladder.clean_week()
    row = ladder.generate()
    assert row is not None
    [item] = ladder.listed().json()["items"]
    ladder.env.call(ladder.env.owner, "POST", f"/delegation-suggestions/{row.id}/dismiss")
    assert ladder.preview(item["change"]).status_code == 409
    assert ladder.mode() == "approval"

    ladder.next_week()
    ladder.clean_week("services")
    second = ladder.generate()
    assert second is not None
    ladder.confirm()
    done = ladder.env.call(ladder.env.owner, "POST", f"/delegation-suggestions/{second.id}/dismiss")
    assert done.status_code == 409


@pytest.mark.parametrize("role", ["manager", "staff"])
def test_only_the_owner_can_dismiss(ladder: Ladder, role: str) -> None:
    ladder.clean_week()
    row = ladder.generate()
    assert row is not None
    response = ladder.env.call(
        getattr(ladder.env, role), "POST", f"/delegation-suggestions/{row.id}/dismiss"
    )
    assert response.status_code == 403
    assert ladder.all()[0].status == "pending"


# --- the weekly job --------------------------------------------------------------------------


def _tick(session: Session, at: datetime) -> int:
    count = suggestions.enqueue_suggestions(session, FrozenClock(at))
    session.commit()
    return count


def _jobs(session: Session) -> list[Job]:
    return list(session.scalars(select(Job).where(Job.job_type == "delegation_suggestion")))


def test_one_job_per_workspace_per_local_week_after_monday_morning(ladder: Ladder) -> None:
    session = ladder.session
    monday = datetime(2026, 1, 12, tzinfo=UTC)
    assert _tick(session, monday.replace(hour=5)) == 0  # 08:00 in Istanbul: too early
    assert _tick(session, monday.replace(hour=6)) == 1  # 09:00 local
    assert _tick(session, monday.replace(hour=7)) == 0
    assert _tick(session, monday + timedelta(days=3)) == 0  # the same week
    [job] = _jobs(session)
    assert job.dedup_key == f"delegation_suggestion:{ladder.env.workspace.id}:2026-01-12"
    assert job.payload == {"workspace_id": str(ladder.env.workspace.id), "week": "2026-01-12"}
    assert _tick(session, monday + timedelta(days=7, hours=6)) == 1  # the next week
    assert len(_jobs(session)) == 2


def test_the_job_creates_the_suggestion_and_the_notification(
    ladder: Ladder, shared_session_factory: sessionmaker[Session]
) -> None:
    ladder.clean_week()
    now = datetime(2026, 1, 15, 12, 0, tzinfo=UTC)  # a Thursday
    assert _tick(ladder.session, now) == 1
    assert run_due_jobs(FrozenClock(now), session_factory=shared_session_factory) >= 1
    assert [row.status for row in ladder.all()] == ["pending"]
    assert len(ladder.notifications()) == 1
    # Running the same week's job again (a retry) creates nothing new.
    [job] = _jobs(ladder.session)
    payload = suggestions.DelegationSuggestionPayload.model_validate(job.payload)
    suggestions.generate(ladder.session, ladder.clock, payload.workspace_id)
    ladder.session.commit()
    assert len(ladder.all()) == 1 and len(ladder.notifications()) == 1


def test_a_workspace_being_deleted_gets_no_job_and_no_suggestion(ladder: Ladder) -> None:
    ladder.clean_week()
    ladder.env.workspace.status = "deleting"
    ladder.session.commit()
    assert _tick(ladder.session, ladder.clock.now()) == 0
    assert ladder.generate() is None


def test_the_notification_has_no_customer_text_and_no_price(ladder: Ladder) -> None:
    ladder.clean_week()
    ladder.generate()
    [notification] = ladder.notifications()
    assert set(notification.params) == {"account_id", "intent"}
    assert notification.severity == "info"
    row = ladder.all()[0]
    assert set(row.counts) == {"unchanged", "edited", "rejected", "failed"}
