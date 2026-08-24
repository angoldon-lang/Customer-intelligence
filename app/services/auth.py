"""Single-admin authentication.

Deliberately small: one administrator, a password hashed with PBKDF2, and
a signed session cookie. No new dependencies - everything here is stdlib,
so upgrading the app stays a plain `git pull`.

There is no default password on purpose: until one is set, every page
redirects to the first-run setup so the dashboard is never briefly
reachable with a well-known credential.
"""

import base64
import hashlib
import hmac
import json
import secrets
import time
from typing import Optional, Tuple

from sqlalchemy.orm import Session

from app.config import settings

# Keys held in app_settings (see settings_store).
USERNAME_KEY = "ADMIN_USERNAME"
PASSWORD_HASH_KEY = "ADMIN_PASSWORD_HASH"
SECRET_KEY = "SESSION_SECRET"

SESSION_COOKIE = "ci_session"

PBKDF2_ITERATIONS = 240_000
SALT_BYTES = 16

# Brute-force guard. One admin on a local dashboard, so a simple global
# counter with a lockout window is enough - no per-IP bookkeeping.
MAX_FAILED_ATTEMPTS = 8
LOCKOUT_SECONDS = 300


def hash_password(password: str, salt: bytes = None) -> str:
    """Return 'pbkdf2_sha256$iterations$salt_hex$hash_hex'."""
    if not password:
        raise ValueError("La password non puo' essere vuota")

    salt = salt or secrets.token_bytes(SALT_BYTES)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    """Constant-time check of a password against a stored hash."""
    if not password or not stored:
        return False

    try:
        algorithm, iterations, salt_hex, hash_hex = stored.split("$")
        if algorithm != "pbkdf2_sha256":
            return False
        digest = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), int(iterations)
        )
    except (ValueError, TypeError):
        return False

    return hmac.compare_digest(digest.hex(), hash_hex)


def password_problem(password: str, confirm: str = None) -> Optional[str]:
    """Reason the password is unacceptable, or None if it's fine."""
    if not password:
        return "Inserisci una password"
    if len(password) < 10:
        return "La password deve avere almeno 10 caratteri"
    if confirm is not None and password != confirm:
        return "Le due password non coincidono"
    return None


def _b64encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def create_session_token(username: str, secret: str, ttl_hours: int = None) -> str:
    """Signed 'payload.signature' token; the payload carries its expiry."""
    ttl_hours = ttl_hours or settings.SESSION_TTL_HOURS
    payload = json.dumps(
        {"u": username, "exp": int(time.time()) + ttl_hours * 3600},
        separators=(",", ":"),
    ).encode("utf-8")

    encoded = _b64encode(payload)
    signature = hmac.new(secret.encode("utf-8"), encoded.encode("ascii"), hashlib.sha256).digest()
    return f"{encoded}.{_b64encode(signature)}"


def read_session_token(token: str, secret: str) -> Optional[str]:
    """Username carried by a valid, unexpired token - otherwise None."""
    if not token or not secret or "." not in token:
        return None

    encoded, _, provided = token.partition(".")
    expected = hmac.new(secret.encode("utf-8"), encoded.encode("ascii"), hashlib.sha256).digest()

    try:
        if not hmac.compare_digest(_b64decode(provided), expected):
            return None
        payload = json.loads(_b64decode(encoded))
    except (ValueError, TypeError, json.JSONDecodeError):
        return None

    if not isinstance(payload, dict) or payload.get("exp", 0) < time.time():
        return None

    username = payload.get("u")
    return username if isinstance(username, str) else None


def get_secret(db: Session) -> str:
    """
    The key that signs session cookies, created on first use.

    Persisted so sessions survive a restart; rotating it (deleting the row)
    simply logs everyone out.
    """
    from app.services import settings_store

    secret = settings_store.get_setting(db, SECRET_KEY)
    if not secret:
        secret = secrets.token_urlsafe(48)
        settings_store.save_settings(db, {SECRET_KEY: secret}, allow_internal=True)
    return secret


def rotate_secret(db: Session) -> str:
    """
    Replace the signing key, invalidating every existing session.

    Used when the password changes: if it was changed because someone else
    got in, leaving their cookie working until it expired would defeat the
    point.
    """
    from app.services import settings_store

    secret = secrets.token_urlsafe(48)
    settings_store.save_settings(db, {SECRET_KEY: secret}, allow_internal=True)
    return secret


def is_configured(db: Session) -> bool:
    """True once an administrator password exists."""
    from app.services import settings_store

    return bool(settings_store.get_setting(db, PASSWORD_HASH_KEY))


def get_username(db: Session) -> str:
    from app.services import settings_store

    return settings_store.get_setting(db, USERNAME_KEY) or settings.ADMIN_USERNAME


def set_admin(db: Session, username: str, password: str) -> None:
    """Create or replace the administrator credentials."""
    from app.services import settings_store

    problem = password_problem(password)
    if problem:
        raise ValueError(problem)

    settings_store.save_settings(db, {
        USERNAME_KEY: (username or settings.ADMIN_USERNAME).strip(),
        PASSWORD_HASH_KEY: hash_password(password),
    }, allow_internal=True)


class LoginThrottle:
    """Locks logins out for a while after repeated failures."""

    def __init__(self):
        self.failures = 0
        self.locked_until = 0.0

    def seconds_remaining(self) -> int:
        return max(0, int(self.locked_until - time.monotonic()))

    def is_locked(self) -> bool:
        if self.locked_until and time.monotonic() >= self.locked_until:
            # Lockout served: start over.
            self.locked_until = 0.0
            self.failures = 0
        return self.seconds_remaining() > 0

    def record_failure(self) -> None:
        self.failures += 1
        if self.failures >= MAX_FAILED_ATTEMPTS:
            self.locked_until = time.monotonic() + LOCKOUT_SECONDS

    def record_success(self) -> None:
        self.failures = 0
        self.locked_until = 0.0


login_throttle = LoginThrottle()


def verify_login(db: Session, username: str, password: str) -> Tuple[bool, Optional[str]]:
    """
    Check credentials. Returns (ok, error_message).

    The error never says whether it was the username or the password that
    was wrong.
    """
    from app.services import settings_store

    if login_throttle.is_locked():
        wait = login_throttle.seconds_remaining()
        return False, f"Troppi tentativi falliti. Riprova tra {wait} secondi."

    stored_hash = settings_store.get_setting(db, PASSWORD_HASH_KEY)
    expected_user = get_username(db)

    # Always run the hash comparison, even for a wrong username, so the
    # response time doesn't reveal whether the username exists.
    password_ok = verify_password(password or "", stored_hash or "")
    # Compared as bytes: compare_digest refuses str with non-ASCII
    # characters, so an accented username would raise instead of simply
    # failing to match.
    user_ok = hmac.compare_digest(
        (username or "").strip().encode("utf-8"),
        (expected_user or "").encode("utf-8"),
    )

    if password_ok and user_ok:
        login_throttle.record_success()
        return True, None

    login_throttle.record_failure()
    return False, "Credenziali non valide"
