"""Tests for news providers."""

import pytest
from app.providers.mock import MockNewsProvider


@pytest.fixture
def provider():
    return MockNewsProvider()


def test_mock_provider_search(provider):
    """Test mock provider search."""
    results = provider.search_company_news("2NIGHT")

    assert len(results) > 0
    assert results[0].source_type == "mock"
    assert results[0].access_status == "available"


def test_mock_provider_search_exact_match(provider):
    """Test exact company name match."""
    results = provider.search_company_news("2NIGHT")

    assert any("partnership" in r.title.lower() for r in results)


def test_mock_provider_search_no_results(provider):
    """Test search with no results."""
    results = provider.search_company_news("NonExistentCompany")

    assert len(results) == 0


def test_mock_provider_search_with_keywords(provider):
    """Test search with keywords."""
    results = provider.search_company_news("2NIGHT", keywords=["partnership"])

    assert all("partnership" in r.title.lower() or "partnership" in (r.summary or "").lower() for r in results)


def test_mock_provider_fetch_metadata(provider):
    """Test metadata fetching."""
    metadata = provider.fetch_article_metadata("https://example.com")

    assert "title" in metadata
    assert "published_date" in metadata
    assert "summary" in metadata


def test_mock_provider_fetch_content(provider):
    """Test content fetching."""
    content = provider.fetch_article_content("https://example.com")

    assert isinstance(content, str)
    assert len(content) > 0


def test_mock_provider_check_access(provider):
    """Test access check."""
    assert provider.check_access() is True


def test_mock_provider_is_enabled(provider):
    """Test provider enabled status."""
    assert provider.is_enabled() is True
