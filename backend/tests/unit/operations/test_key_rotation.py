"""Unit tests for Phase 8 Session 12: Token Encryption Key Rotation (P8-06).

Covers:
- Re-encrypting social_accounts with outdated token_key_id using active key.
- Preserving tenant AAD binding (workspace_id:account_id) across re-encryption.
- Validating that newly encrypted tokens decrypt successfully with the active key.
- Safe skipping of already-rotated accounts (token_key_id == active_key_id).
- Safe skipping of disconnected accounts and accounts without tokens (mock/simulated).
- Handling corrupted ciphertext or missing keys without halting other accounts in batch.
- Emitting security.token_key_rotated audit events with key IDs and no plaintext/ciphertext.
- Background worker job handler handle_rotate_token_keys execution.
"""

from __future__ import annotations

import base64
import os
import uuid
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

from pydantic import SecretStr

from app.core.clock import FrozenClock
from app.core.config import Settings
from app.core.security import TokenKeyRing, account_token_aad
from app.integrations.instagram.models import SocialAccount
from app.jobs.registry import JobContext
from app.operations.key_rotation import (
    KeyRotationResult,
    RotateTokenKeysPayload,
    handle_rotate_token_keys,
    rotate_social_account_tokens,
)

# Setup two valid 32-byte keys
KEY1_BYTES = os.urandom(32)
KEY2_BYTES = os.urandom(32)
KEY1_B64 = base64.b64encode(KEY1_BYTES).decode("utf-8")
KEY2_B64 = base64.b64encode(KEY2_BYTES).decode("utf-8")

CONFIG_KEYS = f"k1:{KEY1_B64},k2:{KEY2_B64}"


def _make_settings(active_key_id: str = "k2", keys_str: str = CONFIG_KEYS) -> Settings:
    return Settings(
        token_encryption_keys=SecretStr(keys_str),
        token_encryption_active_key_id=active_key_id,
    )


def test_rotate_tokens_success() -> None:
    clock = FrozenClock(datetime(2026, 11, 3, 12, 0, tzinfo=UTC))
    settings = _make_settings(active_key_id="k2")

    ws_id = uuid.uuid4()
    acc_id = uuid.uuid4()
    raw_token = "EAABtest_access_token_secret_12345"

    # Encrypt raw_token initially under k1
    ring_k1 = TokenKeyRing(CONFIG_KEYS, "k1")
    aad = account_token_aad(ws_id, acc_id)
    ciphertext_k1, key_id_k1 = ring_k1.encrypt(raw_token, aad=aad)
    assert key_id_k1 == "k1"

    # Create account with k1 token
    account = SocialAccount(
        id=acc_id,
        workspace_id=ws_id,
        platform="instagram",
        provider_kind="meta",
        external_account_id="ig_123",
        status="connected",
        token_ciphertext=ciphertext_k1,
        token_key_id="k1",
        token_refreshed_at=datetime(2026, 10, 1, 0, 0, tzinfo=UTC),
    )

    # Session mock
    mock_session = MagicMock()
    # 1. Discovery query returns candidates
    mock_session.execute.return_value.all.return_value = [(acc_id, ws_id, "k1")]
    # 2. Account query returns our account
    mock_session.scalars.return_value.first.return_value = account

    session_factory = MagicMock()
    session_factory.return_value.__enter__.return_value = mock_session

    with patch("app.operations.key_rotation.audit.record") as mock_audit:
        result = rotate_social_account_tokens(session_factory, settings, clock, batch_size=50)

    assert result.scanned == 1
    assert result.rotated == 1
    assert result.skipped == 0
    assert result.failed == 0
    assert result.active_key_id == "k2"

    # Account was updated with k2
    assert account.token_key_id == "k2"
    assert account.token_ciphertext != ciphertext_k1
    assert account.token_refreshed_at == clock.now()

    # Verify new ciphertext decrypts with k2 and preserves AAD
    ring_k2 = TokenKeyRing(CONFIG_KEYS, "k2")
    decrypted = ring_k2.decrypt(account.token_ciphertext, "k2", aad=aad)
    assert decrypted == raw_token

    # Verify audit event was emitted with key metadata and NEVER plaintext token
    mock_audit.assert_called_once()
    args, kwargs = mock_audit.call_args
    assert args[2] == "security.token_key_rotated"
    assert args[3] == "social_account"
    assert args[4] == acc_id
    assert args[5] == {
        "workspace_id": str(ws_id),
        "old_key_id": "k1",
        "new_key_id": "k2",
    }
    # Plaintext token must not appear anywhere in kwargs or args
    assert raw_token not in str(args) + str(kwargs)


def test_rotate_tokens_skips_already_rotated_or_disconnected() -> None:
    clock = FrozenClock(datetime(2026, 11, 3, 12, 0, tzinfo=UTC))
    settings = _make_settings(active_key_id="k2")

    ws_id = uuid.uuid4()
    acc1_id = uuid.uuid4()
    acc2_id = uuid.uuid4()

    # Account 1: already on k2
    acc1 = SocialAccount(
        id=acc1_id,
        workspace_id=ws_id,
        platform="instagram",
        provider_kind="meta",
        external_account_id="ig_1",
        status="connected",
        token_ciphertext=b"some_bytes",
        token_key_id="k2",
    )

    # Account 2: disconnected concurrently
    acc2 = SocialAccount(
        id=acc2_id,
        workspace_id=ws_id,
        platform="instagram",
        provider_kind="meta",
        external_account_id="ig_2",
        status="disconnected",
        token_ciphertext=None,
        token_key_id=None,
    )

    mock_session = MagicMock()
    mock_session.execute.return_value.all.return_value = [
        (acc1_id, ws_id, "k1"),
        (acc2_id, ws_id, "k1"),
    ]
    mock_session.scalars.return_value.first.side_effect = [acc1, acc2]

    session_factory = MagicMock()
    session_factory.return_value.__enter__.return_value = mock_session

    with patch("app.operations.key_rotation.audit.record") as mock_audit:
        result = rotate_social_account_tokens(session_factory, settings, clock)

    assert result.scanned == 2
    assert result.rotated == 0
    assert result.skipped == 2
    assert result.failed == 0
    mock_audit.assert_not_called()


def test_rotate_tokens_handles_corrupt_ciphertext() -> None:
    clock = FrozenClock(datetime(2026, 11, 3, 12, 0, tzinfo=UTC))
    settings = _make_settings(active_key_id="k2")

    ws_id = uuid.uuid4()
    acc_id = uuid.uuid4()

    # Corrupt ciphertext
    corrupt_account = SocialAccount(
        id=acc_id,
        workspace_id=ws_id,
        platform="instagram",
        provider_kind="meta",
        external_account_id="ig_bad",
        status="connected",
        token_ciphertext=b"corrupted_garbage_bytes_too_short",
        token_key_id="k1",
    )

    mock_session = MagicMock()
    mock_session.execute.return_value.all.return_value = [(acc_id, ws_id, "k1")]
    mock_session.scalars.return_value.first.return_value = corrupt_account

    session_factory = MagicMock()
    session_factory.return_value.__enter__.return_value = mock_session

    with patch("app.operations.key_rotation.audit.record") as mock_audit:
        result = rotate_social_account_tokens(session_factory, settings, clock)

    assert result.scanned == 1
    assert result.rotated == 0
    assert result.failed == 1
    assert corrupt_account.last_error_code == "KEY_ROTATION_FAILED"

    # Audit failure event
    mock_audit.assert_called_once()
    args, kwargs = mock_audit.call_args
    assert args[2] == "security.token_key_rotation_failed"
    assert args[3] == "social_account"
    assert args[4] == acc_id
    assert args[5]["old_key_id"] == "k1"


def test_rotate_tokens_no_keys_configured() -> None:
    clock = FrozenClock(datetime(2026, 11, 3, 12, 0, tzinfo=UTC))
    empty_settings = Settings.model_construct(
        token_encryption_keys=SecretStr(""),
        token_encryption_active_key_id="",
    )

    session_factory = MagicMock()
    result = rotate_social_account_tokens(session_factory, empty_settings, clock)
    assert result.scanned == 0
    assert result.rotated == 0
    assert result.failed == 0
    session_factory.assert_not_called()


def test_job_handler_invokes_rotation() -> None:
    settings = _make_settings(active_key_id="k2")
    job = MagicMock(spec=JobContext)
    job.payload = RotateTokenKeysPayload(batch_size=25)
    job.clock = FrozenClock(datetime(2026, 11, 3, 12, 0, tzinfo=UTC))
    job.session_factory = MagicMock()

    with (
        patch("app.operations.key_rotation.get_settings", return_value=settings),
        patch(
            "app.operations.key_rotation.rotate_social_account_tokens",
            return_value=KeyRotationResult(scanned=5, rotated=5, active_key_id="k2"),
        ) as mock_rot,
    ):
        handle_rotate_token_keys(job)
        mock_rot.assert_called_once_with(job.session_factory, settings, job.clock, batch_size=25)
