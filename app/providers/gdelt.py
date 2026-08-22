"""GDELT DOC 2.0 API provider - free, no API key required."""

from typing import List, Dict, Any
from datetime import datetime
import requests
from app.providers.base import NewsSourceProvider, NewsArticle
from app.config import settings

GDELT_ENDPOINT = "https://api.gdeltproject.org/api/v2/doc/doc"


class GDELTProvider(NewsSourceProvider):
    """Broad news coverage via GDELT's free DOC 2.0 search API.

    GDELT only returns title/url/domain/date, no snippet - it is meant as
    a wide, cheap first pass; GNews (or another paid provider) is used on
    top of it to fill in descriptions for validation.
    """

    def __init__(self, timeout: int = None):
        self.timeout = timeout or settings.NEWS_SEARCH_TIMEOUT

    def search_company_news(
        self, company_name: str, keywords: List[str] = None
    ) -> List[NewsArticle]:
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
            response = requests.get(GDELT_ENDPOINT, params=params, timeout=self.timeout)
            response.raise_for_status()
            data = response.json()
        except (requests.RequestException, ValueError) as e:
            print(f"[GDELT] Error searching '{company_name}': {e}")
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
