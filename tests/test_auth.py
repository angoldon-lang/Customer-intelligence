"""Tests for the single-admin authentication."""

import time

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models import Base
from app.services import auth


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


@pytest.fixture(autouse=True)
def clean_throttle():
    auth.login_throttle.record_success()
    yield
    auth.login_throttle.record_success()


PASSWORD = "unaPasswordLunga1"


# --- password hashing -------------------------------------------------

def test_hash_is_not_the_password_and_verifies():
    stored = auth.hash_password(PASSWORD)

    assert PASSWORD not in stored
    assert auth.verify_password(PASSWORD, stored)


def test_wrong_password_is_rejected():
    stored = auth.hash_password(PASSWORD)

    assert not auth.verify_password("qualcos'altro", stored)
    assert not auth.verify_password("", stored)


def test_same_password_hashes_differently_each_time():
    """A per-password salt: two admins with the same password don't match."""
    assert auth.hash_password(PASSWORD) != auth.hash_password(PASSWORD)


def test_malformed_stored_hash_never_authenticates():
    for broken in ["", "not-a-hash", "pbkdf2_sha256$abc", "md5$1$aa$bb", None]:
        assert not auth.verify_password(PASSWORD, broken)


def test_password_rules():
    assert auth.password_problem("") is not None
    assert auth.password_problem("corta") is not None
    assert auth.password_problem(PASSWORD) is None
    assert auth.password_problem(PASSWORD, "diversa") is not None
    assert auth.password_problem(PASSWORD, PASSWORD) is None


# --- session tokens ---------------------------------------------------

def test_valid_token_round_trips():
    token = auth.create_session_token("admin", "un-segreto")

    assert auth.read_session_token(token, "un-segreto") == "admin"


def test_tampered_token_is_refused():
    token = auth.create_session_token("admin", "un-segreto")

    signature = token.partition(".")[2]
    # A payload claiming to be someone else, kept with the real signature:
    # the signature covers the payload, so it must no longer match.
    forged = auth.create_session_token("altro-utente", "qualsiasi-segreto").partition(".")[0]

    assert auth.read_session_token(token[:-2] + "xx", "un-segreto") is None  # signature
    assert auth.read_session_token(f"{forged}.{signature}", "un-segreto") is None  # payload
    assert auth.read_session_token(token, "un-altro-segreto") is None  # wrong key
    assert auth.read_session_token("", "un-segreto") is None
    assert auth.read_session_token("senza-punto", "un-segreto") is None


def test_expired_token_is_refused():
    token = auth.create_session_token("admin", "un-segreto", ttl_hours=-1)

    assert auth.read_session_token(token, "un-segreto") is None


def test_secret_is_created_once_and_reused(db):
    first = auth.get_secret(db)

    assert first
    assert auth.get_secret(db) == first


def test_rotating_the_secret_invalidates_existing_sessions(db):
    token = auth.create_session_token("admin", auth.get_secret(db))
    assert auth.read_session_token(token, auth.get_secret(db)) == "admin"

    auth.rotate_secret(db)

    assert auth.read_session_token(token, auth.get_secret(db)) is None


# --- admin account ----------------------------------------------------

def test_no_admin_until_one_is_created(db):
    assert auth.is_configured(db) is False

    auth.set_admin(db, "admin", PASSWORD)

    assert auth.is_configured(db) is True


def test_login_accepts_only_the_right_credentials(db):
    auth.set_admin(db, "admin", PASSWORD)

    assert auth.verify_login(db, "admin", PASSWORD)[0] is True

    auth.login_throttle.record_success()
    assert auth.verify_login(db, "admin", "sbagliata")[0] is False

    auth.login_throttle.record_success()
    assert auth.verify_login(db, "altro", PASSWORD)[0] is False


def test_login_error_does_not_reveal_which_field_was_wrong(db):
    auth.set_admin(db, "admin", PASSWORD)

    _, wrong_user = auth.verify_login(db, "sconosciuto", PASSWORD)
    auth.login_throttle.record_success()
    _, wrong_password = auth.verify_login(db, "admin", "sbagliata")

    assert wrong_user == wrong_password


def test_a_non_ascii_username_fails_cleanly(db):
    """An accented username must be rejected, not crash the login."""
    auth.set_admin(db, "admin", PASSWORD)

    ok, error = auth.verify_login(db, "andrèa", PASSWORD)

    assert ok is False
    assert error == "Credenziali non valide"


def test_a_non_ascii_username_can_be_used(db):
    auth.set_admin(db, "andrèa", PASSWORD)

    assert auth.verify_login(db, "andrèa", PASSWORD)[0] is True


def test_password_is_never_stored_in_clear(db):
    from app.models import AppSetting

    auth.set_admin(db, "admin", PASSWORD)

    stored = [row.value for row in db.query(AppSetting).all()]
    assert all(PASSWORD not in (value or "") for value in stored)


def test_a_weak_password_cannot_be_set(db):
    with pytest.raises(ValueError):
        auth.set_admin(db, "admin", "corta")

    assert auth.is_configured(db) is False


# --- brute force ------------------------------------------------------

def test_repeated_failures_lock_logins_out(db):
    auth.set_admin(db, "admin", PASSWORD)

    for _ in range(auth.MAX_FAILED_ATTEMPTS):
        auth.verify_login(db, "admin", "sbagliata")

    ok, error = auth.verify_login(db, "admin", PASSWORD)
    assert ok is False, "the correct password must not work during a lockout"
    assert "Riprova tra" in error


def test_lockout_expires(db, monkeypatch):
    auth.set_admin(db, "admin", PASSWORD)
    for _ in range(auth.MAX_FAILED_ATTEMPTS):
        auth.verify_login(db, "admin", "sbagliata")
    assert auth.login_throttle.is_locked()

    now = time.monotonic()
    monkeypatch.setattr(auth.time, "monotonic", lambda: now + auth.LOCKOUT_SECONDS + 1)

    assert auth.verify_login(db, "admin", PASSWORD)[0] is True


def test_a_successful_login_clears_the_failure_count(db):
    auth.set_admin(db, "admin", PASSWORD)

    for _ in range(auth.MAX_FAILED_ATTEMPTS - 1):
        auth.verify_login(db, "admin", "sbagliata")
    auth.verify_login(db, "admin", PASSWORD)

    assert auth.login_throttle.failures == 0


# --- settings store isolation ----------------------------------------

def test_credentials_cannot_be_written_through_the_settings_form(db):
    """/api/settings must never be able to set the password hash directly."""
    from app.services import settings_store

    auth.set_admin(db, "admin", PASSWORD)
    original = settings_store.get_setting(db, auth.PASSWORD_HASH_KEY)

    settings_store.save_settings(db, {
        auth.PASSWORD_HASH_KEY: auth.hash_password("scelta-dall-attaccante"),
        auth.SECRET_KEY: "segreto-noto",
    })

    assert settings_store.get_setting(db, auth.PASSWORD_HASH_KEY) == original
    assert settings_store.get_setting(db, auth.SECRET_KEY) != "segreto-noto"


def test_credentials_are_not_exposed_by_the_settings_api(db):
    from app.services import settings_store

    auth.set_admin(db, "admin", PASSWORD)
    auth.get_secret(db)

    values = settings_store.get_all(db)

    assert auth.PASSWORD_HASH_KEY not in values
    assert auth.SECRET_KEY not in values
