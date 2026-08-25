"""Tests for the APITube provider.

APITube is metered, so most of these are about *not* spending requests.
"""

import pytest

from app.providers import apitube as apitube_module
from app.providers.apitube import APITubeProvider


RESPONSE = {
    "results": [
        {
            "title": "Aquafil investe in un nuovo impianto",
            "href": "https://ilsole24ore.com/aquafil-impianto",
            "description": "  Il gruppo   annuncia  un investimento da 20 milioni. ",
            "body": "Testo completo dell'articolo...",
            "published_at": "2026-08-20T10:30:00Z",
            "source": {"name": "Il Sole 24 Ore", "domain": "ilsole24ore.com"},
        },
        {
            "title": "Senza url",
            "description": "va scartata",
        },
    ]
}


class FakeResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload if payload is not None else RESPONSE

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise apitube_module.requests.RequestException(f"HTTP {self.status_code}")


@pytest.fixture
def provider():
    return APITubeProvider(api_key="chiave-di-prova")


def capture_get(monkeypatch, response=None):
    """Record the calls made to the API."""
    calls = []

    def _get(url, params=None, timeout=None, headers=None):
        calls.append({"url": url, "params": params, "headers": headers})
        return response or FakeResponse()

    monkeypatch.setattr(apitube_module.requests, "get", _get)
    return calls


# --- request shape ----------------------------------------------------

def test_api_key_goes_in_the_header_not_the_url(provider, monkeypatch):
    calls = capture_get(monkeypatch)

    provider.search_company_news("Aquafil S.p.A.")

    assert calls[0]["headers"]["X-API-Key"] == "chiave-di-prova"
    assert "chiave-di-prova" not in str(calls[0]["params"])


def test_company_name_is_searched_as_an_exact_phrase(provider, monkeypatch):
    """Unquoted, "Sag Tubi Tredozio" would match those words separately."""
    calls = capture_get(monkeypatch)

    provider.search_company_news("Sag Tubi Tredozio srl")

    assert calls[0]["params"]["title"] == '"Sag Tubi Tredozio srl"'


def test_search_is_limited_to_the_configured_language_and_period(provider, monkeypatch):
    calls = capture_get(monkeypatch)

    provider.search_company_news("Aquafil S.p.A.")

    params = calls[0]["params"]
    assert params["language.code"]
    assert params["published_at.start"]


# --- response parsing -------------------------------------------------

def test_articles_are_parsed(provider, monkeypatch):
    capture_get(monkeypatch)

    results = provider.search_company_news("Aquafil S.p.A.")

    assert len(results) == 1  # the entry with no url is dropped
    article = results[0]
    assert article.title == "Aquafil investe in un nuovo impianto"
    assert article.url == "https://ilsole24ore.com/aquafil-impianto"
    assert article.source_name == "Il Sole 24 Ore"
    assert article.source_type == "apitube"
    assert article.published_date.year == 2026
    assert article.summary == "Il gruppo annuncia un investimento da 20 milioni."
    assert provider.last_call_error is None


def test_full_body_is_never_stored(provider, monkeypatch):
    """Only structured stubs reach the classifier, never the full text."""
    capture_get(monkeypatch)

    article = provider.search_company_news("Aquafil S.p.A.")[0]

    assert article.content is None
    assert "Testo completo" not in (article.summary or "")


@pytest.mark.parametrize("envelope", ["results", "data", "articles"])
def test_alternative_envelope_keys_are_accepted(provider, monkeypatch, envelope):
    payload = {envelope: RESPONSE["results"]}
    capture_get(monkeypatch, FakeResponse(payload=payload))

    assert len(provider.search_company_news("Aquafil S.p.A.")) == 1


def test_an_unrecognised_response_is_reported_not_silently_empty(provider, monkeypatch):
    capture_get(monkeypatch, FakeResponse(payload={"message": "qualcosa"}))

    assert provider.search_company_news("Aquafil S.p.A.") == []
    assert provider.last_call_error == "formato risposta non riconosciuto"


def test_dates_in_various_formats(provider):
    assert provider._parse_date("2026-08-20T10:30:00Z").day == 20
    assert provider._parse_date("2026-08-20T10:30:00+02:00").tzinfo is None
    assert provider._parse_date("2026-08-20").day == 20
    assert provider._parse_date(None) is not None       # falls back to now
    assert provider._parse_date("non-una-data") is not None


# --- spending control -------------------------------------------------

def test_no_key_means_no_request(monkeypatch):
    provider = APITubeProvider(api_key=None)
    calls = capture_get(monkeypatch)

    assert provider.search_company_news("Aquafil S.p.A.") == []
    assert calls == []


def test_the_run_budget_is_enforced(provider, monkeypatch):
    """A trial key must survive a run over the whole company list."""
    provider.budget = 3
    calls = capture_get(monkeypatch)

    for i in range(10):
        provider.search_company_news(f"Azienda {i}")

    assert len(calls) == 3
    assert provider.last_call_error == "budget del run esaurito"


def test_an_invalid_key_stops_further_requests(provider, monkeypatch):
    calls = capture_get(monkeypatch, FakeResponse(status_code=401))

    provider.search_company_news("Prima")
    provider.search_company_news("Seconda")
    provider.search_company_news("Terza")

    assert len(calls) == 1, "no point asking again with a rejected key"
    assert "APITUBE_API_KEY" in provider.disabled_reason


def test_an_exhausted_quota_stops_further_requests(provider, monkeypatch):
    calls = capture_get(monkeypatch, FakeResponse(status_code=429))

    provider.search_company_news("Prima")
    provider.search_company_news("Seconda")

    assert len(calls) == 1
    assert provider.disabled_reason == "quota APITube esaurita"


def test_a_network_error_does_not_disable_the_provider(provider, monkeypatch):
    def _raise(url, params=None, timeout=None, headers=None):
        raise apitube_module.requests.ConnectionError("rete non raggiungibile")

    monkeypatch.setattr(apitube_module.requests, "get", _raise)

    assert provider.search_company_news("Aquafil S.p.A.") == []
    assert provider.disabled_reason is None  # a blip must not stop the run
    assert provider.last_call_error == "request exception"


# --- integration with the searcher ------------------------------------

def test_it_is_only_asked_when_the_free_sources_found_nothing():
    """This is what makes a small quota last."""
    from app.services.news_searcher import NewsSearcher
    from app.providers.base import NewsArticle
    from app.models import Company

    class FreeProvider:
        def __init__(self, articles):
            self.articles = articles

        def search_company_news(self, name, keywords=None):
            return self.articles

    found = NewsArticle(
        title="Trovata dai gratuiti", url="https://x.it/1",
        source_name="Google News", source_type="google_news_rss",
        published_date=None,
    )

    searcher = NewsSearcher()
    paid = APITubeProvider(api_key="chiave-di-prova")

    # Free source found something -> the paid one is skipped entirely.
    _, summary = searcher.search_company_news(
        Company(company_name="Aquafil S.p.A."), [FreeProvider([found]), paid]
    )
    assert paid.requests_made == 0
    assert any("non necessario" in entry for entry in summary)


def test_it_is_asked_when_the_free_sources_came_up_empty(monkeypatch):
    from app.services.news_searcher import NewsSearcher
    from app.models import Company

    class EmptyProvider:
        def search_company_news(self, name, keywords=None):
            return []

    capture_get(monkeypatch)
    searcher = NewsSearcher()
    paid = APITubeProvider(api_key="chiave-di-prova")

    items, _ = searcher.search_company_news(
        Company(company_name="Azienda Sconosciuta"), [EmptyProvider(), paid]
    )

    assert paid.requests_made == 1
    assert len(items) == 1
