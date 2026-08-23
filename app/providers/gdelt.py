"""GDELT DOC 2.0 API provider - free, no API key required."""

from typing import List, Dict, Any
from datetime import datetime
import time
import requests
from app.providers.base import NewsSourceProvider, NewsArticle
from app.config import settings

GDELT_ENDPOINT = "https://api.gdeltproject.org/api/v2/doc/doc"

# GDELT's free DOC API has no published quota but rate-limits bursts hard
# (429s start almost immediately without pacing). Space requests out and
# trip a circuit breaker on repeated 429s instead of hammering it once per
# company across a run of hundreds/thousands of companies.
MIN_REQUEST_INTERVAL = 5.0  # seconds between requests
BACKOFF_SECONDS = 30  # wait once on a 429 before giving the retry a chance


class GDELTProvider(NewsSourceProvider):
    """Broad news coverage via GDELT's free DOC 2.0 search API.

    GDELT only returns title/url/domain/date, no snippet - it is meant as
    a wide, cheap first pass; GNews (or another paid provider) is used on
    top of it to fill in descriptions for validation.
    """

    def __init__(self, timeout: int = None):
        self.timeout = timeout or settings.NEWS_SEARCH_TIMEOUT
        self._last_request_at = 0.0
        self.rate_limited = False
        self.last_call_error = None

    def _throttle(self):
        elapsed = time.monotonic() - self._last_request_at
        if elapsed < MIN_REQUEST_INTERVAL:
            time.sleep(MIN_REQUEST_INTERVAL - elapsed)
        self._last_request_at = time.monotonic()

    def _get(self, params: dict) -> requests.Response:
        self._throttle()
        response = requests.get(GDELT_ENDPOINT, params=params, timeout=self.timeout)
        if response.status_code == 429:
            print(f"[GDELT] Rate limited, backing off {BACKOFF_SECONDS}s and retrying once")
            time.sleep(BACKOFF_SECONDS)
            self._throttle()
            response = requests.get(GDELT_ENDPOINT, params=params, timeout=self.timeout)
        return response

    def search_company_news(
        self, company_name: str, keywords: List[str] = None
    ) -> List[NewsArticle]:
        self.last_call_error = None

        if self.rate_limited:
            print(f"[GDELT] Skipping '{company_name}': disabled earlier this run")
            self.last_call_error = "disabled earlier this run"
            return []

        query = f'"{company_name}"'
        if keywords:
            query += " " + " ".join(keywords)

        params = {
            "query": query,
            "mode": "artlist",
            "maxrecords": settings.NEWS_MAX_RESULTS_PER_COMPANY,
            "format": "json",
            "sort": "datedesc",
            "timespan": "3months",
        }

        try:
            response = self._get(params)
            if response.status_code == 429:
                print("[GDELT] Still rate limited after backoff, disabling GDELT for the rest of this run")
                self.rate_limited = True
                self.last_call_error = "HTTP 429"
                return []
            response.raise_for_status()
            data = response.json()
        except (requests.RequestException, ValueError) as e:
            print(f"[GDELT] Error searching '{company_name}': {e}")
            self.last_call_error = "request exception"
            return []

        articles = data.get("articles", []) if isinstance(data, dict) else []
        results = []

        for item in articles:
            url = item.get("url")
            title = item.get("title")
            if not url or not title:
                continue

            results.append(NewsArticle(
                title=title,
                url=url,
                source_name=item.get("domain", "GDELT"),
                source_type="gdelt",
                published_date=self._parse_seendate(item.get("seendate")),
                summary=None,
                access_status="available",
                license_scope="metadata_only",
            ))

        return results

    @staticmethod
    def _parse_seendate(seendate: str) -> datetime:
        if not seendate:
            return datetime.utcnow()
        try:
            return datetime.strptime(seendate, "%Y%m%dT%H%M%SZ")
        except ValueError:
            return datetime.utcnow()

    def fetch_article_metadata(self, url: str) -> Dict[str, Any]:
        return {"title": None, "published_date": None, "summary": None, "source": "gdelt"}

    def fetch_article_content(self, url: str) -> str:
        return None

    def check_access(self) -> bool:
        try:
            response = requests.get(
                GDELT_ENDPOINT,
                params={"query": "test", "mode": "artlist", "maxrecords": 1, "format": "json"},
                timeout=self.timeout,
            )
            return response.status_code == 200
        except requests.RequestException:
            return False

    def is_enabled(self) -> bool:
        return settings.GDELT_ENABLED
