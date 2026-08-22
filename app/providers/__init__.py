"""News source providers."""

from app.providers.base import NewsSourceProvider
from app.providers.mock import MockNewsProvider

__all__ = ["NewsSourceProvider", "MockNewsProvider"]
