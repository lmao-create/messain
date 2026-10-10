"""Password hashing and token helpers.

Passwords are hashed with PBKDF2-HMAC-SHA256 using the standard library only,
so no native build tools are required. Plaintext passwords are never stored.
"""

import base64
import hashlib
import hmac
import secrets

_ALGORITHM = "pbkdf2_sha256"
_ITERATIONS = 600_000
_SALT_BYTES = 16


def hash_password(password: str) -> str:
    """Return a salted, iterated hash string for the given password."""
    salt = secrets.token_bytes(_SALT_BYTES)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _ITERATIONS)
    return "$".join(
        [
            _ALGORITHM,
            str(_ITERATIONS),
            base64.b64encode(salt).decode("ascii"),
            base64.b64encode(digest).decode("ascii"),
        ]
    )


def verify_password(password: str, stored: str) -> bool:
    """Constant-time check of a password against a stored hash string."""
    try:
        algorithm, iterations_raw, salt_b64, digest_b64 = stored.split("$")
        iterations = int(iterations_raw)
        if algorithm != _ALGORITHM:
            return False
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(digest_b64)
    except (ValueError, TypeError):
        return False
    actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return hmac.compare_digest(actual, expected)


# Precomputed hash used to equalise login timing for unknown usernames.
_DUMMY_HASH = hash_password("timing-equalisation-dummy")


def dummy_verify(password: str) -> None:
    """Spend the same CPU time as a real password check without validating anything."""
    verify_password(password, _DUMMY_HASH)


def new_token() -> str:
    """Generate a random session token."""
    return secrets.token_urlsafe(32)
