"""Candidates: staff proposals, discrepancies, contest and resolution (AC-A4; §5)."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import select

from app.audit.service import list_entries
from app.knowledge.models import BusinessFact, FactCandidate, FactVersion
from tests.factories import create_candidate, create_fact, money
from tests.integration.knowledge.conftest import KnowledgeEnv

PRICE_KEY = "pricing.membership_monthly"


def _fact(env: KnowledgeEnv, fact_id: uuid.UUID) -> BusinessFact:
    env.session.expire_all()
    fact = env.session.get(BusinessFact, fact_id)
    assert fact is not None
    return fact


def _candidate(env: KnowledgeEnv, candidate_id: str | uuid.UUID) -> FactCandidate:
    env.session.expire_all()
    found = env.session.get(FactCandidate, uuid.UUID(str(candidate_id)))
    assert found is not None
    return found


def _staff_proposes(env: KnowledgeEnv, fact: BusinessFact, amount: str = "7500") -> dict:  # type: ignore[type-arg]
    response = env.call(
        env.staff,
        "PATCH",
        f"/facts/{fact.id}",
        json={
            "expected_version": fact.current_version,
            "value": {"amount": amount, "unit": "month"},
        },
    )
    assert response.status_code == 202, response.text
    body: dict = response.json()  # type: ignore[type-arg]
    return body


def test_a_staff_edit_becomes_a_contest_candidate_and_the_fact_stays_unchanged(
    env: KnowledgeEnv,
) -> None:
    fact = create_fact(env.session, env.workspace, PRICE_KEY, money())
    candidate = _staff_proposes(env, fact)

    assert candidate["kind"] == "candidate"
    assert (candidate["relation"], candidate["status"]) == ("contest", "pending")
    assert candidate["proposed_display"] == "7.500 ₺ / ay"
    assert candidate["current_display"] == "6.000 ₺ / ay"
    assert candidate["proposed_by_name"] == "Staff User"
    stored = _fact(env, fact.id)
    assert (stored.current_version, stored.value["amount"]) == (1, "6000.00")
    assert (
        len(list(env.session.scalars(select(FactVersion).where(FactVersion.fact_id == fact.id))))
        == 1
    )
    assert (
        len(
            list_entries(
                env.session, workspace_id=env.workspace.id, action="fact_candidate.created"
            )
        )
        == 1
    )
    assert list_entries(env.session, workspace_id=env.workspace.id, action="fact.updated") == []

    # The fact is contested: shown as such, not usable, with one open suggestion.
    [listed] = env.call(env.owner, "GET", "/facts").json()["items"]
    assert (listed["state"], listed["usable"], listed["open_candidates_count"]) == (
        "contested",
        False,
        1,
    )
    assert listed["status"] == "verified"


def test_rejecting_a_contest_makes_the_fact_usable_again(env: KnowledgeEnv) -> None:
    fact = create_fact(env.session, env.workspace, PRICE_KEY, money())
    candidate = _staff_proposes(env, fact)
    response = env.call(env.manager, "POST", f"/fact-candidates/{candidate['id']}/reject")
    assert response.status_code == 200
    assert response.json()["status"] == "rejected"
    [listed] = env.call(env.owner, "GET", "/facts").json()["items"]
    assert (listed["state"], listed["usable"], listed["open_candidates_count"]) == (
        "verified",
        True,
        0,
    )
    assert _candidate(env, candidate["id"]).resolved_by_user_id == env.manager.user.id
    assert (
        len(
            list_entries(
                env.session, workspace_id=env.workspace.id, action="fact_candidate.rejected"
            )
        )
        == 1
    )
    assert _fact(env, fact.id).current_version == 1


def test_accepting_a_contest_applies_the_value_as_a_new_version(env: KnowledgeEnv) -> None:
    fact = create_fact(env.session, env.workspace, PRICE_KEY, money())
    candidate = _staff_proposes(env, fact)
    response = env.call(env.owner, "POST", f"/fact-candidates/{candidate['id']}/accept")
    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["display"], body["current_version"], body["usable"]) == ("7.500 ₺ / ay", 2, True)
    assert body["source_type"] == "candidate_accepted"

    version = env.session.scalars(
        select(FactVersion).where(FactVersion.fact_id == fact.id, FactVersion.version == 2)
    ).one()
    assert (version.source_type, version.source_ref) == ("candidate_accepted", candidate["id"])
    assert _candidate(env, candidate["id"]).status == "accepted"
    assert (
        len(
            list_entries(
                env.session, workspace_id=env.workspace.id, action="fact_candidate.accepted"
            )
        )
        == 1
    )
    assert len(list_entries(env.session, workspace_id=env.workspace.id, action="fact.updated")) == 1


def test_staff_cannot_resolve_candidates(env: KnowledgeEnv) -> None:
    fact = create_fact(env.session, env.workspace, PRICE_KEY, money())
    candidate = _staff_proposes(env, fact)
    for action in ("accept", "reject"):
        response = env.call(env.staff, "POST", f"/fact-candidates/{candidate['id']}/{action}")
        assert response.status_code == 403
    assert _candidate(env, candidate["id"]).status == "pending"


def test_a_candidate_cannot_be_resolved_twice(env: KnowledgeEnv) -> None:
    fact = create_fact(env.session, env.workspace, PRICE_KEY, money())
    candidate = _staff_proposes(env, fact)
    assert (
        env.call(env.owner, "POST", f"/fact-candidates/{candidate['id']}/accept").status_code == 200
    )
    for action in ("accept", "reject"):
        again = env.call(env.owner, "POST", f"/fact-candidates/{candidate['id']}/{action}")
        assert again.status_code == 409
        assert again.json()["code"] == "CONFLICT_STATE"
    assert _fact(env, fact.id).current_version == 2


def test_a_discrepancy_keeps_the_fact_usable_and_explains_itself(env: KnowledgeEnv) -> None:
    fact = create_fact(env.session, env.workspace, PRICE_KEY, money())
    create_candidate(
        env.session, env.workspace, PRICE_KEY, money("5500"), source_type="pasted_text"
    )
    [item] = env.call(env.owner, "GET", "/fact-candidates").json()["items"]
    assert item["relation"] == "discrepancy"
    assert item["source_excerpt"] == "Aylık üyelik 5.500 TL"
    assert (item["proposed_display"], item["current_display"]) == ("5.500 ₺ / ay", "6.000 ₺ / ay")
    assert item["fact_label"]["tr"] == "Aylık üyelik"
    [listed] = env.call(env.owner, "GET", "/facts").json()["items"]
    assert (listed["state"], listed["usable"], listed["open_candidates_count"]) == (
        "verified",
        True,
        1,
    )
    assert _fact(env, fact.id).current_version == 1


def test_a_candidate_equal_to_the_verified_value_is_superseded_straight_away(
    env: KnowledgeEnv,
) -> None:
    create_fact(env.session, env.workspace, PRICE_KEY, money())
    same = create_candidate(env.session, env.workspace, PRICE_KEY, money("6000.00"))
    assert (same.relation, same.status) == ("same", "superseded")
    assert env.call(env.owner, "GET", "/fact-candidates").json()["items"] == []
    assert (
        list_entries(env.session, workspace_id=env.workspace.id, action="fact_candidate.created")
        == []
    )


def test_changing_the_fact_recomputes_pending_relations(env: KnowledgeEnv) -> None:
    fact = create_fact(env.session, env.workspace, PRICE_KEY, money())
    pasted = create_candidate(env.session, env.workspace, PRICE_KEY, money("5500"))
    other = create_candidate(env.session, env.workspace, PRICE_KEY, money("7000"))
    env.call(
        env.owner,
        "PATCH",
        f"/facts/{fact.id}",
        json={"expected_version": 1, "value": {"amount": "5500", "unit": "month"}},
    )
    assert _candidate(env, pasted.id).status == "superseded"  # now equals the fact
    assert (_candidate(env, other.id).status, _candidate(env, other.id).relation) == (
        "pending",
        "discrepancy",
    )


def test_archiving_turns_pending_candidates_into_new_suggestions(env: KnowledgeEnv) -> None:
    fact = create_fact(env.session, env.workspace, PRICE_KEY, money())
    candidate = create_candidate(env.session, env.workspace, PRICE_KEY, money("5500"))
    env.call(env.owner, "POST", f"/facts/{fact.id}/archive", json={"expected_version": 1})
    stored = _candidate(env, candidate.id)
    assert (stored.relation, stored.fact_id) == ("new", None)
    # Accepting it creates the fact again, verified, from the template.
    accepted = env.call(env.owner, "POST", f"/fact-candidates/{candidate.id}/accept")
    assert accepted.status_code == 200
    assert accepted.json()["id"] != str(fact.id)
    assert accepted.json()["label"]["tr"] == "Aylık üyelik"


def test_a_candidate_for_an_unverified_fact_is_new_and_accepting_verifies_it(
    env: KnowledgeEnv,
) -> None:
    fact = create_fact(
        env.session, env.workspace, "pricing.student_monthly", money("4500"), verified=False
    )
    candidate = create_candidate(
        env.session, env.workspace, "pricing.student_monthly", money("4500")
    )
    assert (candidate.relation, candidate.status) == ("new", "pending")
    accepted = env.call(env.owner, "POST", f"/fact-candidates/{candidate.id}/accept")
    assert accepted.json()["status"] == "verified"
    assert accepted.json()["id"] == str(fact.id)
    assert accepted.json()["current_version"] == 2


def test_staff_can_propose_a_missing_template_fact_but_not_custom_or_windowed_ones(
    env: KnowledgeEnv,
) -> None:
    proposal = env.call(
        env.staff,
        "POST",
        "/facts",
        json={"key": PRICE_KEY, "value": {"amount": "6000", "unit": "month"}},
    )
    assert proposal.status_code == 202, proposal.text
    assert (proposal.json()["relation"], proposal.json()["fact_id"]) == ("new", None)
    assert env.call(env.owner, "GET", "/facts").json()["items"] == []  # no fact was created

    custom = env.call(
        env.staff,
        "POST",
        "/facts",
        json={
            "key": "custom.sauna",
            "value_type": "boolean",
            "label": {"tr": "Sauna"},
            "value": {"value": True},
        },
    )
    assert custom.status_code == 403
    pattern = env.call(
        env.staff,
        "POST",
        "/facts",
        json={"key": "service.yoga", "label": {"tr": "Yoga"}, "value": {"tr": "Yoga dersi"}},
    )
    assert pattern.status_code == 403

    fact = create_fact(
        env.session,
        env.workspace,
        "promotion.trial_session",
        {"tr": "Ücretsiz"},
        value_type="localized_text",
        label={"tr": "Deneme"},
    )
    windowed = env.call(
        env.staff,
        "PATCH",
        f"/facts/{fact.id}",
        json={"expected_version": 1, "valid_until": "2026-03-01"},
    )
    assert windowed.status_code == 403
    assert _fact(env, fact.id).valid_until is None


def test_a_newer_proposal_from_the_same_staff_member_supersedes_the_older_one(
    env: KnowledgeEnv,
) -> None:
    fact = create_fact(env.session, env.workspace, PRICE_KEY, money())
    first = _staff_proposes(env, fact, "7500")
    second = _staff_proposes(env, fact, "8000")
    assert _candidate(env, first["id"]).status == "superseded"
    pending = env.call(env.owner, "GET", "/fact-candidates").json()["items"]
    assert [c["id"] for c in pending] == [second["id"]]


def test_a_staff_edit_with_a_stale_version_is_rejected_before_anything_is_stored(
    env: KnowledgeEnv,
) -> None:
    fact = create_fact(env.session, env.workspace, PRICE_KEY, money())
    response = env.call(
        env.staff,
        "PATCH",
        f"/facts/{fact.id}",
        json={"expected_version": 3, "value": {"amount": "1", "unit": "month"}},
    )
    assert response.status_code == 409
    assert response.json()["code"] == "FACT_VERSION_CONFLICT"
    assert env.call(env.owner, "GET", "/fact-candidates").json()["items"] == []


def test_candidate_listing_filters_by_status(env: KnowledgeEnv) -> None:
    create_fact(env.session, env.workspace, PRICE_KEY, money())
    candidate = create_candidate(env.session, env.workspace, PRICE_KEY, money("5500"))
    env.call(env.owner, "POST", f"/fact-candidates/{candidate.id}/reject")
    assert env.call(env.owner, "GET", "/fact-candidates").json()["items"] == []
    rejected = env.call(env.owner, "GET", "/fact-candidates", params={"status": "rejected"}).json()
    assert [c["id"] for c in rejected["items"]] == [str(candidate.id)]
    assert env.call(env.owner, "GET", "/fact-candidates", params={"status": "x"}).status_code == 422


def test_resolution_is_stamped_with_the_injected_clock(env: KnowledgeEnv) -> None:
    create_fact(env.session, env.workspace, PRICE_KEY, money())
    candidate = create_candidate(env.session, env.workspace, PRICE_KEY, money("5500"))
    env.clock.advance(hours=3)
    env.call(env.owner, "POST", f"/fact-candidates/{candidate.id}/reject")
    assert _candidate(env, candidate.id).resolved_at == datetime(2026, 1, 15, 15, 0, tzinfo=UTC)
