"""Password hashing, API key minting/verification, JWTs, and the credential vault.

Section 31 is the load-bearing rule here::

    passwords -> Argon2id
    API keys  -> HMAC-SHA256 with a server-side pepper

API keys carry 190+ bits of entropy so there is no brute-force surface to
stretch against; Argon2 would add 50-100 ms to *every* request for no gain.
Comparison is always ``hmac.compare_digest``.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import re
import secrets
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from argon2.low_level import Type
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.config import settings

# --------------------------------------------------------------------------
# Passwords - Argon2id (sections 31, 62)
# --------------------------------------------------------------------------
_password_hasher = PasswordHasher(
    time_cost=3,
    memory_cost=65536,
    parallelism=4,
    hash_len=32,
    salt_len=16,
    type=Type.ID,
)

BULLET = "•"


def hash_password(password: str) -> str:
    return _password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _password_hasher.verify(password_hash, password)
    except VerifyMismatchError:
        return False
    except Exception:
        return False


def password_needs_rehash(password_hash: str) -> bool:
    try:
        return _password_hasher.check_needs_rehash(password_hash)
    except Exception:
        return True


# --------------------------------------------------------------------------
# SerpFlow API keys (sections 28-32)
# --------------------------------------------------------------------------
API_KEY_PATTERN = re.compile(r"^sf_(live|test)_([a-z0-9]{6})_([A-Za-z0-9]{32})$")
_SECRET_ALPHABET = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
_PREFIX_ALPHABET = "abcdefghijklmnopqrstuvwxyz0123456789"

KeyEnvironment = Literal["live", "test"]


@dataclass(frozen=True, slots=True)
class MintedApiKey:
    """A freshly minted key. ``plaintext`` is shown exactly once, then dropped."""

    plaintext: str
    environment: str
    project_prefix: str
    key_hash: str
    display: str


def generate_project_prefix() -> str:
    """6 lowercase alphanumerics, stored in plaintext and indexed for O(1) lookup."""
    return "".join(secrets.choice(_PREFIX_ALPHABET) for _ in range(6))


def api_key_display(environment: str, project_prefix: str) -> str:
    return "sf_" + environment + "_" + project_prefix + "_" + BULLET * 4


def mint_api_key(environment: str, project_prefix: str) -> MintedApiKey:
    if environment not in ("live", "test"):
        raise ValueError("environment must be live or test")
    if not re.fullmatch(r"[a-z0-9]{6}", project_prefix):
        raise ValueError("project_prefix must be exactly 6 lowercase alphanumerics")
    secret = "".join(secrets.choice(_SECRET_ALPHABET) for _ in range(32))
    plaintext = "sf_" + environment + "_" + project_prefix + "_" + secret
    return MintedApiKey(
        plaintext=plaintext,
        environment=environment,
        project_prefix=project_prefix,
        key_hash=hash_api_key(plaintext),
        display=api_key_display(environment, project_prefix),
    )


def hash_api_key(plaintext: str) -> str:
    """HMAC-SHA256 under the server-side pepper. Sub-millisecond, constant time."""
    return hmac.new(
        settings.api_key_pepper.encode("utf-8"),
        plaintext.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def verify_api_key(plaintext: str, stored_hash: str) -> bool:
    return hmac.compare_digest(hash_api_key(plaintext), stored_hash)


@dataclass(frozen=True, slots=True)
class ParsedApiKey:
    environment: str
    project_prefix: str
    secret: str
    plaintext: str

    @property
    def is_test(self) -> bool:
        return self.environment == "test"


def parse_api_key(plaintext: str) -> ParsedApiKey | None:
    """Structural parse only. Never a substitute for the HMAC check."""
    if not plaintext:
        return None
    match = API_KEY_PATTERN.match(plaintext.strip())
    if not match:
        return None
    env, prefix, secret = match.groups()
    return ParsedApiKey(
        environment=env,
        project_prefix=prefix,
        secret=secret,
        plaintext=plaintext.strip(),
    )


# --------------------------------------------------------------------------
# JWT sessions (section 62)
# --------------------------------------------------------------------------
def create_token(
    subject: str,
    token_type: str,
    *,
    extra: dict[str, Any] | None = None,
    ttl_seconds: int | None = None,
) -> tuple[str, datetime]:
    now = datetime.now(UTC)
    ttl = ttl_seconds or (
        settings.access_token_ttl_seconds
        if token_type == "access"
        else settings.refresh_token_ttl_seconds
    )
    expires = now + timedelta(seconds=ttl)
    payload: dict[str, Any] = {
        "sub": subject,
        "typ": token_type,
        "iat": int(now.timestamp()),
        "exp": int(expires.timestamp()),
        "jti": secrets.token_urlsafe(16),
        "iss": settings.service_name,
    }
    payload.update(extra or {})
    token = jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    return token, expires


def decode_token(token: str, expected_type: str | None = None) -> dict[str, Any]:
    payload = jwt.decode(
        token,
        settings.jwt_secret,
        algorithms=[settings.jwt_algorithm],
        issuer=settings.service_name,
    )
    if expected_type and payload.get("typ") != expected_type:
        raise jwt.InvalidTokenError("unexpected token type")
    return payload


def generate_opaque_token(nbytes: int = 32) -> str:
    return secrets.token_urlsafe(nbytes)


def hash_opaque_token(token: str) -> str:
    """For email-verification / password-reset / refresh-session handles."""
    return hmac.new(
        settings.api_key_pepper.encode("utf-8"), token.encode("utf-8"), hashlib.sha256
    ).hexdigest()


# --------------------------------------------------------------------------
# Credential vault - envelope encryption (section 24)
# --------------------------------------------------------------------------
CREDENTIAL_ALGO = "AES-256-GCM/DEK+KEK"


@dataclass(frozen=True, slots=True)
class EnvelopeCiphertext:
    ciphertext: str
    encrypted_dek: str
    kek_id: str
    algo: str
    fingerprint: str


def _load_kek() -> bytes:
    raw = settings.credential_kek
    try:
        key = base64.b64decode(raw, validate=True)
    except Exception:
        key = hashlib.sha256(raw.encode("utf-8")).digest()
    if len(key) != 32:
        key = hashlib.sha256(key).digest()
    return key


def credential_fingerprint(secret: str) -> str:
    """Non-reversible, 8 hex chars - safe to render in the UI (section 24)."""
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()[:8]


def encrypt_credential(secret: str, *, kek_id: str | None = None) -> EnvelopeCiphertext:
    """Random per-credential DEK, wrapped by the KEK. Never log any part of this."""
    dek = AESGCM.generate_key(bit_length=256)
    data_nonce = os.urandom(12)
    ciphertext = AESGCM(dek).encrypt(data_nonce, secret.encode("utf-8"), None)

    kek = _load_kek()
    dek_nonce = os.urandom(12)
    wrapped = AESGCM(kek).encrypt(dek_nonce, dek, None)

    return EnvelopeCiphertext(
        ciphertext=base64.b64encode(data_nonce + ciphertext).decode("ascii"),
        encrypted_dek=base64.b64encode(dek_nonce + wrapped).decode("ascii"),
        kek_id=kek_id or settings.credential_kek_id,
        algo=CREDENTIAL_ALGO,
        fingerprint=credential_fingerprint(secret),
    )


def decrypt_credential(ciphertext: str, encrypted_dek: str) -> str:
    """Only ever called from inside the executor service (section 25)."""
    kek = _load_kek()
    wrapped = base64.b64decode(encrypted_dek)
    dek = AESGCM(kek).decrypt(wrapped[:12], wrapped[12:], None)
    blob = base64.b64decode(ciphertext)
    return AESGCM(dek).decrypt(blob[:12], blob[12:], None).decode("utf-8")


# --------------------------------------------------------------------------
# misc
# --------------------------------------------------------------------------
def constant_time_compare(a: str, b: str) -> bool:
    return hmac.compare_digest(a, b)


def content_address(payload: bytes) -> str:
    """Content-addressable key for deduplicating SERP payloads (section 56)."""
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def monotonic_ms() -> float:
    return time.perf_counter() * 1000.0


__all__ = [
    "API_KEY_PATTERN",
    "CREDENTIAL_ALGO",
    "EnvelopeCiphertext",
    "MintedApiKey",
    "ParsedApiKey",
    "api_key_display",
    "constant_time_compare",
    "content_address",
    "create_token",
    "credential_fingerprint",
    "decode_token",
    "decrypt_credential",
    "encrypt_credential",
    "generate_opaque_token",
    "generate_project_prefix",
    "hash_api_key",
    "hash_opaque_token",
    "hash_password",
    "mint_api_key",
    "monotonic_ms",
    "parse_api_key",
    "password_needs_rehash",
    "verify_api_key",
    "verify_password",
]
