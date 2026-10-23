"""Password hashing, session/CSRF tokens and account-bound token encryption (ADR-017)."""

import base64
import binascii
import hashlib
import hmac
import secrets
import uuid

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

MIN_PASSWORD_LENGTH = 10

# Small deny-list; the policy is length-based, no composition rules (security-and-privacy.md §3).
_COMMON_PASSWORDS = frozenset(
    {
        "password",
        "password1",
        "password12",
        "password123",
        "1234567890",
        "12345678910",
        "0123456789",
        "qwertyuiop",
        "qwerty12345",
        "iloveyou123",
        "letmein1234",
        "admin12345",
        "welcome123",
        "changeme123",
        "parola1234",
        "sifre12345",
    }
)

_hasher = PasswordHasher()  # argon2id with library defaults
# Verified against when the user does not exist, so timing does not reveal existence.
_DUMMY_HASH = _hasher.hash("agentnest-dummy-password")


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str | None, password: str) -> bool:
    """Constant-effort verification; ``None`` hash (unknown user) still costs one verify."""
    try:
        return _hasher.verify(password_hash or _DUMMY_HASH, password) and password_hash is not None
    except (VerificationError, InvalidHashError):
        return False


def password_needs_rehash(password_hash: str) -> bool:
    return _hasher.check_needs_rehash(password_hash)


def password_policy_problems(password: str) -> list[str]:
    """Return machine codes for policy violations (empty when acceptable)."""
    problems: list[str] = []
    if len(password) < MIN_PASSWORD_LENGTH:
        problems.append("too_short")
    if password.lower() in _COMMON_PASSWORDS:
        problems.append("too_common")
    return problems


def generate_token() -> str:
    """Opaque URL-safe random token (session cookie value, CSRF token)."""
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> bytes:
    """SHA-256 of a token; only the hash is stored."""
    return hashlib.sha256(token.encode()).digest()


def constant_time_equal(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode(), b.encode())


def generate_secret_key() -> str:
    """A value suitable for SECRET_KEY (>= 32 bytes of randomness)."""
    return secrets.token_urlsafe(48)


def generate_encryption_key(key_id: str = "k1") -> str:
    """``key_id:base64(32 random bytes)``, the TOKEN_ENCRYPTION_KEYS entry format (ADR-017)."""
    return f"{key_id}:{base64.b64encode(secrets.token_bytes(32)).decode()}"


class TokenCryptoError(ValueError):
    """Invalid key configuration or unauthenticated token ciphertext; never contains secrets."""


class TokenKeyRing:
    """AES-256-GCM keys: new writes use the active key; retained keys decrypt older rows."""

    def __init__(self, keys: str, active_key_id: str) -> None:
        self._keys: dict[str, bytes] = {}
        for entry in keys.split(","):
            key_id, separator, encoded = entry.strip().partition(":")
            key_id = key_id.strip()
            if not separator or not key_id or key_id in self._keys:
                raise TokenCryptoError("TOKEN_ENCRYPTION_KEYS has empty or duplicate key IDs.")
            try:
                key = base64.b64decode(encoded, validate=True)
            except (binascii.Error, ValueError):
                raise TokenCryptoError("TOKEN_ENCRYPTION_KEYS must contain base64 keys.") from None
            if len(key) != 32:
                raise TokenCryptoError("TOKEN_ENCRYPTION_KEYS keys must decode to 32 bytes.")
            self._keys[key_id] = key
        if active_key_id not in self._keys:
            raise TokenCryptoError("TOKEN_ENCRYPTION_ACTIVE_KEY_ID must name a configured key.")
        self.active_key_id = active_key_id

    def encrypt(self, plaintext: str, *, aad: bytes = b"") -> tuple[bytes, str]:
        nonce = secrets.token_bytes(12)
        encrypted = AESGCM(self._keys[self.active_key_id]).encrypt(nonce, plaintext.encode(), aad)
        return nonce + encrypted, self.active_key_id

    def decrypt(self, blob: bytes, key_id: str, *, aad: bytes = b"") -> str:
        key = self._keys.get(key_id)
        if key is None or len(blob) < 28:  # 12-byte nonce and 16-byte authentication tag
            raise TokenCryptoError("Token ciphertext or key ID is invalid.")
        try:
            return AESGCM(key).decrypt(blob[:12], blob[12:], aad).decode("utf-8")
        except (InvalidTag, UnicodeDecodeError, ValueError):
            raise TokenCryptoError("Token ciphertext authentication failed.") from None


def account_token_aad(workspace_id: uuid.UUID, account_id: uuid.UUID) -> bytes:
    """Bind ciphertext to its tenant and account so moving a stored blob cannot authenticate."""
    return f"{workspace_id}:{account_id}".encode()
