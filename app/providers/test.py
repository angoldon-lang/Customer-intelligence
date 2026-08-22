"""Test news provider with mock data for development."""

from typing import List, Dict, Any
from datetime import datetime, timedelta
from app.providers.base import NewsSourceProvider, NewsArticle


class TestNewsProvider(NewsSourceProvider):
    """Test provider that returns mock news for testing."""

    def __init__(self):
        self.test_news = {
            "Acme Corp": [
                {
                    "title": "Acme Corp announces quarterly earnings of $2.5M",
                    "url": "https://example.com/acme-earnings",
                    "source_name": "Business Times",
                    "published_date": datetime.utcnow() - timedelta(days=1),
                    "summary": "Acme Corporation reported strong Q3 performance with 15% revenue growth.",
                },
                {
                    "title": "Acme Corp expands operations to Europe",
                    "url": "https://example.com/acme-expansion",
                    "source_name": "Tech News Daily",
                    "published_date": datetime.utcnow() - timedelta(days=3),
                    "summary": "The company opens new office in London to serve European market.",
                },
            ],
            "Globex Inc": [
                {
                    "title": "Globex Inc partners with major retailer",
                    "url": "https://example.com/globex-partnership",
                    "source_name": "Market Watch",
                    "published_date": datetime.utcnow() - timedelta(days=2),
                    "summary": "Strategic partnership announced to expand distribution channels.",
                },
                {
                    "title": "Globex Inc receives ISO certification",
                    "url": "https://example.com/globex-iso",
                    "source_name": "Quality News",
                    "published_date": datetime.utcnow() - timedelta(days=5),
                    "summary": "Company achieves ISO 9001 quality management certification.",
                },
            ],
            "Initech Ltd": [
                {
                    "title": "Initech Ltd launches new product line",
                    "url": "https://example.com/initech-product",
                    "source_name": "Innovation Weekly",
                    "published_date": datetime.utcnow() - timedelta(days=1),
                    "summary": "Revolutionary new product targets enterprise market.",
                },
            ],
        }

    def search_company_news(
        self, company_name: str, keywords: List[str] = None
    ) -> List[NewsArticle]:
        """Search for news in test database."""
        results = []

        # Search by company name
        for key in self.test_news:
            if company_name.upper() in key.upper() or key.upper() in company_name.upper():
                for news in self.test_news[key]:
                    article = NewsArticle(
                        title=news["title"],
                        url=news["url"],
                        source_name=news["source_name"],
                        source_type="test",
                        published_date=news["published_date"],
                        summary=news["summary"],
                        access_status="available",
                        license_scope="summary_allowed",
                    )
                    results.append(article)

        # Filter by keywords if provided
        if keywords:
            results = [
                a for a in results
                if any(kw.lower() in a.title.lower() or kw.lower() in (a.summary or "").lower()
                       for kw in keywords)
            ]

        return results

    def fetch_article_metadata(self, url: str) -> Dict[str, Any]:
        """Fetch metadata for article."""
        return {
            "title": "Article Title",
            "published_date": datetime.utcnow(),
            "summary": "Article summary",
            "source": "test",
        }

    def fetch_article_content(self, url: str) -> str:
        """Fetch article content."""
        return "This is test news content for development and testing purposes."

    def check_access(self) -> bool:
        """Check if provider is accessible."""
        return True
