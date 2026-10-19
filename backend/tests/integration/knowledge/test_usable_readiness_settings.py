"""usable_facts (INV-02, INV-19), readiness API (AC-A5) and the automation-review stamp."""

from datetime import UTC, date, datetime

import pytest
from sqlalchemy.exc import IntegrityError

from app.audit.service import list_entries
from app.knowledge import service
from app.knowledge.models import BusinessFact, FactCandidate, FactVersion
from tests.factories import (
    create_fact,
    create_workspace,
    knowledge_ctx,
    money,
)
from tests.integration.knowledge.conftest import KnowledgeEnv

PRICE_KEY = "pricing.membership_monthly"
DRAFT_FACTS = {
    "identity.business_name": ({"text": "Gölkent"}, {}),
    "contact.phone": ({"e164": "+905550000000"}, {}),
    "location.address": ({"lines": ["Demo Sok. 1"], "city": "Burdur"}, {}),
    "hours.weekly": ({"mon": [["07:00", "23:00"]]}, {}),
}


def _usable_keys(env: KnowledgeEnv, **kwargs: object) -> set[str]:
    ctx = knowledge_ctx(env.workspace)
    return {f.key for f in service.usable_facts(env.session, env.clock, ctx, **kwargs)}  # type: ignore[arg-type]


def test_only_verified_live_in_window_uncontested_facts_are_usable(env: KnowledgeEnv) -> None:
    create_fact(env.session, env.workspace, PRICE_KEY, money())
    create_fact(
        env.session, env.workspace, "pricing.student_monthly", money("4500"), verified=False
    )
    archived = create_fact(env.session, env.workspace, "pricing.single_session", money("300"))
    env.call(env.owner, "POST", f"/facts/{archived.id}/archive", json={"expected_version": 1})
    create_fact(
        env.session,
        env.workspace,
        "promotion.old",
        {"tr": "Bitti"},
        value_type="localized_text",
        label={"tr": "Eski"},
        valid_until=date(2026, 1, 1),
    )
    create_fact(env.session, env.workspace, "booking.instructions", {"tr": "Arayın"})
    contested = create_fact(
        env.session, env.workspace, "pricing.membership_3_months", money("16500")
    )
    env.call(
        env.staff,
        "PATCH",
        f"/facts/{contested.id}",
        json={"expected_version": 1, "value": {"amount": "99", "unit": "month"}},
    )
    assert _usable_keys(env) == {PRICE_KEY, "booking.instructions"}
    assert _usable_keys(env, categories=("pricing",)) == {PRICE_KEY}


def test_usable_facts_carry_a_rendered_display_and_a_placeholder(env: KnowledgeEnv) -> None:
    create_fact(env.session, env.workspace, PRICE_KEY, money())
    ctx = knowledge_ctx(env.workspace)
    [fact] = service.usable_facts(env.session, env.clock, ctx)
    assert (fact.display, fact.placeholder, fact.version) == (
        "6.000 ₺ / ay",
        "{{fact:pricing.membership_monthly}}",
        1,
    )
    [english] = service.usable_facts(env.session, env.clock, ctx, locale="en")
    assert english.display == "TRY 6,000 / month"


def test_a_promotion_ends_at_the_end_of_the_workspace_local_day(env: KnowledgeEnv) -> None:
    create_fact(
        env.session,
        env.workspace,
        "promotion.trial",
        {"tr": "Ücretsiz"},
        value_type="localized_text",
        label={"tr": "Deneme"},
        valid_until=date(2026, 10, 29),
    )
    # 29 Oct 20:59 UTC = 23:59 in Istanbul (UTC+3): still valid. One hour later it is 30 Oct there.
    env.clock.advance(datetime(2026, 10, 29, 20, 59, tzinfo=UTC) - env.clock.now())
    assert _usable_keys(env) == {"promotion.trial"}
    env.clock.advance(hours=1)
    assert _usable_keys(env) == set()
    # An explicit date overrides "today" (used for scheduled content):
    assert _usable_keys(env, on_date=date(2026, 10, 29)) == {"promotion.trial"}


def test_a_non_utc_workspace_in_dst_uses_its_own_local_date() -> None:
    from app.knowledge.usability import local_today

    # Europe/Lisbon is UTC+1 in July: 23:30 UTC on 1 July is already 2 July locally.
    assert local_today(datetime(2026, 7, 1, 23, 30, tzinfo=UTC), "Europe/Lisbon") == date(
        2026, 7, 2
    )


# --- readiness ------------------------------------------------------------------------------


def test_readiness_api_lists_what_is_missing_then_reaches_ready_for_drafts(
    env: KnowledgeEnv,
) -> None:
    """AC-A5."""
    first = env.call(env.owner, "GET", "/readiness").json()
    assert first["level"] == "not_ready"
    codes = {r["code"]: r for r in first["requirements"]}
    assert codes["hours"]["satisfied"] is False
    assert codes["hours"]["missing_keys"] == ["hours.weekly"]
    assert codes["hours"]["link"] == {
        "target": "knowledge",
        "category": "hours",
        "key": "hours.weekly",
    }
    assert codes["account_connected"]["status"] == "not_connected"
    assert codes["automation_reviewed"]["status"] == "not_reviewed"

    for key, (value, extra) in DRAFT_FACTS.items():
        create_fact(env.session, env.workspace, key, value, **extra)
    second = env.call(env.staff, "GET", "/readiness").json()  # any member may read it
    assert second["level"] == "ready_for_drafts"
    assert [r["code"] for r in second["requirements"] if not r["satisfied"]] == [
        "booking_instructions",
        "price_policy",
        "services",
        "account_connected",
        "automation_reviewed",
    ]


def test_a_contested_required_fact_lowers_readiness_until_resolved(env: KnowledgeEnv) -> None:
    for key, (value, extra) in DRAFT_FACTS.items():
        create_fact(env.session, env.workspace, key, value, **extra)
    assert env.call(env.owner, "GET", "/readiness").json()["level"] == "ready_for_drafts"
    name = env.call(env.owner, "GET", "/facts", params={"category": "identity"}).json()["items"][0]
    contest = env.call(
        env.staff,
        "PATCH",
        f"/facts/{name['id']}",
        json={"expected_version": 1, "value": {"text": "Başka ad"}},
    )
    assert env.call(env.owner, "GET", "/readiness").json()["level"] == "not_ready"
    env.call(env.owner, "POST", f"/fact-candidates/{contest.json()['id']}/reject")
    assert env.call(env.owner, "GET", "/readiness").json()["level"] == "ready_for_drafts"


# --- automation_reviewed_at is server-stamped by the policy review (Phase 4) -----------------


def test_automation_review_cannot_be_forged_through_the_workspace_settings(
    env: KnowledgeEnv,
) -> None:
    for settings in (
        {"automation_reviewed_at": "2020-01-01T00:00:00Z"},
        {"automation_reviewed": True},  # the Phase 2 stand-in is gone
    ):
        response = env.call(env.owner, "PATCH", "", json={"settings": settings})
        assert response.status_code == 422
    assert list_entries(env.session, workspace_id=env.workspace.id, action="policy.reviewed") == []


# --- database-level guarantees (INV-01, INV-17) ----------------------------------------------


def _insert(env: KnowledgeEnv, row: object) -> None:
    """Add ``row`` in a savepoint so a violated constraint does not poison the test session."""
    with env.session.begin_nested():
        env.session.add(row)
        env.session.flush()


def test_a_version_or_candidate_cannot_reference_a_fact_of_another_workspace(
    env: KnowledgeEnv,
) -> None:
    other = create_workspace(env.session, name="Other", slug="other-ws")
    foreign_fact = create_fact(env.session, other, PRICE_KEY, money())
    version = FactVersion(
        workspace_id=env.workspace.id,
        fact_id=foreign_fact.id,
        version=9,
        value={},
        status="verified",
        source_type="seed",
        actor_type="system",
        change_kind="created",
    )
    candidate = FactCandidate(
        workspace_id=env.workspace.id,
        fact_id=foreign_fact.id,
        fact_key=PRICE_KEY,
        proposed_value={},
        value_type="money",
        source_type="pasted_text",
        relation="new",
        status="pending",
        proposed_by_actor_type="system",
    )
    with pytest.raises(IntegrityError):
        _insert(env, version)
    with pytest.raises(IntegrityError):
        _insert(env, candidate)


def test_only_one_live_fact_per_key_is_allowed_by_the_database(env: KnowledgeEnv) -> None:
    create_fact(env.session, env.workspace, PRICE_KEY, money())
    duplicate = BusinessFact(
        workspace_id=env.workspace.id,
        key=PRICE_KEY,
        category="pricing",
        label={},
        value_type="money",
        value={},
        status="unverified",
        criticality="critical",
        current_version=1,
    )
    with pytest.raises(IntegrityError):
        _insert(env, duplicate)
