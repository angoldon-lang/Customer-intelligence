"""GNews.io provider - used to validate/complement GDELT coverage with snippets."""

from typing import List, Dict, Any
from datetime import datetime
import requests
from app.providers.base import NewsSourceProvider, NewsArticle
from app.config import settings

GNEWS_ENDPOINT = "https://gnews.io/api/v4/search"


class GNewsProvider(NewsSourceProvider):
    """News search via GNews.io (requires GNEWS_API_KEY)."""

    def __init__(self, api_key: str = None, timeout: int = None):
        self.api_key = api_key or settings.GNEWS_API_KEY
        self.timeout = timeout or settings.NEWS_SEARCH_TIMEOUT
        self.quota_exceeded = False
        self.last_call_error = None

    def search_company_news(
        self, company_name: str, keywords: List[str] = None
    ) -> List[NewsArticle]:
        self.last_call_error = None

        if not self.api_key or self.quota_exceeded:
            self.last_call_error = "not configured" if not self.api_key else "quota exceeded earlier this run"
            return []

        query = f'"{company_name}"'
        if keywords:
            query += " " + " ".join(keywords)

        params = {
            "q": query,
            "lang": settings.NEWS_LANGUAGE,
            "country": settings.NEWS_COUNTRY,
            "max": min(settings.NEWS_MAX_RESULTS_PER_COMPANY, 10),
            "apikey": self.api_key,
        }

        try:
            response = requests.get(GNEWS_ENDPOINT, params=params, timeout=self.timeout)
            if response.status_code in (401, 403, 429):
                self.quota_exceeded = True
                print(f"[GNews] Quota/auth error ({response.status_code}), disabling for this run")
                self.last_call_error = f"HTTP {response.status_code}"
                return []
            response.raise_for_status()
            data = response.json()
        except (requests.RequestException, ValueError) as e:
            print(f"[GNews] Error searching '{company_name}': {e}")
            self.last_call_error = "request exception"
            return []

        articles = data.get("articles", []) if isinstance(data, dict) else []
        results = []

        for item in articles:
            url = item.get("url")
            title = item.get("title")
            if not url or not title:
                continue

            source = item.get("source") or {}
            results.append(NewsArticle(
                title=title,
                url=url,
                source_name=source.get("name", "GNews"),
                source_type="gnews",
                published_date=self._parse_date(item.get("publishedAt")),
                summary=item.get("description"),
                access_status="available",
                license_scope="summary_allowed",
            ))

        return results

    @staticmethod
    def _parse_date(value: str) -> datetime:
        if not value:
            return datetime.utcnow()
        try:
            return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
        except ValueError:
            return datetime.utcnow()

    def fetch_article_metadata(self, url: str) -> Dict[str, Any]:
        return {"title": None, "published_date": None, "summary": None, "source": "gnews"}

    def fetch_article_content(self, url: str) -> str:
        return None

    def check_access(self) -> bool:
        if not self.api_key:
            return False
        try:
            response = requests.get(
                GNEWS_ENDPOINT,
                params={"q": "test", "max": 1, "apikey": self.api_key},
                timeout=self.timeout,
            )
            return response.status_code == 200
        except requests.RequestException:
            return False

    def is_enabled(self) -> bool:
        return bool(self.api_key)
