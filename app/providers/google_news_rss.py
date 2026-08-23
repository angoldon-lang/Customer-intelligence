"""Google News RSS provider - free, no API key required.

Uses the public RSS search feed (not the HTML search page, which is
protected by a cookie-consent wall and blocked scraping in earlier
attempts). This endpoint returns plain XML and tends to have much better
coverage of small/local businesses than GDELT or GNews.io, which mostly
index larger outlets.
"""

from typing import List, Dict, Any
from datetime import datetime
from urllib.parse import quote_plus
import base64
import re
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
        self._consecutive_failures = 0
        self.last_call_error = None

    def _throttle(self):
        elapsed = time.monotonic() - self._last_request_at
        if elapsed < MIN_REQUEST_INTERVAL:
            time.sleep(MIN_REQUEST_INTERVAL - elapsed)
        self._last_request_at = time.monotonic()

    def _record_failure(self, reason: str):
        self._consecutive_failures += 1
        if self._consecutive_failures >= 2:
            print(f"[GoogleNewsRSS] {reason} twice in a row, disabling for the rest of this run")
            self.blocked = True
        else:
            print(f"[GoogleNewsRSS] {reason} (attempt {self._consecutive_failures}/2 before disabling)")

    def search_company_news(
        self, company_name: str, keywords: List[str] = None
    ) -> List[NewsArticle]:
        # Reset per-call: distinguishes "0 results, request genuinely
        # succeeded" from "0 results because this specific call failed"
        # (which the run-level `blocked` flag alone can't show before the
        # circuit breaker actually trips after 2 failures).
        self.last_call_error = None

        if self.blocked:
            print(f"[GoogleNewsRSS] Skipping '{company_name}': disabled earlier this run")
            self.last_call_error = "disabled earlier this run"
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
                self._record_failure(f"HTTP {response.status_code}")
                self.last_call_error = f"HTTP {response.status_code}"
                return []
            response.raise_for_status()
        except requests.RequestException as e:
            print(f"[GoogleNewsRSS] Error searching '{company_name}': {e}")
            self._record_failure("request exception")
            self.last_call_error = "request exception"
            return []

        parsed = feedparser.parse(response.content)

        if parsed.bozo and not parsed.entries:
            # A 200 OK with a malformed/non-RSS body (e.g. a consent or
            # CAPTCHA page) - feedparser silently returns 0 entries with no
            # exception, so without this check a block looks identical to
            # "genuinely no news found".
            print(f"[GoogleNewsRSS] Response for '{company_name}' wasn't valid RSS ({parsed.get('bozo_exception')}), likely blocked")
            self._record_failure("malformed RSS response")
            self.last_call_error = "malformed RSS response"
            return []

        self._consecutive_failures = 0
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
                url=self.normalize_article_url(url, title),
                source_name=source_name,
                source_type="google_news_rss",
                published_date=self._parse_entry_date(entry),
                summary=entry.get("summary"),
                access_status="available",
                license_scope="summary_allowed",
            ))

        return results

    @staticmethod
    def normalize_article_url(url: str, title: str = None) -> str:
        """
        Turn an RSS item link into one a browser can actually open.

        Google News RSS items link to news.google.com/rss/articles/<id>.
        A browser opening that path gets the RSS XML back, or a redirect to
        /rss/unsupported - never the article. Two cases:

        * Older ids embed the publisher URL in a base64 protobuf: decode it
          and return the real article link (best outcome).
        * Newer ids (AU_yqL...) are opaque and can only be resolved by
          Google itself, so fall back to a news search on the headline,
          which reliably lands on the article.
        """
        if not url or "news.google.com" not in url:
            return url

        match = re.search(r"/articles/([A-Za-z0-9_\-]+)", url)
        if match:
            decoded = GoogleNewsRSSProvider._decode_article_id(match.group(1))
            if decoded:
                return decoded

        if title:
            # Strip the " - Publisher" suffix Google appends to headlines.
            query = re.sub(r"\s+-\s+[^-]+$", "", title).strip() or title
            return "https://www.google.com/search?q=" + quote_plus(query)

        return url

    @staticmethod
    def _decode_article_id(article_id: str) -> str:
        """Extract the publisher URL from a Google News article id, if present."""
        try:
            padded = article_id + "=" * (-len(article_id) % 4)
            raw = base64.urlsafe_b64decode(padded)
        except Exception:
            return None

        # The payload is a small protobuf. Read length-delimited fields
        # (tag 0x22 = field 4, wire type 2) properly rather than regexing
        # for "http", which can't tell where the string ends and would drag
        # in the next field's tag byte.
        i = 0
        while i < len(raw):
            if raw[i] != 0x22:
                i += 1
                continue
            i += 1
            length, shift = 0, 0
            while i < len(raw):
                byte = raw[i]
                i += 1
                length |= (byte & 0x7F) << shift
                if not byte & 0x80:
                    break
                shift += 7
            value = raw[i:i + length]
            i += length
            if value.startswith((b"http://", b"https://")):
                candidate = value.decode("utf-8", errors="ignore")
                if "news.google.com" not in candidate:
                    return candidate
        return None

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
