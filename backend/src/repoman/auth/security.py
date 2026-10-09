"""Password hashing and opaque secret (session id, API token, CSRF token) helpers."""

import asyncio
import hashlib
import hmac
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

PASSWORD_MIN_LENGTH = 8
PASSWORD_MAX_LENGTH = 1024

TOKEN_PREFIX = "rpm_"
# Number of characters after TOKEN_PREFIX shown to users to identify a token.
TOKEN_DISPLAY_CHARS = 8

_hasher = PasswordHasher()
# Verified against when a user does not exist, so timing does not reveal valid usernames.
_DUMMY_HASH = _hasher.hash(secrets.token_urlsafe(16))


async def hash_password(password: str) -> str:
    return await asyncio.to_thread(_hasher.hash, password)


def _verify(password_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


async def verify_password(password_hash: str | None, password: str) -> bool:
    if password_hash is None:
        await asyncio.to_thread(_verify, _DUMMY_HASH, password)
        return False
    return await asyncio.to_thread(_verify, password_hash, password)


def password_needs_rehash(password_hash: str) -> bool:
    return _hasher.check_needs_rehash(password_hash)


def new_secret() -> str:
    return secrets.token_urlsafe(32)


def new_api_token() -> str:
    return TOKEN_PREFIX + secrets.token_urlsafe(32)


def token_display_prefix(token: str) -> str:
    return token[: len(TOKEN_PREFIX) + TOKEN_DISPLAY_CHARS]


def hash_secret(secret: str) -> str:
    """Secrets are high-entropy random values, so a fast hash is sufficient."""
    return hashlib.sha256(secret.encode()).hexdigest()


def secrets_equal(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode(), b.encode())
