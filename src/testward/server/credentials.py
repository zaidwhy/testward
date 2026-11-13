"""Password hashing and opaque tokens. Only hashes are ever stored."""

from __future__ import annotations

import hashlib
import hmac
import secrets

SCRYPT_N, SCRYPT_R, SCRYPT_P = 2**14, 8, 1
PASSWORD_MIN, PASSWORD_MAX = 10, 200


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P)
    return f"scrypt${salt.hex()}${digest.hex()}"


def password_matches(password: str, stored: str) -> bool:
    try:
        scheme, salt_hex, digest_hex = stored.split("$")
    except ValueError:
        return False
    if scheme != "scrypt":
        return False
    digest = hashlib.scrypt(
        password.encode(), salt=bytes.fromhex(salt_hex), n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P
    )
    return hmac.compare_digest(digest, bytes.fromhex(digest_hex))


def new_token(prefix: str = "") -> str:
    return prefix + secrets.token_urlsafe(32)


def token_digest(token: str) -> str:
    """Tokens are 256 bits of randomness, so a plain SHA-256 lookup key is enough."""
    return hashlib.sha256(token.encode()).hexdigest()
