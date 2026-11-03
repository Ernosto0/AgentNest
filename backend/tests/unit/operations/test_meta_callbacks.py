"""Unit tests for Phase 8 Session 11: Meta Deauthorization and Data-Deletion Callbacks.

Covers:
- Strict signed_request HMAC-SHA256 signature verification and bounded size.
- Refusal of invalid signatures, malformed payloads, and unsupported algorithms.
- Audit emission of webhook.signature_invalid upon verification failure.
- Deauthorization lifecycle: revoking credentials, disconnecting account,
  pausing agent, emitting audit.
- Deauthorization of unknown or already-disconnected account without leaking existence.
- Data-deletion request lifecycle: resolving account or customer identity via server-owned records.
- Routing through Session 10 erasure orchestration (INV-05 reconciliation pending vs completed).
- Generation of unguessable confirmation codes and idempotent replay handling.
- Anticipatory tombstone creation for unknown identities to prevent backup-restore resurrection.
- Privacy-preserving status queries (never echoing PII, IDs, or message contents).
- Dual-format status response: JSON API response and bilingual (TR/EN) HTML status page.
- TestClient coverage for both /api/v1/webhooks/meta/... and /webhooks/meta/... routes.
"""

import base64
import hashlib
import hmac
import json
import uuid
from datetime import UTC, datetime
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.agent.models import AccountAgent
from app.core.clock import FrozenClock
from app.core.config import Settings
from app.integrations.instagram.models import SocialAccount
from app.main import create_app
from app.memory.models import CustomerIdentity
from app.operations.meta_callbacks import (
    InvalidSignatureError,
    InvalidSignedRequestError,
    get_data_deletion_status,
    handle_data_deletion_request,
    handle_deauthorization,
    parse_and_verify_signed_request,
)
from app.operations.models import DataDeletionRequest, DeletionTombstone

MOCK_SECRET = "test-meta-secret-32-chars-long-1234"


def make_signed_request(payload: dict[str, Any], secret: str = MOCK_SECRET) -> str:
    """Helper to construct a valid base64url signed_request."""
    payload_json = json.dumps(payload, separators=(",", ":"))
    payload_b64 = base64.urlsafe_b64encode(payload_json.encode("utf-8")).decode("utf-8").rstrip("=")
    sig = hmac.new(secret.encode("utf-8"), payload_b64.encode("utf-8"), hashlib.sha256).digest()
    sig_b64 = base64.urlsafe_b64encode(sig).decode("utf-8").rstrip("=")
    return f"{sig_b64}.{payload_b64}"


def test_parse_and_verify_valid_signed_request() -> None:
    payload = {
        "user_id": "meta_user_12345",
        "algorithm": "HMAC-SHA256",
        "issued_at": 1600000000,
    }
    signed_req = make_signed_request(payload, MOCK_SECRET)
    parsed = parse_and_verify_signed_request(signed_req, MOCK_SECRET)
    assert parsed["user_id"] == "meta_user_12345"
    assert parsed["algorithm"] == "HMAC-SHA256"


def test_parse_and_verify_invalid_signature() -> None:
    payload = {
        "user_id": "meta_user_12345",
        "algorithm": "HMAC-SHA256",
    }
    signed_req = make_signed_request(payload, MOCK_SECRET)
    # Tamper with the secret
    with pytest.raises(InvalidSignatureError, match="Signature mismatch"):
        parse_and_verify_signed_request(signed_req, "wrong-secret")


def test_parse_and_verify_malformed_requests() -> None:
    # 1. No dot separator
    with pytest.raises(InvalidSignedRequestError, match="exactly two parts"):
        parse_and_verify_signed_request("notavalidsignedrequest", MOCK_SECRET)

    # 2. Empty string
    with pytest.raises(InvalidSignedRequestError, match="empty or exceeds"):
        parse_and_verify_signed_request("", MOCK_SECRET)

    # 3. Oversized string
    with pytest.raises(InvalidSignedRequestError, match="empty or exceeds"):
        parse_and_verify_signed_request("a" * 20000, MOCK_SECRET)

    # 4. Invalid algorithm
    bad_algo = make_signed_request({"user_id": "u1", "algorithm": "HMAC-SHA1"}, MOCK_SECRET)
    with pytest.raises(InvalidSignedRequestError, match="Unsupported signature algorithm"):
        parse_and_verify_signed_request(bad_algo, MOCK_SECRET)

    # 5. Missing user_id
    missing_user = make_signed_request({"algorithm": "HMAC-SHA256"}, MOCK_SECRET)
    with pytest.raises(InvalidSignedRequestError, match="missing user_id"):
        parse_and_verify_signed_request(missing_user, MOCK_SECRET)


def test_handle_deauthorization_disconnects_connected_account() -> None:
    session = MagicMock()
    clock = FrozenClock(datetime(2026, 11, 3, 12, 0, tzinfo=UTC))
    settings = Settings(meta_app_secret=SecretStr(MOCK_SECRET))

    user_id = "meta_owner_1001"
    ws_id = uuid.uuid4()
    account_id = uuid.uuid4()

    acc = MagicMock(spec=SocialAccount)
    acc.id = account_id
    acc.workspace_id = ws_id
    acc.external_account_id = user_id
    acc.status = "connected"
    acc.token_ciphertext = b"encrypted"
    acc.capabilities = {"messages": True}

    agent = MagicMock(spec=AccountAgent)
    agent.workspace_id = ws_id
    agent.social_account_id = account_id
    agent.state = "active"

    # Mock DB query for SocialAccount and AccountAgent
    session.execute.return_value.scalars.return_value.all.return_value = [acc]
    session.execute.return_value.scalar_one_or_none.return_value = agent

    signed_req = make_signed_request({"user_id": user_id, "algorithm": "HMAC-SHA256"}, MOCK_SECRET)
    result = handle_deauthorization(session, clock, settings, signed_req)

    assert result == {"status": "ok"}
    assert acc.status == "disconnected"
    assert acc.token_ciphertext is None
    assert acc.capabilities == {}
    assert agent.state == "paused"
    assert session.commit.called


def test_handle_deauthorization_unknown_account_succeeds_without_error() -> None:
    session = MagicMock()
    clock = FrozenClock(datetime(2026, 11, 3, 12, 0, tzinfo=UTC))
    settings = Settings(meta_app_secret=SecretStr(MOCK_SECRET))

    # DB returns no matching accounts
    session.execute.return_value.scalars.return_value.all.return_value = []

    signed_req = make_signed_request(
        {"user_id": "unknown_user", "algorithm": "HMAC-SHA256"}, MOCK_SECRET
    )
    result = handle_deauthorization(session, clock, settings, signed_req)

    assert result == {"status": "ok"}
    assert session.commit.called


def test_handle_deauthorization_invalid_signature_raises_and_audits() -> None:
    session = MagicMock()
    clock = FrozenClock(datetime(2026, 11, 3, 12, 0, tzinfo=UTC))
    settings = Settings(meta_app_secret=SecretStr(MOCK_SECRET))

    bad_signed_req = make_signed_request(
        {"user_id": "user1", "algorithm": "HMAC-SHA256"}, "different-secret"
    )

    with pytest.raises(InvalidSignatureError):
        handle_deauthorization(session, clock, settings, bad_signed_req)

    assert session.commit.called  # Audits failure and commits


def test_handle_data_deletion_page_owner_account() -> None:
    session = MagicMock()
    clock = FrozenClock(datetime(2026, 11, 3, 12, 0, tzinfo=UTC))
    settings = Settings(
        app_base_url="https://app.agentnest.test",
        meta_app_secret=SecretStr(MOCK_SECRET),
    )

    user_id = "meta_owner_2002"
    ws_id = uuid.uuid4()

    acc = MagicMock(spec=SocialAccount)
    acc.id = uuid.uuid4()
    acc.workspace_id = ws_id
    acc.external_account_id = user_id
    acc.status = "connected"

    # Setup session.execute queries:
    # 1. Check existing DataDeletionRequest -> None
    # 2. Check SocialAccount -> [acc]
    scalars_mock = MagicMock()
    scalars_mock.first.side_effect = [None, acc]
    session.execute.return_value.scalars.return_value = scalars_mock

    signed_req = make_signed_request({"user_id": user_id, "algorithm": "HMAC-SHA256"}, MOCK_SECRET)
    res = handle_data_deletion_request(session, clock, settings, signed_req)

    assert "confirmation_code" in res
    assert res["url"].startswith(
        "https://app.agentnest.test/api/v1/webhooks/meta/data-deletion/del_"
    )
    assert acc.status == "disconnected"
    assert session.add.called
    assert session.commit.called


def test_handle_data_deletion_customer_identity_triggers_erasure() -> None:
    session = MagicMock()
    clock = FrozenClock(datetime(2026, 11, 3, 12, 0, tzinfo=UTC))
    settings = Settings(
        app_base_url="https://app.agentnest.test",
        meta_app_secret=SecretStr(MOCK_SECRET),
    )

    user_id = "meta_cust_3003"
    ws_id = uuid.uuid4()
    cust_id = uuid.uuid4()

    cust = MagicMock(spec=CustomerIdentity)
    cust.id = cust_id
    cust.workspace_id = ws_id

    # 1. Existing DataDeletionRequest -> None
    # 2. SocialAccount -> None
    # 3. CustomerIdentity -> cust
    scalars_mock = MagicMock()
    scalars_mock.first.side_effect = [None, None, cust]
    session.execute.return_value.scalars.return_value = scalars_mock

    with patch("app.operations.meta_callbacks.erase_customer") as mock_erase:
        mock_erase.return_value = {"status": "erased"}

        signed_req = make_signed_request(
            {"user_id": user_id, "algorithm": "HMAC-SHA256"}, MOCK_SECRET
        )
        res = handle_data_deletion_request(session, clock, settings, signed_req)

        assert "confirmation_code" in res
        assert mock_erase.called
        call_args = mock_erase.call_args[0]
        assert call_args[0] == session
        assert call_args[1] == clock
        assert call_args[2].workspace_id == ws_id
        assert call_args[3] == cust_id


def test_handle_data_deletion_reconciliation_pending_marks_in_progress() -> None:
    session = MagicMock()
    clock = FrozenClock(datetime(2026, 11, 3, 12, 0, tzinfo=UTC))
    settings = Settings(
        app_base_url="https://app.agentnest.test",
        meta_app_secret=SecretStr(MOCK_SECRET),
    )

    user_id = "meta_cust_4004"
    ws_id = uuid.uuid4()
    cust_id = uuid.uuid4()

    cust = MagicMock(spec=CustomerIdentity)
    cust.id = cust_id
    cust.workspace_id = ws_id

    scalars_mock = MagicMock()
    scalars_mock.first.side_effect = [None, None, cust]
    session.execute.return_value.scalars.return_value = scalars_mock

    with patch("app.operations.meta_callbacks.erase_customer") as mock_erase:
        # Returns reconciliation pending
        mock_erase.return_value = {"status": "redacted_reconciliation_pending"}

        signed_req = make_signed_request(
            {"user_id": user_id, "algorithm": "HMAC-SHA256"}, MOCK_SECRET
        )
        res = handle_data_deletion_request(session, clock, settings, signed_req)

        # Check added DataDeletionRequest has status='in_progress'
        added_request = [
            arg[0][0]
            for arg in session.add.call_args_list
            if isinstance(arg[0][0], DataDeletionRequest)
        ][0]
        assert added_request.status == "in_progress"
        assert added_request.completed_at is None
        assert "confirmation_code" in res


def test_handle_data_deletion_unknown_identity_writes_tombstone() -> None:
    session = MagicMock()
    clock = FrozenClock(datetime(2026, 11, 3, 12, 0, tzinfo=UTC))
    settings = Settings(
        app_base_url="https://app.agentnest.test",
        meta_app_secret=SecretStr(MOCK_SECRET),
    )

    user_id = "unknown_user_9999"

    # 1. Existing DataDeletionRequest -> None
    # 2. SocialAccount -> None
    # 3. CustomerIdentity -> None
    scalars_mock = MagicMock()
    scalars_mock.first.side_effect = [None, None, None]
    session.execute.return_value.scalars.return_value = scalars_mock

    signed_req = make_signed_request({"user_id": user_id, "algorithm": "HMAC-SHA256"}, MOCK_SECRET)
    res = handle_data_deletion_request(session, clock, settings, signed_req)

    assert "confirmation_code" in res
    # Verifies anticipatory tombstone added to prevent future resurrection
    added_tombstone = [
        arg[0][0] for arg in session.add.call_args_list if isinstance(arg[0][0], DeletionTombstone)
    ][0]
    assert added_tombstone.entity_type == "meta_user"
    assert added_tombstone.entity_id == user_id


def test_handle_data_deletion_idempotent_replay() -> None:
    session = MagicMock()
    clock = FrozenClock(datetime(2026, 11, 3, 12, 0, tzinfo=UTC))
    settings = Settings(
        app_base_url="https://app.agentnest.test",
        meta_app_secret=SecretStr(MOCK_SECRET),
    )

    existing_req = MagicMock(spec=DataDeletionRequest)
    existing_req.confirmation_code = "del_existing_code_123"

    session.execute.return_value.scalars.return_value.first.return_value = existing_req

    signed_req = make_signed_request(
        {"user_id": "meta_user_1", "algorithm": "HMAC-SHA256"}, MOCK_SECRET
    )
    res = handle_data_deletion_request(session, clock, settings, signed_req)

    assert res["confirmation_code"] == "del_existing_code_123"
    assert (
        res["url"]
        == "https://app.agentnest.test/api/v1/webhooks/meta/data-deletion/del_existing_code_123"
    )
    assert not session.add.called  # No new record added


def test_get_data_deletion_status_privacy_safe() -> None:
    session = MagicMock()
    clock = FrozenClock(datetime(2026, 11, 3, 12, 0, tzinfo=UTC))

    req = MagicMock(spec=DataDeletionRequest)
    req.confirmation_code = "del_safe_test_code"
    req.status = "completed"
    req.requested_at = datetime(2026, 11, 3, 10, 0, tzinfo=UTC)
    req.completed_at = datetime(2026, 11, 3, 10, 5, tzinfo=UTC)
    req.workspace_id = uuid.uuid4()

    session.execute.return_value.scalars.return_value.first.return_value = req

    status = get_data_deletion_status(session, clock, "del_safe_test_code")
    assert status is not None
    assert status["confirmation_code"] == "del_safe_test_code"
    assert status["status"] == "completed"
    assert status["requested_at"] == "2026-11-03T10:00:00+00:00"
    assert status["completed_at"] == "2026-11-03T10:05:00+00:00"

    # Strictly verify NO PII or internal IDs leak in status output
    for forbidden_key in ("user_id", "external_account_id", "username", "workspace_id", "details"):
        assert forbidden_key not in status


def test_meta_callbacks_endpoints_via_test_client() -> None:
    settings = Settings(
        app_base_url="https://app.agentnest.test",
        meta_app_secret=SecretStr(MOCK_SECRET),
        demo_tools_enabled=True,
    )
    clock = FrozenClock(datetime(2026, 11, 3, 12, 0, tzinfo=UTC))
    mock_session = MagicMock()

    from app.core.db import get_db

    app = create_app(settings=settings, clock=clock)
    app.dependency_overrides[get_db] = lambda: mock_session
    client = TestClient(app)

    # 1. Missing signed_request -> 400
    res_deauth_missing = client.post("/api/v1/webhooks/meta/deauthorize")
    assert res_deauth_missing.status_code == 400

    # 2. Invalid signed_request signature -> 401
    bad_req = make_signed_request({"user_id": "u1", "algorithm": "HMAC-SHA256"}, "wrong-secret")
    res_deauth_bad_sig = client.post(
        "/api/v1/webhooks/meta/deauthorize",
        data={"signed_request": bad_req},
    )
    assert res_deauth_bad_sig.status_code == 401

    # 3. Successful deauthorization (Form & JSON, canonical & alias routes)
    valid_req = make_signed_request(
        {"user_id": "test_client_user", "algorithm": "HMAC-SHA256"}, MOCK_SECRET
    )

    with patch("app.operations.meta_callbacks_router.handle_deauthorization") as mock_deauth:
        mock_deauth.return_value = {"status": "ok"}

        # Form POST to /api/v1 route
        res_form = client.post(
            "/api/v1/webhooks/meta/deauthorize",
            data={"signed_request": valid_req},
        )
        assert res_form.status_code == 200
        assert res_form.json() == {"status": "ok"}

        # JSON POST to /webhooks proxy route
        res_json = client.post(
            "/webhooks/meta/deauthorize",
            json={"signed_request": valid_req},
        )
        assert res_json.status_code == 200
        assert res_json.json() == {"status": "ok"}

    # 4. Successful data-deletion callback
    with patch("app.operations.meta_callbacks_router.handle_data_deletion_request") as mock_del:
        mock_del.return_value = {
            "url": "https://app.agentnest.test/api/v1/webhooks/meta/data-deletion/del_123",
            "confirmation_code": "del_123",
        }

        res_del = client.post(
            "/api/v1/webhooks/meta/data-deletion",
            data={"signed_request": valid_req},
        )
        assert res_del.status_code == 200
        assert res_del.json()["confirmation_code"] == "del_123"

    # 5. Data deletion status endpoint (JSON & HTML)
    with patch("app.operations.meta_callbacks_router.get_data_deletion_status") as mock_status:
        mock_status.return_value = {
            "confirmation_code": "del_123",
            "status": "completed",
            "requested_at": "2026-11-03T12:00:00+00:00",
            "completed_at": "2026-11-03T12:01:00+00:00",
        }

        # JSON response
        res_status_json = client.get(
            "/api/v1/webhooks/meta/data-deletion/del_123",
            headers={"Accept": "application/json"},
        )
        assert res_status_json.status_code == 200
        assert res_status_json.json()["status"] == "completed"

        # HTML response for browser navigation
        res_status_html = client.get(
            "/api/v1/webhooks/meta/data-deletion/del_123",
            headers={"Accept": "text/html"},
        )
        assert res_status_html.status_code == 200
        assert "text/html" in res_status_html.headers["content-type"]
        assert "del_123" in res_status_html.text
        assert "Veri Silme Durumu" in res_status_html.text

    # 6. Non-existent status code -> 404
    with patch("app.operations.meta_callbacks_router.get_data_deletion_status") as mock_status:
        mock_status.return_value = None
        res_status_404 = client.get("/api/v1/webhooks/meta/data-deletion/non_existent_code")
        assert res_status_404.status_code == 404
