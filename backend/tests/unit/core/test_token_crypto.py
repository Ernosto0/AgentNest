"""Account-bound AES-GCM, malformed configuration, and rotation without losing old reads."""

import base64
import uuid

import pytest

from app.core.security import TokenCryptoError, TokenKeyRing, account_token_aad

K1 = base64.b64encode(b"1" * 32).decode()
K2 = base64.b64encode(b"2" * 32).decode()
WORKSPACE = uuid.UUID("11111111-2222-3333-4444-555555555555")
ACCOUNT = uuid.UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
AAD = account_token_aad(WORKSPACE, ACCOUNT)


@pytest.mark.parametrize("plaintext", ["test-token", "", "erişim-anahtarı-🔑"])
def test_round_trip_with_account_bound_aad(plaintext: str) -> None:
    ring = TokenKeyRing(f"k1:{K1}", "k1")
    blob, key_id = ring.encrypt(plaintext, aad=AAD)
    assert key_id == "k1"
    assert len(blob) == 12 + len(plaintext.encode()) + 16
    assert ring.decrypt(blob, key_id, aad=AAD) == plaintext
    assert ring.encrypt(plaintext, aad=AAD)[0] != blob  # independent random nonce
    assert f"{WORKSPACE}:{ACCOUNT}".encode() == AAD


def test_rotation_reads_retained_keys_and_writes_only_the_active_key() -> None:
    first = TokenKeyRing(f"k1:{K1}", "k1")
    old, old_id = first.encrypt("old-token", aad=AAD)
    rotated = TokenKeyRing(f"k1:{K1},k2:{K2}", "k2")
    assert rotated.decrypt(old, old_id, aad=AAD) == "old-token"
    new, new_id = rotated.encrypt("new-token", aad=AAD)
    assert new_id == "k2"
    assert rotated.decrypt(new, new_id, aad=AAD) == "new-token"
    with pytest.raises(TokenCryptoError):
        first.decrypt(new, new_id, aad=AAD)


@pytest.mark.parametrize("part", ["nonce", "ciphertext", "tag"])
def test_tampering_is_rejected(part: str) -> None:
    ring = TokenKeyRing(f"k1:{K1}", "k1")
    blob, key_id = ring.encrypt("private-token", aad=AAD)
    changed = bytearray(blob)
    changed[{"nonce": 0, "ciphertext": 12, "tag": -1}[part]] ^= 1
    with pytest.raises(TokenCryptoError):
        ring.decrypt(bytes(changed), key_id, aad=AAD)


def test_unknown_key_wrong_key_and_cross_account_or_workspace_aad_are_rejected() -> None:
    ring = TokenKeyRing(f"k1:{K1}", "k1")
    blob, _ = ring.encrypt("private-token", aad=AAD)
    for key_id, aad in (
        ("unknown", AAD),
        ("k1", account_token_aad(uuid.uuid4(), ACCOUNT)),
        ("k1", account_token_aad(WORKSPACE, uuid.uuid4())),
        ("k1", b""),
    ):
        with pytest.raises(TokenCryptoError):
            ring.decrypt(blob, key_id, aad=aad)
    with pytest.raises(TokenCryptoError):
        TokenKeyRing(f"k1:{K2}", "k1").decrypt(blob, "k1", aad=AAD)


@pytest.mark.parametrize("blob", [b"", b"x" * 11, b"x" * 12, b"x" * 27, b"x" * 28])
def test_truncated_or_invalid_blobs_are_rejected(blob: bytes) -> None:
    with pytest.raises(TokenCryptoError):
        TokenKeyRing(f"k1:{K1}", "k1").decrypt(blob, "k1")


@pytest.mark.parametrize(
    ("keys", "active"),
    [
        ("", "k1"),
        (f":{K1}", "k1"),
        (f" :{K1}", "k1"),
        (f"k1:{K1},k1:{K2}", "k1"),
        (f"k1:{K1},", "k1"),
        ("k1:not-base64!!!", "k1"),
        ("k1:🔑", "k1"),
        ("k1:", "k1"),
        (f"k1:{base64.b64encode(b'x' * 31).decode()}", "k1"),
        (f"k1:{base64.b64encode(b'x' * 33).decode()}", "k1"),
        (K1, "k1"),
        (f"k1:{K1}", "missing"),
        (f"k1:{K1}", ""),
    ],
)
def test_malformed_key_ring_is_rejected_without_disclosing_keys(keys: str, active: str) -> None:
    with pytest.raises(TokenCryptoError) as info:
        TokenKeyRing(keys, active)
    assert K1 not in str(info.value)
    assert K2 not in str(info.value)


def test_object_representation_and_errors_do_not_expose_tokens_or_keys() -> None:
    ring = TokenKeyRing(f"k1:{K1}", "k1")
    assert K1 not in repr(ring)
    blob, key_id = ring.encrypt("secret-token", aad=AAD)
    with pytest.raises(TokenCryptoError) as info:
        ring.decrypt(blob, key_id, aad=b"wrong")
    assert "secret-token" not in str(info.value)
    assert K1 not in str(info.value)
