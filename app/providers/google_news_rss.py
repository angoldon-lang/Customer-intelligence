"""Google News RSS provider - free, no API key required.

Uses the public RSS search feed (not the HTML search page, which is
protected by a cookie-consent wall and blocked scraping in earlier
attempts). This endpoint returns plain XML and tends to have much better
coverage of small/local businesses than GDELT or GNews.io, which mostly
index larger outlets.
"""

from typing import List, Dict, Any
from datetime import datetime
import time
import requests
import feedparser
from app.providers.base import NewsSourceProvider, NewsArticle
from app.config import settings

GOOGLE_NEWS_RSS_ENDPOINT = "https://news.google.com/rss/search"

MIN_REQUEST_INTERVAL = 1.0  # seconds between requests
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"


class GoogleNewsRSSProvider(NewsSourceProvider):
    """Search Google News via its public RSS search feed."""

    def __init__(self, timeout: int = None, days: int = 30):
        self.timeout = timeout or settings.NEWS_SEARCH_TIMEOUT
        self.days = days
        self._last_request_at = 0.0
        self.blocked = False

    def _throttle(self):
        elapsed = time.monotonic() - self._last_request_at
        if elapsed < MIN_REQUEST_INTERVAL:
            time.sleep(MIN_REQUEST_INTERVAL - elapsed)
        self._last_request_at = time.monotonic()

    def search_company_news(
        self, company_name: str, keywords: List[str] = None
    ) -> List[NewsArticle]:
        if self.blocked:
            return []

        query = f'"{company_name}" when:{self.days}d'
        if keywords:
            query += " " + " ".join(keywords)

        ceid = f"{settings.NEWS_COUNTRY}:{settings.NEWS_LANGUAGE}"
        params = {
            "q": query,
            "hl": settings.NEWS_LANGUAGE,
            "gl": settings.NEWS_COUNTRY,
            "ceid": ceid,
        }

        self._throttle()
        try:
            response = requests.get(
                GOOGLE_NEWS_RSS_ENDPOINT,
                params=params,
                timeout=self.timeout,
                headers={"User-Agent": USER_AGENT},
            )
            if response.status_code in (403, 429):
                print(f"[GoogleNewsRSS] Blocked ({response.status_code}), disabling for the rest of this run")
                self.blocked = True
                return []
            response.raise_for_status()
        except requests.RequestException as e:
            print(f"[GoogleNewsRSS] Error searching '{company_name}': {e}")
            return []

        parsed = feedparser.parse(response.content)
        results = []

        for entry in parsed.entries:
            title = entry.get("title")
            url = entry.get("link")
            if not title or not url:
                continue

            source_name = "Google News"
            source_obj = entry.get("source")
            if isinstance(source_obj, dict) and source_obj.get("title"):
                source_name = source_obj["title"]
            elif " - " in title:
                # Google News often suffixes the title with " - Source Name"
                title, _, maybe_source = title.rpartition(" - ")
                source_name = maybe_source or source_name

            results.append(NewsArticle(
                title=title,
                url=url,
                source_name=source_name,
                source_type="google_news_rss",
                published_date=self._parse_entry_date(entry),
                summary=entry.get("summary"),
                access_status="available",
                license_scope="summary_allowed",
            ))

        return results

    @staticmethod
    def _parse_entry_date(entry) -> datetime:
        parsed_time = entry.get("published_parsed")
        if parsed_time:
            return datetime(*parsed_time[:6])
        return datetime.utcnow()

    def fetch_article_metadata(self, url: str) -> Dict[str, Any]:
        return {"title": None, "published_date": None, "summary": None, "source": "google_news_rss"}

    def fetch_article_content(self, url: str) -> str:
        return None

    def check_access(self) -> bool:
        try:
            response = requests.get(
                GOOGLE_NEWS_RSS_ENDPOINT,
                params={"q": "test", "hl": "it", "gl": "IT", "ceid": "IT:it"},
                timeout=self.timeout,
                headers={"User-Agent": USER_AGENT},
            )
            return response.status_code == 200
        except requests.RequestException:
            return False

    def is_enabled(self) -> bool:
        return settings.GOOGLE_NEWS_RSS_ENABLED
