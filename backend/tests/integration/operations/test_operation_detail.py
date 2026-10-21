"""``GET /workspaces/{ws}/operations/{id}`` (api-design.md section 2.8): the failure explanation
of one operation for the owner and the manager, never a provider payload."""

import uuid
from datetime import timedelta
from typing import Any

import pytest

from app.integrations.instagram.models import SocialAccount
from app.operations.models import Operation
from tests.helpers.content import connect_account
from tests.helpers.env import Env

EXPECTED_KEYS = {
    "id",
    "type",
    "status",
    "attempts",
    "last_error_code",
    "what",
    "next",
    "subject_type",
    "subject_id",
    "created_at",
    "completed_at",
    "is_simulated",
}


def make_operation(env: Env, account: SocialAccount | None = None, **fields: Any) -> Operation:
    account = account or connect_account(env)
    values: dict[str, Any] = {
        "workspace_id": env.workspace.id,
        "operation_type": "send_reply",
        "idempotency_key": f"send_reply:{uuid.uuid4()}",
        "subject_type": "reply_draft",
        "subject_id": uuid.uuid4(),
        "social_account_id": account.id,
        "provider_kind": "mock",
        "status": "failed",
        "attempts": 3,
        "last_error_code": "OUTCOME_UNCONFIRMED",
        "last_error_detail": "provider said: access token ABC expired",
        "provider_ref": {"recipient_id": "customer-123", "text_sha256": "f" * 64},
        "result": {"raw": "provider payload"},
        "completed_at": env.clock.now() - timedelta(minutes=5),
        "is_simulated": True,
    }
    operation = Operation(**{**values, **fields})
    env.session.add(operation)
    env.session.commit()
    return operation


def test_a_failed_reply_is_explained_in_the_readers_language(env: Env) -> None:
    operation = make_operation(env)
    response = env.call(env.owner, "GET", f"/operations/{operation.id}")
    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body) == EXPECTED_KEYS
    assert body["id"] == str(operation.id)
    assert (body["type"], body["status"], body["attempts"]) == ("send_reply", "failed", 3)
    assert body["last_error_code"] == "OUTCOME_UNCONFIRMED"
    assert body["what"] == "Yanıtın müşteriye ulaşıp ulaşmadığını doğrulayamadık."
    assert body["next"] == "Yeniden göndermeden önce Instagram'daki konuşmayı kontrol edin."
    assert body["subject_type"] == "reply_draft" and body["subject_id"] == str(operation.subject_id)
    assert body["is_simulated"] is True  # INV-09
    assert body["completed_at"] is not None and body["created_at"] is not None

    env.owner.user.ui_locale = "en"
    env.session.commit()
    english = env.call(env.owner, "GET", f"/operations/{operation.id}").json()
    assert english["what"] == "We could not confirm that the reply reached the customer."


def test_no_provider_data_reaches_the_response(env: Env) -> None:
    operation = make_operation(env)
    text = env.call(env.owner, "GET", f"/operations/{operation.id}").text
    for secret in ("access token", "ABC", "customer-123", "provider payload", "f" * 64):
        assert secret not in text
    for column in ("provider_ref", "result", "last_error_detail", "idempotency_key", "correlation"):
        assert column not in text


def test_the_manager_may_read_it_and_staff_may_not(env: Env) -> None:
    operation = make_operation(env)
    assert env.call(env.manager, "GET", f"/operations/{operation.id}").status_code == 200
    denied = env.call(env.staff, "GET", f"/operations/{operation.id}")
    assert denied.status_code == 403 and denied.json()["code"] == "FORBIDDEN"


def test_an_operation_that_is_not_in_trouble_has_no_explanation(env: Env) -> None:
    operation = make_operation(env, status="succeeded", last_error_code=None)
    body = env.call(env.owner, "GET", f"/operations/{operation.id}").json()
    assert body["status"] == "succeeded" and body["what"] is None and body["next"] is None


def test_an_unknown_outcome_reads_as_still_checking(env: Env) -> None:
    operation = make_operation(env, status="outcome_unknown", last_error_code=None)
    body = env.call(env.owner, "GET", f"/operations/{operation.id}").json()
    assert body["what"] == "Yanıtın müşteriye ulaşıp ulaşmadığını hâlâ kontrol ediyoruz."


def test_a_post_operation_uses_the_shared_texts(env: Env) -> None:
    operation = make_operation(
        env,
        operation_type="publish_content",
        subject_type="content_item",
        last_error_code="MEDIA_REJECTED",
    )
    body = env.call(env.owner, "GET", f"/operations/{operation.id}").json()
    assert body["what"] == "Instagram görseli işleyemedi."


def test_an_unknown_id_is_a_404(env: Env) -> None:
    response = env.call(env.owner, "GET", f"/operations/{uuid.uuid4()}")
    assert response.status_code == 404 and response.json()["code"] == "NOT_FOUND"
    assert env.call(env.owner, "GET", "/operations/not-a-uuid").status_code == 422


@pytest.mark.parametrize("role", ["owner", "manager"])
def test_the_operation_of_another_workspace_is_a_404(env: Env, role: str) -> None:
    from tests.factories import workspace_with_members

    other, _ = workspace_with_members(env.session, roles=("owner",), slug="other")
    account = SocialAccount(
        workspace_id=other.id,
        platform="instagram",
        provider_kind="mock",
        external_account_id="mock-other",
        username="other.demo",
        status="connected",
        capabilities={},
    )
    env.session.add(account)
    env.session.flush()
    foreign = Operation(
        workspace_id=other.id,
        operation_type="send_reply",
        idempotency_key=f"send_reply:{uuid.uuid4()}",
        subject_type="reply_draft",
        subject_id=uuid.uuid4(),
        social_account_id=account.id,
        provider_kind="mock",
        status="failed",
        last_error_code="OUTCOME_UNCONFIRMED",
        is_simulated=True,
    )
    env.session.add(foreign)
    env.session.commit()
    caller = env.owner if role == "owner" else env.manager
    response = env.call(caller, "GET", f"/operations/{foreign.id}")
    assert response.status_code == 404 and response.json()["code"] == "NOT_FOUND"
