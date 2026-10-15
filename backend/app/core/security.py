"""Password hashing, session/CSRF tokens. Token encryption (AES-GCM) arrives with Phase 7."""

import base64
import hashlib
import hmac
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

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
