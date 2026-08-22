"""RSS provider for official company press-release / IR feeds.

Feeds are configured in the news_sources table (source_type='rss',
enabled=True) rather than hardcoded, so official sources can be added per
company/sector without a code change. See README "Fonti ufficiali (RSS)".
"""

from typing import List, Dict, Any, Optional
from datetime import datetime
import time
import feedparser
from sqlalchemy.orm import Session
from app.providers.base import NewsSourceProvider, NewsArticle
from app.models import NewsSource


class RSSProvider(NewsSourceProvider):
    """Matches company names against entries from configured RSS feeds.

    Feeds are fetched once per monitoring run via refresh(), then every
    company lookup filters the cached entries - this avoids re-downloading
    every feed once per company.
    """

    def __init__(self, db: Session):
        self.db = db
        self._entries: List[Dict[str, Any]] = []
        self._refreshed = False

    def refresh(self):
        """Fetch and cache entries from all enabled RSS sources."""
        self._entries = []
        sources = (
            self.db.query(NewsSource)
            .filter_by(source_type="rss", enabled=True)
            .all()
        )

        for source in sources:
            if not source.base_url:
                continue
            try:
                parsed = feedparser.parse(source.base_url)
            except Exception as e:
                print(f"[RSS] Error parsing feed '{source.source_name}': {e}")
                continue

            for entry in parsed.entries:
                title = entry.get("title")
                link = entry.get("link")
                if not title or not link:
                    continue

                self._entries.append({
                    "title": title,
                    "url": link,
                    "summary": entry.get("summary", ""),
                    "published_date": self._parse_entry_date(entry),
                    "source_name": source.source_name,
                    "license_scope": source.license_scope or "summary_allowed",
                })

        self._refreshed = True

    @staticmethod
    def _parse_entry_date(entry) -> datetime:
        parsed_time = entry.get("published_parsed") or entry.get("updated_parsed")
        if parsed_time:
            return datetime.fromtimestamp(time.mktime(parsed_time))
        return datetime.utcnow()

    def search_company_news(
        self, company_name: str, keywords: List[str] = None
    ) -> List[NewsArticle]:
        if not self._refreshed:
            self.refresh()

        name_lower = company_name.lower()
        results = []

        for entry in self._entries:
            haystack = f"{entry['title']} {entry['summary']}".lower()
            if name_lower not in haystack:
                continue

            results.append(NewsArticle(
                title=entry["title"],
                url=entry["url"],
                source_name=entry["source_name"],
                source_type="official",
                published_date=entry["published_date"],
                summary=entry["summary"] or None,
                access_status="available",
                license_scope=entry["license_scope"],
            ))

        return results

    def fetch_article_metadata(self, url: str) -> Dict[str, Any]:
        return {"title": None, "published_date": None, "summary": None, "source": "rss"}

    def fetch_article_content(self, url: str) -> str:
        return None

    def check_access(self) -> bool:
        return self.db.query(NewsSource).filter_by(source_type="rss", enabled=True).count() > 0

    def is_enabled(self) -> bool:
        return True
