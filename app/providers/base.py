"""Base class for news source providers."""

from abc import ABC, abstractmethod
from typing import List, Dict, Any
from dataclasses import dataclass
from datetime import datetime


@dataclass
class NewsArticle:
    """Article metadata and content."""

    title: str
    url: str
    source_name: str
    source_type: str
    published_date: datetime
    summary: str = None
    content: str = None
    access_status: str = "available"
    license_scope: str = "metadata_only"


class NewsSourceProvider(ABC):
    """Abstract base class for news source providers."""

    @abstractmethod
    def search_company_news(self, company_name: str, keywords: List[str] = None) -> List[NewsArticle]:
        """
        Search for news about a company.

        Args:
            company_name: Name of company to search
            keywords: Optional keywords to refine search

        Returns:
            List of NewsArticle objects
        """
        pass

    @abstractmethod
    def fetch_article_metadata(self, url: str) -> Dict[str, Any]:
        """
        Fetch metadata about an article.

        Returns:
            Dict with title, published_date, summary, etc.
        """
        pass

    @abstractmethod
    def fetch_article_content(self, url: str) -> str:
        """
        Fetch full article content.

        Returns:
            Article text or None if not accessible
        """
        pass

    @abstractmethod
    def check_access(self) -> bool:
        """
        Check if provider is accessible.

        Returns:
            True if provider is working
        """
        pass

    def is_enabled(self) -> bool:
        """Check if provider is enabled."""
        return True
