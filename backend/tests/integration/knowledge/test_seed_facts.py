"""P2-08: the demo fact seed (realistic, fictional, idempotent) and its readiness result."""

from datetime import date

import pytest
from pydantic import SecretStr
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.audit.models import AuditLog
from app.core.clock import FrozenClock
from app.core.config import Settings
from app.demo.facts_seed import FACT_FILES, load_facts_seed
from app.demo.seed import seed
from app.identity import repository as identity_repo
from app.knowledge import readiness, repository
from app.knowledge.models import BusinessFact, FactCandidate, FactVersion
from tests.factories import knowledge_ctx

pytestmark = pytest.mark.commits


def demo_settings(settings: Settings) -> Settings:
    return settings.model_copy(update={"demo_password": SecretStr("demo-password")})


SessionFactory = sessionmaker[Session]


@pytest.fixture
def seeded(
    session_factory: SessionFactory, clock: FrozenClock, settings: Settings
) -> SessionFactory:
    seed(
        session_factory,
        clock,
        demo_settings(settings),
    )
    return session_factory


def _ctx(session: Session, slug: str):  # type: ignore[no-untyped-def]
    workspace = identity_repo.get_workspace_by_slug(session, slug)
    assert workspace is not None
    return workspace, knowledge_ctx(workspace)


def test_the_gym_has_the_documented_facts(seeded: SessionFactory) -> None:
    with seeded() as session:
        _, ctx = _ctx(session, "golkent-fitness")
        facts = {f.key: f for f in repository.list_facts(session, ctx)}
        assert facts["pricing.membership_monthly"].value == {
            "amount": "6000.00",
            "currency": "TRY",
            "unit": "month",
        }
        assert facts["pricing.membership_monthly"].status == "verified"
        assert facts["pricing.student_monthly"].status == "unverified"  # a non-usable fact
        assert facts["contact.phone"].value["display"] == "0555 000 00 00"
        assert facts["hours.weekly"].value["exceptions"][0]["date"] == "2026-10-29"
        assert {"service.reformer_pilates", "service.fitness", "service.personal_training"} <= set(
            facts
        )
        assert facts["escalation.keywords"].value["items"] == [
            "avukat",
            "tüketici hakem",
            "sakatlandım",
        ]
        # "valid until the end of next month" is computed from the injected clock (15 Jan 2026)
        assert facts["promotion.trial_session"].valid_until == date(2026, 2, 28)


def test_the_gym_has_one_pending_discrepancy_that_is_not_used(seeded: SessionFactory) -> None:
    with seeded() as session:
        _, ctx = _ctx(session, "golkent-fitness")
        [candidate] = repository.list_candidates(session, ctx, status="pending")
        assert candidate.fact_key == "pricing.membership_monthly"
        assert candidate.relation == "discrepancy"
        assert candidate.proposed_value["amount"] == "5500.00"
        assert candidate.source_excerpt == "Instagram bio: Aylık üyelik 5.500 TL"
        assert repository.contested_keys(session, ctx) == set()  # the verified price stays usable


@pytest.mark.parametrize("slug", ["golkent-fitness", "harbor-pilates"])
def test_seeded_workspaces_are_ready(seeded: SessionFactory, clock: FrozenClock, slug: str) -> None:
    with seeded() as session:
        workspace, ctx = _ctx(session, slug)
        report = readiness.readiness(session, clock, ctx)
        unmet = [r.code for r in report.requirements if not r.satisfied]
        assert report.level == "ready"  # Phase 4 connects a simulated account and reviews it
        assert unmet == []
        assert workspace.is_demo


def test_harbor_is_english_and_in_euro(seeded: SessionFactory) -> None:
    with seeded() as session:
        _, ctx = _ctx(session, "harbor-pilates")
        facts = {f.key: f for f in repository.list_facts(session, ctx)}
        assert facts["pricing.reformer_8_sessions"].value["currency"] == "EUR"
        assert facts["pricing.student_monthly"].status == "unverified"
        assert facts["booking.instructions"].value.get("en")
        [candidate] = repository.list_candidates(session, ctx, status="pending")
        assert candidate.relation == "discrepancy"


def test_other_workspace_gets_no_facts(seeded: SessionFactory) -> None:
    with seeded() as session:
        _, ctx = _ctx(session, "other-workspace")
        assert repository.count_facts(session, ctx) == 0


def test_every_fact_has_a_seed_version_and_an_audit_entry(seeded: SessionFactory) -> None:
    with seeded() as session:
        workspace, ctx = _ctx(session, "golkent-fitness")
        facts = repository.count_facts(session, ctx)
        versions = session.scalars(
            select(FactVersion).where(FactVersion.workspace_id == workspace.id)
        ).all()
        assert len(versions) == facts
        assert {(v.source_type, v.version, v.actor_type) for v in versions} == {
            ("seed", 1, "system")
        }
        created = session.scalar(
            select(func.count())
            .select_from(AuditLog)
            .where(AuditLog.workspace_id == workspace.id, AuditLog.action == "fact.created")
        )
        assert created == facts


def test_seeding_twice_adds_nothing(
    seeded: SessionFactory, clock: FrozenClock, settings: Settings
) -> None:
    def totals() -> tuple[int, int, int]:
        with seeded() as session:
            return tuple(  # type: ignore[return-value]
                session.scalar(select(func.count()).select_from(model)) or 0
                for model in (BusinessFact, FactVersion, FactCandidate)
            )

    before = totals()
    report = seed(seeded, clock, demo_settings(settings))
    assert totals() == before
    assert set(report.seeded_facts.values()) == {0}


def test_an_existing_workspace_without_facts_still_receives_them(
    seeded: SessionFactory, clock: FrozenClock, settings: Settings
) -> None:
    """A database seeded in Phase 1 has the workspaces already; the facts must still arrive."""
    with seeded() as session:
        session.execute(delete(BusinessFact))
        session.commit()
    report = seed(seeded, clock, demo_settings(settings))
    assert report.created_workspaces == []
    assert report.seeded_facts["golkent-fitness"] > 10
    with seeded() as session:
        _, ctx = _ctx(session, "golkent-fitness")
        assert repository.count_facts(session, ctx) > 10


def test_reset_recreates_the_facts(
    seeded: SessionFactory, clock: FrozenClock, settings: Settings
) -> None:
    report = seed(
        seeded,
        clock,
        demo_settings(settings),
        reset=True,
    )
    assert report.removed_workspaces == 3
    assert report.seeded_facts["golkent-fitness"] > 10
    with seeded() as session:
        _, ctx = _ctx(session, "golkent-fitness")
        assert len(repository.list_candidates(session, ctx, status="pending")) == 1


def test_seed_files_exist_for_every_registered_workspace() -> None:
    for slug in FACT_FILES:
        assert load_facts_seed(slug).facts
