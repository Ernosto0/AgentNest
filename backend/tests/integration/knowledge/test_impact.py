"""Impact framework: handlers, propagation in the update transaction, fact_references."""

import uuid
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.clock import Clock
from app.core.context import WorkspaceContext
from app.knowledge import impact, service
from app.knowledge.models import BusinessFact, FactReference
from app.notifications.models import Notification
from tests.factories import create_fact, create_workspace, money
from tests.integration.knowledge.conftest import KnowledgeEnv

KEY = "pricing.membership_monthly"


@dataclass
class FakeReferrer:
    """A throw-away referrer type: counts rows in ``fact_references`` and 'supersedes' them."""

    referrer_type: str = "reply_draft"
    fail: bool = False
    calls: list[tuple[str, int, int]] = field(default_factory=list)

    def count(self, session: Session, ctx: WorkspaceContext, fact_id: uuid.UUID) -> dict[str, int]:
        rows = impact.references_to_fact(session, ctx, fact_id, self.referrer_type)
        return {"pending_approval": len(rows)} if rows else {}

    def apply_change(
        self,
        session: Session,
        clock: Clock,
        ctx: WorkspaceContext,
        fact: BusinessFact,
        change: str,
        old_version: int,
    ) -> dict[str, int]:
        self.calls.append((change, old_version, fact.current_version))
        if self.fail:
            raise RuntimeError("handler failed")
        return {"superseded": len(impact.references_to_fact(session, ctx, fact.id, "reply_draft"))}


@pytest.fixture
def referrer() -> Iterator[FakeReferrer]:
    fake = FakeReferrer()
    with impact.handlers_snapshot(clear=True):
        impact.register_handler(fake)  # type: ignore[arg-type]
        yield fake


def _fact(env: KnowledgeEnv) -> BusinessFact:
    return create_fact(env.session, env.workspace, KEY, money("6000"), clock=env.clock)


def _reference(env: KnowledgeEnv, fact: BusinessFact, count: int = 2) -> None:
    ctx = service_ctx(env)
    for _ in range(count):
        impact.replace_references(
            env.session, ctx, "reply_draft", uuid.uuid4(), [(fact.id, fact.current_version)]
        )
    env.session.commit()


def service_ctx(env: KnowledgeEnv) -> WorkspaceContext:
    from tests.factories import knowledge_ctx

    return knowledge_ctx(env.workspace, env.owner.user, "owner")


def test_analyze_impact_counts_what_each_handler_reports(
    env: KnowledgeEnv, referrer: FakeReferrer
) -> None:
    fact = _fact(env)
    _reference(env, fact, 3)
    report = impact.analyze_impact(env.session, service_ctx(env), fact.id)
    assert report.total == 3
    assert report.to_dict() == {
        "total": 3,
        "items": [{"referrer_type": "reply_draft", "counts": {"pending_approval": 3}, "total": 3}],
    }


def test_with_no_handlers_the_report_is_empty_and_updates_still_work(env: KnowledgeEnv) -> None:
    with impact.handlers_snapshot(clear=True):
        fact = _fact(env)
        assert impact.analyze_impact(env.session, service_ctx(env), fact.id).to_dict() == {
            "total": 0,
            "items": [],
        }
        updated = service.update_fact(
            env.session,
            env.clock,
            service_ctx(env),
            fact.id,
            expected_version=1,
            value=money("7000"),
        )
        assert updated.current_version == 2  # type: ignore[union-attr]


def test_a_value_change_calls_the_handlers_in_the_same_transaction(
    env: KnowledgeEnv, referrer: FakeReferrer
) -> None:
    fact = _fact(env)
    _reference(env, fact, 2)
    service.update_fact(
        env.session, env.clock, service_ctx(env), fact.id, expected_version=1, value=money("7000")
    )
    assert referrer.calls == [("value_changed", 1, 2)]  # old version 1, new version 2


def test_the_fact_changed_notification_reaches_the_other_verifiers_with_impact_counts(
    env: KnowledgeEnv, referrer: FakeReferrer
) -> None:
    fact = _fact(env)
    _reference(env, fact, 2)
    service.update_fact(
        env.session, env.clock, service_ctx(env), fact.id, expected_version=1, value=money("7000")
    )
    notes = env.session.scalars(select(Notification)).all()
    # The owner made the change; the manager is told; staff cannot verify, so is not told.
    assert [n.recipient_user_id for n in notes] == [env.manager.user.id]
    (note,) = notes
    assert note.type == "knowledge.fact_changed" and note.subject_id == fact.id
    assert note.dedup_key == f"fact:{fact.id}:v2"
    params: dict[str, Any] = note.params
    assert (
        params["fact_key"] == KEY and params["version"] == 2 and params["change"] == "value_changed"
    )
    assert params["old_display"] == "6.000 ₺ / ay" and params["new_display"] == "7.000 ₺ / ay"
    assert params["impact"] == {"total": 2, "by_referrer": {"reply_draft": {"superseded": 2}}}


def test_archiving_a_fact_propagates_too(env: KnowledgeEnv, referrer: FakeReferrer) -> None:
    fact = _fact(env)
    service.archive_fact(env.session, env.clock, service_ctx(env), fact.id, expected_version=1)
    assert referrer.calls == [("archived", 1, 2)]
    note = env.session.scalars(select(Notification)).one()
    assert note.params["change"] == "archived" and note.params["new_display"] == ""


def test_saving_the_same_value_changes_nothing_and_notifies_nobody(
    env: KnowledgeEnv, referrer: FakeReferrer
) -> None:
    fact = _fact(env)
    service.update_fact(
        env.session, env.clock, service_ctx(env), fact.id, expected_version=1, value=money("6000")
    )
    assert referrer.calls == [] and env.session.scalars(select(Notification)).all() == []


def test_a_failing_handler_undoes_the_whole_fact_change(
    env: KnowledgeEnv, referrer: FakeReferrer
) -> None:
    fact = _fact(env)
    referrer.fail = True
    with pytest.raises(RuntimeError):
        service.update_fact(
            env.session,
            env.clock,
            service_ctx(env),
            fact.id,
            expected_version=1,
            value=money("7000"),
        )
    env.session.rollback()
    env.session.expire_all()
    stored = env.session.get(BusinessFact, fact.id)
    assert stored is not None and stored.current_version == 1
    assert stored.value["amount"] == "6000.00"


def test_the_notification_is_not_repeated_for_the_same_version(
    env: KnowledgeEnv, referrer: FakeReferrer
) -> None:
    fact = _fact(env)
    ctx = service_ctx(env)
    for _ in range(2):  # the same event delivered twice
        impact.notify_fact_changed(
            env.session,
            env.clock,
            ctx,
            fact,
            change="value_changed",
            old_display="a",
            new_display="b",
            effects=impact.ChangeEffects(),
        )
    assert len(env.session.scalars(select(Notification)).all()) == 1  # one recipient (manager)


# --- fact_references ----------------------------------------------------------------------


def test_replacing_references_swaps_the_whole_set_and_keeps_one_row_per_fact(
    env: KnowledgeEnv,
) -> None:
    price = _fact(env)
    hours = create_fact(
        env.session,
        env.workspace,
        "booking.instructions",
        {"tr": "Arayın", "en": "Call"},
        clock=env.clock,
    )
    ctx, referrer_id = service_ctx(env), uuid.uuid4()
    impact.replace_references(
        env.session, ctx, "content_item", referrer_id, [(price.id, 1), (hours.id, 1), (price.id, 3)]
    )
    rows = env.session.scalars(select(FactReference)).all()
    assert len(rows) == 2 and {r.fact_id: r.fact_version for r in rows}[price.id] == 3

    impact.replace_references(env.session, ctx, "content_item", referrer_id, [(hours.id, 1)])
    assert [r.fact_id for r in env.session.scalars(select(FactReference))] == [hours.id]
    assert impact.count_references(env.session, ctx, price.id) == 0
    impact.replace_references(env.session, ctx, "content_item", referrer_id, [])
    assert env.session.scalars(select(FactReference)).all() == []


def test_a_reference_cannot_point_at_another_workspaces_fact(env: KnowledgeEnv) -> None:
    other = create_workspace(env.session)
    foreign_fact = create_fact(env.session, other, KEY, money("1"), clock=env.clock)
    env.session.add(
        FactReference(
            workspace_id=env.workspace.id,  # A's row, B's fact
            fact_id=foreign_fact.id,
            fact_version=1,
            referrer_type="reply_draft",
            referrer_id=uuid.uuid4(),
        )
    )
    with pytest.raises(IntegrityError):  # the composite FK (INV-01)
        env.session.flush()
    env.session.rollback()


def test_handlers_register_once_per_referrer_type() -> None:
    with impact.handlers_snapshot(clear=True):
        impact.register_handler(FakeReferrer())  # type: ignore[arg-type]
        with pytest.raises(ValueError, match="already registered"):
            impact.register_handler(FakeReferrer())  # type: ignore[arg-type]
