"""Tests for SMTP sending: TLS mode selection and error diagnostics."""

import smtplib

import pytest

from app.services import email_sender as email_module
from app.services.email_sender import EmailSender


@pytest.fixture
def sender():
    s = EmailSender()
    s.smtp_host = "smtp.gmail.com"
    s.smtp_port = 587
    s.smtp_user = "andrea@example.com"
    s.smtp_password = "una-password"
    s.from_email = "andrea@example.com"
    s.from_name = "Andrea"
    s.use_ssl = False
    return s


class FakeServer:
    def __init__(self, *args, **kwargs):
        self.args = args
        self.started_tls = False
        self.logged_in = False
        self.sent = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def ehlo(self):
        pass

    def has_extn(self, name):
        return name == "starttls"

    def starttls(self):
        self.started_tls = True

    def login(self, user, password):
        self.logged_in = True

    def send_message(self, msg):
        self.sent.append(msg)


def patch_smtp(monkeypatch):
    """Record which smtplib class gets used."""
    used = {}

    def make(kind):
        def _factory(host, port, timeout=None):
            server = FakeServer(host, port)
            used["kind"] = kind
            used["server"] = server
            used["port"] = port
            return server
        return _factory

    monkeypatch.setattr(email_module.smtplib, "SMTP", make("SMTP"))
    monkeypatch.setattr(email_module.smtplib, "SMTP_SSL", make("SMTP_SSL"))
    return used


# --- TLS mode ---------------------------------------------------------

def test_port_587_uses_starttls(sender, monkeypatch):
    used = patch_smtp(monkeypatch)
    sender.smtp_port = 587

    sender.test_connection()

    assert used["kind"] == "SMTP"
    assert used["server"].started_tls is True


def test_port_465_uses_implicit_ssl(sender, monkeypatch):
    """The old code called starttls() on 465 and hung until timeout."""
    used = patch_smtp(monkeypatch)
    sender.smtp_port = 465

    sender.test_connection()

    assert used["kind"] == "SMTP_SSL"
    assert used["server"].started_tls is False


def test_ssl_can_be_forced_on_any_port(sender, monkeypatch):
    used = patch_smtp(monkeypatch)
    sender.smtp_port = 2465
    sender.use_ssl = True

    sender.test_connection()

    assert used["kind"] == "SMTP_SSL"


def test_a_server_without_starttls_is_not_forced(sender, monkeypatch):
    """Some internal relays accept plain SMTP; don't crash on them."""
    used = patch_smtp(monkeypatch)
    monkeypatch.setattr(FakeServer, "has_extn", lambda self, name: False)

    result = sender.test_connection()

    assert result["success"] is True
    assert used["server"].started_tls is False


# --- configuration validation -----------------------------------------

@pytest.mark.parametrize("missing", ["smtp_host", "smtp_user", "smtp_password", "from_email"])
def test_incomplete_configuration_is_reported_before_connecting(sender, monkeypatch, missing):
    used = patch_smtp(monkeypatch)
    setattr(sender, missing, "")

    result = sender.send_report(["x@y.it"], "Oggetto", "<p>ciao</p>")

    assert result["success"] is False
    assert "non configurat" in result["error"]
    assert "server" not in used, "it must not dial out with a broken config"


# --- error diagnostics ------------------------------------------------

def test_gmail_auth_failure_points_at_the_app_password(sender):
    error = smtplib.SMTPAuthenticationError(535, b"5.7.8 Username and Password not accepted")

    message = sender.explain_error(error)

    assert "password per le app" in message
    assert "myaccount.google.com/apppasswords" in message


def test_microsoft_auth_failure_points_at_smtp_auth(sender):
    sender.smtp_host = "smtp.office365.com"
    error = smtplib.SMTPAuthenticationError(535, b"5.7.139 Authentication unsuccessful")

    message = sender.explain_error(error)

    assert "SMTP AUTH" in message
    assert "amministratore" in message


def test_a_refused_sender_explains_the_mismatch(sender):
    sender.from_email = "altro@example.com"
    error = smtplib.SMTPSenderRefused(553, b"5.7.0 not allowed", "altro@example.com")

    message = sender.explain_error(error)

    assert "altro@example.com" in message
    assert "andrea@example.com" in message


def test_a_timeout_suggests_the_port(sender):
    message = sender.explain_error(TimeoutError("timed out"))

    assert "465" in message and "587" in message


def test_an_unknown_host_is_named(sender):
    message = sender.explain_error(OSError("getaddrinfo failed"))

    assert "smtp.gmail.com" in message


def test_an_unrecognised_error_is_passed_through(sender):
    message = sender.explain_error(RuntimeError("qualcosa di strano"))

    assert message == "qualcosa di strano"


# --- sending ----------------------------------------------------------

def test_a_report_is_sent_with_both_parts(sender, monkeypatch):
    used = patch_smtp(monkeypatch)

    result = sender.send_report(["a@x.it", "b@x.it"], "Report", "<p>ciao</p>", "ciao")

    assert result["success"] is True
    assert result["recipients"] == 2

    message = used["server"].sent[0]
    types = [part.get_content_type() for part in message.walk()]
    assert "text/plain" in types
    assert "text/html" in types
    assert message["From"] == "Andrea <andrea@example.com>"


def test_a_send_failure_is_explained_not_raised(sender, monkeypatch):
    def failing(host, port, timeout=None):
        raise smtplib.SMTPAuthenticationError(535, b"5.7.8 Username and Password not accepted")

    monkeypatch.setattr(email_module.smtplib, "SMTP", failing)

    result = sender.send_report(["a@x.it"], "Report", "<p>ciao</p>")

    assert result["success"] is False
    assert "password per le app" in result["error"]
