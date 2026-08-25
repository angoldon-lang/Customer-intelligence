"""Tests for choosing which news sources run, and in what order."""

import pytest

from app.config import settings
from app.services.news_searcher import NewsSearcher


@pytest.fixture(autouse=True)
def restore_settings():
    saved = {
        key: getattr(settings, key)
        for key in [
            "PROVIDER_ORDER", "GOOGLE_NEWS_RSS_ENABLED", "GDELT_ENABLED",
            "RSS_ENABLED", "GNEWS_API_KEY", "APITUBE_API_KEY",
        ]
    }
    yield
    for key, value in saved.items():
        setattr(settings, key, value)


def keys_of(providers):
    labels = {
        "GoogleNewsRSSProvider": "google_news_rss",
        "GDELTProvider": "gdelt",
        "GNewsProvider": "gnews",
        "RSSProvider": "rss",
        "APITubeProvider": "apitube",
        "TestNewsProvider": "test",
    }
    return [labels.get(p.__class__.__name__, p.__class__.__name__) for p in providers]


def enable_all():
    settings.GOOGLE_NEWS_RSS_ENABLED = True
    settings.GDELT_ENABLED = True
    settings.RSS_ENABLED = False   # needs a db session; covered separately
    settings.GNEWS_API_KEY = "chiave-gnews"
    settings.APITUBE_API_KEY = "chiave-apitube"


def test_sources_are_queried_in_the_configured_order():
    enable_all()
    settings.PROVIDER_ORDER = "gdelt,apitube,google_news_rss,gnews"

    providers = NewsSearcher()._build_providers(db=None)

    assert keys_of(providers) == ["gdelt", "apitube", "google_news_rss", "gnews"]


def test_reversing_the_order_reverses_the_search():
    enable_all()
    # Every enabled source is listed: an unlisted one always goes last, so
    # it would sit at the end of both lists and break the symmetry.
    settings.PROVIDER_ORDER = "gnews,apitube,google_news_rss,gdelt"
    first = keys_of(NewsSearcher()._build_providers(db=None))

    settings.PROVIDER_ORDER = "gdelt,google_news_rss,apitube,gnews"
    second = keys_of(NewsSearcher()._build_providers(db=None))

    assert first == list(reversed(second))


def test_a_source_missing_from_the_order_still_runs_last():
    """Otherwise adding a provider would silently disable it."""
    enable_all()
    settings.PROVIDER_ORDER = "gdelt"

    order = NewsSearcher.provider_order()

    assert order[0] == "gdelt"
    assert set(order) == set(NewsSearcher.PROVIDER_KEYS)


def test_unknown_names_in_the_order_are_ignored():
    enable_all()
    settings.PROVIDER_ORDER = "non_esiste,gdelt,nemmeno_questo"

    assert NewsSearcher.provider_order()[0] == "gdelt"


def test_a_disabled_source_is_not_queried_even_if_listed_first():
    enable_all()
    settings.GDELT_ENABLED = False
    settings.PROVIDER_ORDER = "gdelt,google_news_rss"

    assert "gdelt" not in keys_of(NewsSearcher()._build_providers(db=None))


def test_a_source_without_its_key_is_not_queried():
    enable_all()
    settings.GNEWS_API_KEY = None
    settings.APITUBE_API_KEY = None

    keys = keys_of(NewsSearcher()._build_providers(db=None))

    assert "gnews" not in keys
    assert "apitube" not in keys


def test_apitube_keeps_its_fallback_behaviour_wherever_it_sits():
    """Moving it first must not turn it into a full-quota source."""
    enable_all()
    settings.PROVIDER_ORDER = "apitube,google_news_rss"
    settings.APITUBE_FALLBACK_ONLY = True

    providers = NewsSearcher()._build_providers(db=None)
    apitube = next(p for p in providers if p.__class__.__name__ == "APITubeProvider")

    assert apitube.fallback_only is True


def test_with_everything_off_the_pipeline_still_runs():
    settings.GOOGLE_NEWS_RSS_ENABLED = False
    settings.GDELT_ENABLED = False
    settings.RSS_ENABLED = False
    settings.GNEWS_API_KEY = None
    settings.APITUBE_API_KEY = None

    assert keys_of(NewsSearcher()._build_providers(db=None)) == ["test"]
