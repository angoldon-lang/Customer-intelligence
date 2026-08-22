"""News source providers."""

from app.providers.base import NewsSourceProvider
from app.providers.mock import MockNewsProvider
from app.providers.test import TestNewsProvider
from app.providers.gdelt import GDELTProvider
from app.providers.gnews import GNewsProvider
from app.providers.rss import RSSProvider
from app.providers.google_news_rss import GoogleNewsRSSProvider

__all__ = [
    "NewsSourceProvider",
    "MockNewsProvider",
    "TestNewsProvider",
    "GDELTProvider",
    "GNewsProvider",
    "RSSProvider",
    "GoogleNewsRSSProvider",
]
