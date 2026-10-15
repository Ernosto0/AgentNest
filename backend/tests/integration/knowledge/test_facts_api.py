"""Fact lifecycle through the HTTP API: create, update, verify, archive, restore (AC-A2…A4)."""

import uuid

import pytest
from sqlalchemy import select

from app.audit.service import list_entries
from app.knowledge.models import BusinessFact, FactVersion
from tests.factories import create_fact, money
from tests.integration.knowledge.conftest import KnowledgeEnv

PRICE_KEY = "pricing.membership_monthly"


def _versions(env: KnowledgeEnv, fact_id: uuid.UUID | str) -> list[FactVersion]:
    env.session.expire_all()
    return list(
        env.session.scalars(
            select(FactVersion)
            .where(FactVersion.fact_id == uuid.UUID(str(fact_id)))
            .order_by(FactVersion.version)
        )
    )


def _audit(env: KnowledgeEnv, action: str) -> int:
    return len(list_entries(env.session, workspace_id=env.workspace.id, action=action))


def test_owner_creates_a_verified_fact_with_version_and_audit(env: KnowledgeEnv) -> None:
    response = env.call(
        env.owner,
        "POST",
        "/facts",
        json={"key": PRICE_KEY, "value": {"amount": "6000", "unit": "month"}},
    )
    assert response.status_code == 201, response.text
    fact = response.json()
    assert fact["kind"] == "fact"
    assert fact["value"] == {"amount": "6000.00", "currency": "TRY", "unit": "month"}
    assert fact["display"] == "6.000 ₺ / ay"
    assert (fact["status"], fact["state"], fact["usable"]) == ("verified", "verified", True)
    assert fact["current_version"] == 1
    assert fact["category"] == "pricing"
    assert fact["label"]["tr"] == "Aylık üyelik"
    # AC-A2: a verified fact shows its source and last-verified date
    assert fact["source_type"] == "owner_entry"
    assert fact["last_verified_at"] is not None
    assert fact["last_verified_by_name"] == "Owner User"

    [version] = _versions(env, fact["id"])
    assert (version.version, version.change_kind, version.status) == (1, "created", "verified")
    assert _audit(env, "fact.created") == 1


def test_display_follows_the_users_ui_locale(env: KnowledgeEnv) -> None:
    create_fact(env.session, env.workspace, PRICE_KEY, money())
    patched = env.owner.client.patch(
        "/api/v1/auth/me", json={"ui_locale": "en"}, headers=env.owner.headers
    )
    assert patched.status_code == 200
    [fact] = env.call(env.owner, "GET", "/facts").json()["items"]
    assert fact["display"] == "TRY 6,000 / month"
    [staff_view] = env.call(env.staff, "GET", "/facts").json()["items"]
    assert staff_view["display"] == "6.000 ₺ / ay"


def test_update_creates_exactly_one_version_and_one_audit_entry(env: KnowledgeEnv) -> None:
    fact = create_fact(env.session, env.workspace, PRICE_KEY, money())
    first_snapshot = dict(_versions(env, fact.id)[0].value)

    response = env.call(
        env.manager,
        "PATCH",
        f"/facts/{fact.id}",
        json={"expected_version": 1, "value": {"amount": "7000", "unit": "month"}, "reason": "Zam"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["current_version"] == 2
    assert response.json()["display"] == "7.000 ₺ / ay"

    versions = _versions(env, fact.id)
    assert [v.version for v in versions] == [1, 2]
    assert versions[0].value == first_snapshot  # INV-17: history is never rewritten
    assert (versions[1].change_kind, versions[1].reason) == ("value_changed", "Zam")
    assert _audit(env, "fact.updated") == 1
    entry = list_entries(env.session, workspace_id=env.workspace.id, action="fact.updated")[0]
    assert entry.metadata_["old_display"] == "6.000 ₺ / ay"
    assert entry.metadata_["new_display"] == "7.000 ₺ / ay"


def test_saving_the_same_value_changes_nothing(env: KnowledgeEnv) -> None:
    fact = create_fact(env.session, env.workspace, PRICE_KEY, money())
    response = env.call(
        env.owner,
        "PATCH",
        f"/facts/{fact.id}",
        json={"expected_version": 1, "value": {"amount": "6000.00", "unit": "month"}},
    )
    assert response.status_code == 200
    assert response.json()["current_version"] == 1
    assert len(_versions(env, fact.id)) == 1
    assert _audit(env, "fact.updated") == 0


def test_stale_expected_version_is_a_conflict_and_changes_nothing(env: KnowledgeEnv) -> None:
    fact = create_fact(env.session, env.workspace, PRICE_KEY, money())
    response = env.call(
        env.owner,
        "PATCH",
        f"/facts/{fact.id}",
        json={"expected_version": 5, "value": {"amount": "9999", "unit": "month"}},
    )
    assert response.status_code == 409
    assert response.json()["code"] == "FACT_VERSION_CONFLICT"
    assert response.json()["params"]["current_version"] == 1
    assert len(_versions(env, fact.id)) == 1


def test_verifying_an_unverified_fact(env: KnowledgeEnv) -> None:
    """AC-A3."""
    fact = create_fact(
        env.session, env.workspace, "pricing.student_monthly", money("4500"), verified=False
    )
    listed = env.call(env.owner, "GET", "/facts").json()["items"][0]
    assert (listed["status"], listed["usable"]) == ("unverified", False)

    response = env.call(
        env.manager, "POST", f"/facts/{fact.id}/verify", json={"expected_version": 1}
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["status"], body["usable"], body["current_version"]) == ("verified", True, 2)
    assert body["last_verified_by_name"] == "Manager User"

    versions = _versions(env, fact.id)
    assert [(v.version, v.change_kind, v.status) for v in versions] == [
        (1, "created", "unverified"),
        (2, "verified", "verified"),
    ]
    assert _audit(env, "fact.verified") == 1
    assert _audit(env, "fact.updated") == 0


def test_verifying_twice_is_a_conflict(env: KnowledgeEnv) -> None:
    fact = create_fact(env.session, env.workspace, PRICE_KEY, money())
    response = env.call(env.owner, "POST", f"/facts/{fact.id}/verify", json={"expected_version": 1})
    assert response.status_code == 409
    assert response.json()["code"] == "CONFLICT_STATE"


def test_editing_an_unverified_fact_as_a_verifier_verifies_it(env: KnowledgeEnv) -> None:
    fact = create_fact(env.session, env.workspace, PRICE_KEY, money("5000"), verified=False)
    response = env.call(
        env.owner,
        "PATCH",
        f"/facts/{fact.id}",
        json={"expected_version": 1, "value": {"amount": "6000", "unit": "month"}},
    )
    assert response.json()["status"] == "verified"
    assert [v.change_kind for v in _versions(env, fact.id)] == ["created", "value_changed"]
    assert _audit(env, "fact.updated") == 1


def test_staff_cannot_verify(env: KnowledgeEnv) -> None:
    """AC-A4: 403 FORBIDDEN and nothing changes."""
    fact = create_fact(env.session, env.workspace, PRICE_KEY, money(), verified=False)
    response = env.call(env.staff, "POST", f"/facts/{fact.id}/verify", json={"expected_version": 1})
    assert response.status_code == 403
    assert response.json()["code"] == "FORBIDDEN"
    env.session.expire_all()
    assert env.session.get(BusinessFact, fact.id).status == "unverified"  # type: ignore[union-attr]
    assert len(_versions(env, fact.id)) == 1
    assert _audit(env, "fact.verified") == 0


def test_staff_cannot_archive_or_restore_either(env: KnowledgeEnv) -> None:
    fact = create_fact(env.session, env.workspace, PRICE_KEY, money())
    for action in ("archive", "restore"):
        response = env.call(
            env.staff, "POST", f"/facts/{fact.id}/{action}", json={"expected_version": 1}
        )
        assert response.status_code == 403


def test_archive_frees_the_key_and_restore_needs_a_free_key(env: KnowledgeEnv) -> None:
    fact = create_fact(env.session, env.workspace, PRICE_KEY, money())
    archived = env.call(
        env.owner, "POST", f"/facts/{fact.id}/archive", json={"expected_version": 1}
    )
    assert (archived.json()["status"], archived.json()["usable"]) == ("archived", False)
    assert _audit(env, "fact.archived") == 1
    assert (
        env.call(
            env.owner,
            "PATCH",
            f"/facts/{fact.id}",
            json={"expected_version": 2, "value": {"amount": "1", "unit": "month"}},
        ).status_code
        == 409
    )

    replacement = env.call(
        env.owner,
        "POST",
        "/facts",
        json={"key": PRICE_KEY, "value": {"amount": "7000", "unit": "month"}},
    )
    assert replacement.status_code == 201  # the key was free
    blocked = env.call(env.owner, "POST", f"/facts/{fact.id}/restore", json={"expected_version": 2})
    assert blocked.status_code == 409
    assert blocked.json()["code"] == "CONFLICT_STATE"


def test_restore_returns_an_unverified_fact_that_must_be_verified_again(env: KnowledgeEnv) -> None:
    fact = create_fact(env.session, env.workspace, PRICE_KEY, money())
    env.call(env.owner, "POST", f"/facts/{fact.id}/archive", json={"expected_version": 1})
    restored = env.call(
        env.owner, "POST", f"/facts/{fact.id}/restore", json={"expected_version": 2}
    )
    assert (restored.json()["status"], restored.json()["usable"]) == ("unverified", False)
    verified = env.call(env.owner, "POST", f"/facts/{fact.id}/verify", json={"expected_version": 3})
    assert verified.json()["status"] == "verified"
    assert [v.change_kind for v in _versions(env, fact.id)] == [
        "created",
        "archived",
        "restored",
        "verified",
    ]
    assert (_audit(env, "fact.archived"), _audit(env, "fact.restored")) == (1, 1)


def test_version_history_is_listed_newest_first(env: KnowledgeEnv) -> None:
    fact = create_fact(env.session, env.workspace, PRICE_KEY, money())
    env.call(
        env.owner,
        "PATCH",
        f"/facts/{fact.id}",
        json={"expected_version": 1, "value": {"amount": "7000", "unit": "month"}},
    )
    items = env.call(env.owner, "GET", f"/facts/{fact.id}/versions").json()["items"]
    assert [i["version"] for i in items] == [2, 1]
    assert items[0]["display"] == "7.000 ₺ / ay"
    assert items[0]["actor_name"] == "Owner User"
    assert items[1]["source_type"] == "seed"


def test_validation_errors_are_field_errors(env: KnowledgeEnv) -> None:
    bad_value = env.call(
        env.owner, "POST", "/facts", json={"key": PRICE_KEY, "value": {"amount": "-5"}}
    )
    assert bad_value.status_code == 422
    assert {e["field"] for e in bad_value.json()["errors"]} == {"value.amount"}

    unknown = env.call(
        env.owner, "POST", "/facts", json={"key": "nonsense.key", "value": {"text": "x"}}
    )
    assert unknown.status_code == 422
    assert unknown.json()["errors"][0] == {"field": "key", "code": "unknown_key", "params": {}}

    wrong_type = env.call(
        env.owner,
        "POST",
        "/facts",
        json={"key": PRICE_KEY, "value_type": "text", "value": {"text": "x"}},
    )
    assert wrong_type.json()["errors"][0]["field"] == "value_type"

    no_label = env.call(
        env.owner, "POST", "/facts", json={"key": "service.fitness", "value": {"tr": "Fitness"}}
    )
    assert no_label.json()["errors"][0] == {"field": "label", "code": "required", "params": {}}


def test_pattern_and_custom_keys_need_a_label(env: KnowledgeEnv) -> None:
    service = env.call(
        env.owner,
        "POST",
        "/facts",
        json={
            "key": "service.fitness",
            "label": {"tr": "Fitness"},
            "value": {"tr": "Fitness salonu"},
        },
    )
    assert service.status_code == 201
    assert service.json()["label"] == {"tr": "Fitness", "en": "Fitness"}
    custom = env.call(
        env.owner,
        "POST",
        "/facts",
        json={
            "key": "custom.parking",
            "value_type": "boolean",
            "label": {"tr": "Otopark", "en": "Parking"},
            "criticality": "critical",
            "value": {"value": True},
        },
    )
    assert custom.status_code == 201
    assert (custom.json()["category"], custom.json()["criticality"]) == ("custom", "critical")


def test_duplicate_keys_are_a_conflict(env: KnowledgeEnv) -> None:
    create_fact(env.session, env.workspace, PRICE_KEY, money())
    response = env.call(
        env.owner,
        "POST",
        "/facts",
        json={"key": PRICE_KEY, "value": {"amount": "1", "unit": "month"}},
    )
    assert response.status_code == 409
    assert response.json()["code"] == "CONFLICT_STATE"
    assert response.json()["params"]["reason"] == "key_exists"


@pytest.mark.parametrize(
    ("valid_until", "expected_state"), [("2026-01-14", "expired"), ("2026-01-15", "verified")]
)
def test_validity_windows_use_the_workspace_local_date(
    env: KnowledgeEnv, valid_until: str, expected_state: str
) -> None:
    # FrozenClock: 2026-01-15 12:00 UTC = 15 Jan in Europe/Istanbul
    response = env.call(
        env.owner,
        "POST",
        "/facts",
        json={
            "key": "promotion.trial_session",
            "value_type": "localized_text",
            "label": {"tr": "Deneme seansı"},
            "value": {"tr": "İlk seans ücretsiz"},
            "valid_until": valid_until,
        },
    )
    assert response.status_code == 201, response.text
    assert response.json()["state"] == expected_state
    assert response.json()["usable"] is (expected_state == "verified")


def test_changing_a_validity_window_is_a_versioned_change(env: KnowledgeEnv) -> None:
    fact = create_fact(
        env.session,
        env.workspace,
        "promotion.trial_session",
        {"tr": "Ücretsiz"},
        value_type="localized_text",
        label={"tr": "Deneme"},
    )
    response = env.call(
        env.owner,
        "PATCH",
        f"/facts/{fact.id}",
        json={"expected_version": 1, "valid_until": "2026-02-28"},
    )
    assert response.status_code == 200
    versions = _versions(env, fact.id)
    assert [v.valid_until for v in versions] == [None, versions[1].valid_until]
    assert str(versions[1].valid_until) == "2026-02-28"
    cleared = env.call(
        env.owner, "PATCH", f"/facts/{fact.id}", json={"expected_version": 2, "valid_until": None}
    )
    assert cleared.json()["valid_until"] is None
    invalid = env.call(
        env.owner,
        "PATCH",
        f"/facts/{fact.id}",
        json={"expected_version": 3, "valid_from": "2026-03-01", "valid_until": "2026-02-01"},
    )
    assert invalid.status_code == 422


def test_listing_filters_and_template_checklist(env: KnowledgeEnv) -> None:
    create_fact(env.session, env.workspace, PRICE_KEY, money())
    create_fact(
        env.session, env.workspace, "pricing.student_monthly", money("4500"), verified=False
    )
    create_fact(env.session, env.workspace, "identity.business_name", {"text": "Gölkent"})
    by_category = env.call(env.owner, "GET", "/facts", params={"category": "pricing"}).json()
    assert {i["key"] for i in by_category["items"]} == {PRICE_KEY, "pricing.student_monthly"}
    assert by_category["next_cursor"] is None
    unverified = env.call(env.owner, "GET", "/facts", params={"status": "unverified"}).json()
    assert [i["key"] for i in unverified["items"]] == ["pricing.student_monthly"]
    assert env.call(env.owner, "GET", "/facts", params={"category": "bogus"}).status_code == 422

    checklist = {i["identifier"]: i for i in env.call(env.owner, "GET", "/facts/template").json()}
    assert checklist["identity.business_name"]["status"] == "verified"
    assert checklist["pricing.student_monthly"]["status"] == "unverified"
    assert checklist["hours.weekly"]["status"] == "missing"
    assert checklist["service.*"]["status"] == "missing"
    create_fact(
        env.session,
        env.workspace,
        "service.fitness",
        {"tr": "x"},
        value_type="localized_text",
        label={"tr": "Fitness"},
    )
    again = {i["identifier"]: i for i in env.call(env.owner, "GET", "/facts/template").json()}
    assert again["service.*"]["status"] == "present"
    assert len(again["service.*"]["fact_ids"]) == 1


def test_staff_can_read_but_a_non_member_cannot(env: KnowledgeEnv, make_client) -> None:  # type: ignore[no-untyped-def]
    from tests.factories import create_user, login

    create_fact(env.session, env.workspace, PRICE_KEY, money())
    assert env.call(env.staff, "GET", "/facts").status_code == 200
    stranger = create_user(env.session)
    client = make_client()
    headers = login(client, stranger)
    response = client.get(f"{env.base}/facts", headers=headers)
    assert response.status_code == 404


def test_every_change_is_attributed_in_the_audit_log(env: KnowledgeEnv) -> None:
    env.call(
        env.owner,
        "POST",
        "/facts",
        json={"key": PRICE_KEY, "value": {"amount": "6000", "unit": "month"}},
    )
    [entry] = list_entries(env.session, workspace_id=env.workspace.id, action="fact.created")
    assert entry.actor_type == "user"
    assert entry.actor_id == str(env.owner.user.id)
    assert entry.resource_type == "business_fact"
    assert entry.metadata_["key"] == PRICE_KEY
