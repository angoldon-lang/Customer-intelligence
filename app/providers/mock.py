"""Mock news provider for testing and MVP."""

from typing import List, Dict, Any
from datetime import datetime, timedelta
from app.providers.base import NewsSourceProvider, NewsArticle


class MockNewsProvider(NewsSourceProvider):
    """Mock news provider with predefined news items for testing."""

    def __init__(self):
        self.mock_news = {
            "2NIGHT": [
                {
                    "title": "2NIGHT announces new partnership with major hotel chain",
                    "url": "https://example.com/news/2night-partnership",
                    "source_name": "Business News Daily",
                    "published_date": datetime.utcnow() - timedelta(days=2),
                    "summary": "2NIGHT has announced a strategic partnership to expand event organization services.",
                },
                {
                    "title": "2NIGHT invests in AI-powered event management platform",
                    "url": "https://example.com/news/2night-ai",
                    "source_name": "Tech Crunch",
                    "published_date": datetime.utcnow() - timedelta(days=5),
                    "summary": "The company has invested in new AI technology to improve event organization.",
                },
            ],
            "3AI DATA": [
                {
                    "title": "3AI DATA completes Series B funding round",
                    "url": "https://example.com/news/3aidata-funding",
                    "source_name": "Crunchbase",
                    "published_date": datetime.utcnow() - timedelta(days=1),
                    "summary": "3AI DATA has closed a Series B funding round to expand its data analytics platform.",
                },
            ],
            "PEAC ITALY": [
                {
                    "title": "PEAC Solutions expands European operations",
                    "url": "https://example.com/news/peac-expansion",
                    "source_name": "European Business Monthly",
                    "published_date": datetime.utcnow() - timedelta(days=3),
                    "summary": "PEAC Solutions opens new offices across Europe to support growing client base.",
                },
            ],
        }

    def search_company_news(
        self, company_name: str, keywords: List[str] = None
    ) -> List[NewsArticle]:
        """Search for news in mock database."""
        results = []

        # Search by company name
        for key in self.mock_news:
            if company_name.upper() in key.upper() or key.upper() in company_name.upper():
                for news in self.mock_news[key]:
                    article = NewsArticle(
                        title=news["title"],
                        url=news["url"],
                        source_name=news["source_name"],
                        source_type="mock",
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
        # Mock: return same data for all URLs
        return {
            "title": "Article Title",
            "published_date": datetime.utcnow(),
            "summary": "Article summary",
            "source": "mock",
        }

    def fetch_article_content(self, url: str) -> str:
        """Fetch article content."""
        # Mock: return dummy content
        return """
        This is a mock article content.
        It demonstrates the structure of a news article for testing purposes.
        In a real implementation, this would fetch from actual news sources.
        """

    def check_access(self) -> bool:
        """Check if provider is accessible."""
        return True
