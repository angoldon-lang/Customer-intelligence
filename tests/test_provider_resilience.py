"""Tests for provider resilience: transient errors must not kill a run."""

import pytest

from app.providers import google_news_rss
from app.providers.google_news_rss import GoogleNewsRSSProvider


FEED = b"""<?xml version="1.0"?>
<rss version="2.0"><channel><title>news</title>
<item>
  <title>Aquafil investe in un nuovo impianto - Il Sole 24 Ore</title>
  <link>https://news.google.com/rss/articles/ABC123</link>
  <description>&lt;a href="x"&gt;Aquafil investe&lt;/a&gt;</description>
</item>
</channel></rss>"""


class FakeResponse:
    def __init__(self, status_code, content=b"", headers=None):
        self.status_code = status_code
        self.content = content
        self.headers = headers or {}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise google_news_rss.requests.RequestException(f"HTTP {self.status_code}")


@pytest.fixture
def no_sleep(monkeypatch):
    """Keep tests instant: the provider's waits are what we're exercising."""
    slept = []
    monkeypatch.setattr(google_news_rss.time, "sleep", lambda s: slept.append(s))
    return slept


@pytest.fixture
def provider(no_sleep):
    return GoogleNewsRSSProvider()


def fake_get(responses):
    """Serve the given responses in order, then repeat the last one."""
    calls = {"n": 0}

    def _get(url, params=None, timeout=None, headers=None):
        index = min(calls["n"], len(responses) - 1)
        calls["n"] += 1
        return responses[index]

    _get.calls = calls
    return _get


def test_transient_503_is_retried_and_succeeds(provider, monkeypatch, no_sleep):
    """One 503 burst must not lose the company's news."""
    get = fake_get([FakeResponse(503), FakeResponse(200, FEED)])
    monkeypatch.setattr(google_news_rss.requests, "get", get)

    results = provider.search_company_news("Aquafil S.p.A.")

    assert len(results) == 1
    assert provider.last_call_error is None
    assert provider.blocked is False
    assert no_sleep, "the retry should have backed off before trying again"


def test_retry_honours_retry_after_header(provider, monkeypatch, no_sleep):
    get = fake_get([FakeResponse(429, headers={"Retry-After": "42"}), FakeResponse(200, FEED)])
    monkeypatch.setattr(google_news_rss.requests, "get", get)

    provider.search_company_news("Aquafil S.p.A.")

    assert 42 in no_sleep


def test_a_single_failing_company_does_not_pause_the_provider(provider, monkeypatch):
    get = fake_get([FakeResponse(503)])
    monkeypatch.setattr(google_news_rss.requests, "get", get)

    assert provider.search_company_news("Azienda Uno") == []
    assert provider.blocked is False, "one bad company must not stop the run"


def test_provider_pauses_only_after_repeated_failures(provider, monkeypatch):
    get = fake_get([FakeResponse(503)])
    monkeypatch.setattr(google_news_rss.requests, "get", get)

    for i in range(google_news_rss.MAX_CONSECUTIVE_FAILURES):
        assert provider.blocked is False
        provider.search_company_news(f"Azienda {i}")

    assert provider.blocked is True


def test_pause_reopens_after_the_cooldown(provider, monkeypatch):
    get = fake_get([FakeResponse(503)])
    monkeypatch.setattr(google_news_rss.requests, "get", get)

    for i in range(google_news_rss.MAX_CONSECUTIVE_FAILURES):
        provider.search_company_news(f"Azienda {i}")
    assert provider.blocked is True

    # Companies searched during the pause are reported as paused, not as a
    # genuine "no news found".
    assert provider.search_company_news("Durante la pausa") == []
    assert "pausa" in provider.last_call_error

    # Once the cooldown elapses the provider tries again by itself.
    provider._blocked_until = 0
    monkeypatch.setattr(google_news_rss.requests, "get", fake_get([FakeResponse(200, FEED)]))

    results = provider.search_company_news("Dopo la pausa")
    assert provider.blocked is False
    assert len(results) == 1


def test_success_resets_the_failure_counter(provider, monkeypatch):
    monkeypatch.setattr(google_news_rss.requests, "get", fake_get([FakeResponse(503)]))
    provider.search_company_news("Azienda Uno")
    assert provider._consecutive_failures == 1

    monkeypatch.setattr(google_news_rss.requests, "get", fake_get([FakeResponse(200, FEED)]))
    provider.search_company_news("Azienda Due")
    assert provider._consecutive_failures == 0


def test_403_is_not_retried(provider, monkeypatch, no_sleep):
    """A consent/robot wall won't clear by asking again."""
    get = fake_get([FakeResponse(403)])
    monkeypatch.setattr(google_news_rss.requests, "get", get)

    provider.search_company_news("Azienda")

    assert get.calls["n"] == 1
    assert provider.last_call_error == "HTTP 403"
