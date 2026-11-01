"""GeoFlood AI backend - password hashing (scrypt, Python standard library) and password rules."""

import base64
import hashlib
import hmac
import secrets

SCRYPT_N, SCRYPT_R, SCRYPT_P = 2 ** 14, 8, 1
SALT_BYTES, KEY_BYTES = 16, 32
MAX_MEMORY = 2 ** 26            # 64 MiB limit for scrypt; these settings need about 16 MiB
MIN_LENGTH, MAX_LENGTH = 10, 128


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def hash_password(password: str) -> str:
    """Return 'scrypt$N$r$p$salt$key'. A new random salt is used on every call."""
    salt = secrets.token_bytes(SALT_BYTES)
    key = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P,
                         dklen=KEY_BYTES, maxmem=MAX_MEMORY)
    return f"scrypt${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}${_b64(salt)}${_b64(key)}"


def verify_password(password: str, stored: str) -> bool:
    """True only if the password matches. A malformed stored value gives False, never an exception."""
    try:
        scheme, n, r, p, salt_b64, key_b64 = stored.split("$")
        if scheme != "scrypt":
            return False
        salt = base64.b64decode(salt_b64, validate=True)
        expected = base64.b64decode(key_b64, validate=True)
        actual = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=int(n), r=int(r), p=int(p),
                                dklen=len(expected), maxmem=MAX_MEMORY)
    except (ValueError, TypeError, AttributeError):
        return False
    return hmac.compare_digest(actual, expected)


def check_password_rules(password: str, username: str = "") -> None:
    """Raise ValueError with a user-friendly message if the password is not acceptable."""
    try:
        password.encode("utf-8")
    except UnicodeEncodeError:
        raise ValueError("The password contains characters that cannot be stored.")
    if len(password) < MIN_LENGTH:
        raise ValueError(f"The password must be at least {MIN_LENGTH} characters long.")
    if len(password) > MAX_LENGTH:
        raise ValueError(f"The password must be at most {MAX_LENGTH} characters long.")
    if not password.strip():
        raise ValueError("The password cannot be only spaces.")
    if username and password.lower() == username.lower():
        raise ValueError("The password must not be the same as the username.")


# Checked against when the username does not exist, so an unknown user costs the same time as a wrong password
DUMMY_HASH = hash_password("timing-equalizer-not-a-real-password")
