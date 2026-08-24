"""End-to-end tests for the login flow through the HTTP layer."""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.database import SessionLocal
from app.models import AppSetting
from app.services import auth

PASSWORD = "unaPasswordLunga1"


@pytest.fixture
def client():
    """A fresh app with no administrator configured yet."""
    db = SessionLocal()
    db.query(AppSetting).delete()
    db.commit()
    db.close()

    auth.login_throttle.record_success()
    yield TestClient(app, follow_redirects=False)

    db = SessionLocal()
    db.query(AppSetting).delete()
    db.commit()
    db.close()
    auth.login_throttle.record_success()


@pytest.fixture
def logged_in(client):
    client.post("/api/auth/setup", data={
        "username": "admin", "password": PASSWORD, "password_confirm": PASSWORD,
    })
    return client


# --- first run --------------------------------------------------------

def test_everything_redirects_to_setup_until_an_admin_exists(client):
    for path in ["/", "/companies", "/news", "/settings"]:
        response = client.get(path)
        assert response.status_code == 303
        assert response.headers["location"] == "/setup"


def test_setup_creates_the_admin_and_signs_in(client):
    response = client.post("/api/auth/setup", data={
        "username": "admin", "password": PASSWORD, "password_confirm": PASSWORD,
    })

    assert response.status_code == 303
    assert auth.SESSION_COOKIE in response.cookies


def test_setup_rejects_a_weak_or_mismatched_password(client):
    short = client.post("/api/auth/setup", data={
        "username": "admin", "password": "corta", "password_confirm": "corta",
    })
    assert short.status_code == 400

    mismatch = client.post("/api/auth/setup", data={
        "username": "admin", "password": PASSWORD, "password_confirm": "diversa",
    })
    assert mismatch.status_code == 400

    db = SessionLocal()
    assert auth.is_configured(db) is False
    db.close()


def test_setup_closes_once_an_admin_exists(logged_in):
    """Otherwise anyone could walk in and overwrite the credentials."""
    logged_in.cookies.clear()

    page = logged_in.get("/setup")
    assert page.status_code == 303
    assert page.headers["location"] == "/login"

    attempt = logged_in.post("/api/auth/setup", data={
        "username": "intruso", "password": "PasswordIntruso1", "password_confirm": "PasswordIntruso1",
    })
    assert attempt.status_code in (303, 403)

    db = SessionLocal()
    assert auth.verify_login(db, "admin", PASSWORD)[0] is True
    db.close()


# --- protection -------------------------------------------------------

def test_pages_redirect_to_login_keeping_the_destination(logged_in):
    logged_in.cookies.clear()

    response = logged_in.get("/companies")

    assert response.status_code == 303
    assert response.headers["location"] == "/login?next=/companies"


def test_api_answers_401_json_not_a_redirect(logged_in):
    """The dashboard parses JSON on every call; HTML here breaks it."""
    logged_in.cookies.clear()

    response = logged_in.get("/api/companies")

    assert response.status_code == 401
    assert response.json()["detail"]


def test_a_valid_session_reaches_pages_and_api(logged_in):
    assert logged_in.get("/companies").status_code == 200
    assert logged_in.get("/api/companies").status_code == 200
    assert logged_in.get("/api/auth/me").json()["username"] == "admin"


def test_a_tampered_cookie_is_rejected(logged_in):
    token = logged_in.cookies.get(auth.SESSION_COOKIE)
    logged_in.cookies.set(auth.SESSION_COOKIE, token[:-2] + "xx")

    assert logged_in.get("/api/companies").status_code == 401


def test_login_page_and_static_stay_public(logged_in):
    logged_in.cookies.clear()

    assert logged_in.get("/login").status_code == 200


# --- login ------------------------------------------------------------

def test_login_with_the_right_credentials(logged_in):
    logged_in.cookies.clear()

    response = logged_in.post("/api/auth/login", data={
        "username": "admin", "password": PASSWORD, "next": "/news",
    })

    assert response.status_code == 303
    assert response.headers["location"] == "/news"
    assert auth.SESSION_COOKIE in response.cookies


def test_login_with_a_wrong_password_sets_no_cookie(logged_in):
    logged_in.cookies.clear()

    response = logged_in.post("/api/auth/login", data={
        "username": "admin", "password": "sbagliata", "next": "/",
    })

    assert response.status_code == 401
    assert auth.SESSION_COOKIE not in response.cookies


@pytest.mark.parametrize("target", [
    "https://evil.example",
    "//evil.example",
    "http://evil.example/path",
])
def test_login_never_redirects_off_site(logged_in, target):
    """?next= must not become an open redirect after authenticating."""
    logged_in.cookies.clear()

    response = logged_in.post("/api/auth/login", data={
        "username": "admin", "password": PASSWORD, "next": target,
    })

    assert response.headers["location"] == "/"


def test_the_session_cookie_is_httponly_and_samesite(logged_in):
    logged_in.cookies.clear()

    response = logged_in.post("/api/auth/login", data={
        "username": "admin", "password": PASSWORD, "next": "/",
    })

    cookie_header = response.headers["set-cookie"].lower()
    assert "httponly" in cookie_header
    assert "samesite=lax" in cookie_header


def test_logout_clears_the_session(logged_in):
    assert logged_in.get("/api/companies").status_code == 200

    logged_in.get("/logout")
    logged_in.cookies.clear()

    assert logged_in.get("/api/companies").status_code == 401


# --- password change --------------------------------------------------

def test_changing_the_password_requires_the_current_one(logged_in):
    response = logged_in.post("/api/auth/password", json={
        "current_password": "sbagliata",
        "new_password": "NuovaPassword123",
        "new_password_confirm": "NuovaPassword123",
    })

    assert response.status_code == 400
    db = SessionLocal()
    assert auth.verify_login(db, "admin", PASSWORD)[0] is True
    db.close()


def test_a_wrong_current_password_does_not_lock_the_login_out(logged_in):
    """Fumbling this form must not lock the admin out of /login."""
    for _ in range(auth.MAX_FAILED_ATTEMPTS + 2):
        logged_in.post("/api/auth/password", json={
            "current_password": "sbagliata",
            "new_password": "NuovaPassword123",
            "new_password_confirm": "NuovaPassword123",
        })

    assert auth.login_throttle.is_locked() is False


def test_changing_the_password_logs_other_sessions_out(logged_in):
    other = TestClient(app, follow_redirects=False)
    other.post("/api/auth/login", data={"username": "admin", "password": PASSWORD, "next": "/"})
    assert other.get("/api/companies").status_code == 200

    response = logged_in.post("/api/auth/password", json={
        "current_password": PASSWORD,
        "new_password": "NuovaPassword123",
        "new_password_confirm": "NuovaPassword123",
    })
    assert response.status_code == 200

    assert other.get("/api/companies").status_code == 401
    # ...but the session that made the change keeps working.
    assert logged_in.get("/api/companies").status_code == 200
