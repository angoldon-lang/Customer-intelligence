"""APITube provider - paid news API with structured, enriched articles.

Unlike the free sources, APITube returns a real description/body per
article, so it is the best candidate for the press-review ("rassegna
stampa") work later on.

It is metered, so this provider is deliberately frugal:

* it runs **only for companies the free sources found nothing for**
  (`fallback_only`), which is exactly where a paid lookup earns its cost;
* it stops after a hard per-run request budget, so a trial key can never
  be drained by a single run over the whole company list.
"""

from typing import List, Dict, Any
from datetime import datetime, timedelta
import requests

from app.providers.base import NewsSourceProvider, NewsArticle
from app.config import settings

APITUBE_ENDPOINT = "https://api.apitube.io/v1/news/everything"


class APITubeProvider(NewsSourceProvider):
    """News search via APITube (requires APITUBE_API_KEY)."""

    # Only consulted when the free providers came back empty for a company.
    fallback_only = True

    def __init__(self, api_key: str = None, timeout: int = None, days: int = None):
        self.api_key = api_key or settings.APITUBE_API_KEY
        self.timeout = timeout or settings.NEWS_SEARCH_TIMEOUT
        self.days = days or settings.NEWS_SEARCH_DAYS
        self.disabled_reason = None
        self.last_call_error = None
        self.requests_made = 0
        self.budget = settings.APITUBE_MAX_REQUESTS_PER_RUN
        self._budget_notice_shown = False

    def _budget_left(self) -> bool:
        if self.budget <= 0 or self.requests_made < self.budget:
            return True
        if not self._budget_notice_shown:
            print(
                f"[APITube] Budget del run esaurito ({self.budget} richieste): "
                f"le aziende successive non vengono cercate qui. "
                f"Alza APITUBE_MAX_REQUESTS_PER_RUN se la tua quota lo permette."
            )
            self._budget_notice_shown = True
        return False

    def search_company_news(
        self, company_name: str, keywords: List[str] = None
    ) -> List[NewsArticle]:
        self.last_call_error = None

        if not self.api_key:
            self.last_call_error = "not configured"
            return []

        if self.disabled_reason:
            self.last_call_error = self.disabled_reason
            return []

        if not self._budget_left():
            self.last_call_error = "budget del run esaurito"
            return []

        # Quoted phrase = exact, in-order match. Without the quotes a name
        # like "Sag Tubi Tredozio" would match any article containing those
        # words separately.
        title_query = f'"{company_name}"'
        if keywords:
            title_query += " " + " ".join(keywords)

        since = (datetime.utcnow() - timedelta(days=self.days)).strftime("%Y-%m-%d")
        params = {
            "title": title_query,
            "language.code": settings.NEWS_LANGUAGE,
            "published_at.start": since,
            "per_page": min(settings.NEWS_MAX_RESULTS_PER_COMPANY, 20),
            "sort.by": "published_at",
            "sort.order": "desc",
        }
        if settings.APITUBE_COUNTRY_FILTER:
            params["source.country.code"] = settings.NEWS_COUNTRY.lower()

        try:
            self.requests_made += 1
            response = requests.get(
                APITUBE_ENDPOINT,
                params=params,
                timeout=self.timeout,
                headers={"X-API-Key": self.api_key, "Accept": "application/json"},
            )

            if response.status_code in (401, 403):
                self.disabled_reason = f"chiave APITUBE_API_KEY non valida o non autorizzata (HTTP {response.status_code})"
                print(f"[APITube] {self.disabled_reason}: disattivato per questo run")
                self.last_call_error = f"HTTP {response.status_code}"
                return []

            if response.status_code in (402, 429):
                self.disabled_reason = "quota APITube esaurita"
                print(f"[APITube] {self.disabled_reason} (HTTP {response.status_code}): disattivato per questo run")
                self.last_call_error = f"HTTP {response.status_code}"
                return []

            response.raise_for_status()
            data = response.json()

        except (requests.RequestException, ValueError) as e:
            print(f"[APITube] Errore cercando '{company_name}': {e}")
            self.last_call_error = "request exception"
            return []

        return self._parse(data, company_name)

    def _parse(self, data: Any, company_name: str) -> List[NewsArticle]:
        """
        Turn a response into articles.

        Written defensively on purpose: the exact envelope key has varied
        across APITube versions, so accept the documented one and the
        plausible alternatives rather than silently returning nothing.
        """
        if not isinstance(data, dict):
            self.last_call_error = "risposta inattesa"
            return []

        articles = None
        for key in ("results", "data", "articles"):
            if isinstance(data.get(key), list):
                articles = data[key]
                break

        if articles is None:
            # Don't fail silently: say what came back so it can be fixed.
            print(
                f"[APITube] Risposta senza elenco articoli per '{company_name}'. "
                f"Chiavi ricevute: {sorted(data.keys())}"
            )
            self.last_call_error = "formato risposta non riconosciuto"
            return []

        results = []
        for item in articles:
            if not isinstance(item, dict):
                continue

            title = item.get("title")
            url = item.get("href") or item.get("url") or item.get("link")
            if not title or not url:
                continue

            results.append(NewsArticle(
                title=title,
                url=url,
                source_name=self._source_name(item),
                source_type="apitube",
                published_date=self._parse_date(item.get("published_at") or item.get("published_date")),
                # description is the abstract; body is the full text, which
                # we deliberately don't store - only structured stubs go to
                # the classifier.
                summary=self._clean(item.get("description") or item.get("summary")),
                access_status="available",
                license_scope="summary_allowed",
            ))

        return results

    @staticmethod
    def _source_name(item: dict) -> str:
        source = item.get("source")
        if isinstance(source, dict):
            return source.get("name") or source.get("domain") or "APITube"
        if isinstance(source, str) and source:
            return source
        return "APITube"

    @staticmethod
    def _clean(text: str) -> str:
        if not text or not isinstance(text, str):
            return None
        text = " ".join(text.split())
        return text or None

    @staticmethod
    def _parse_date(value: Any) -> datetime:
        if not value or not isinstance(value, str):
            return datetime.utcnow()
        try:
            # Naive UTC everywhere else in the app, so drop the offset.
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return parsed.replace(tzinfo=None)
        except ValueError:
            for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
                try:
                    return datetime.strptime(value[:19], fmt)
                except ValueError:
                    continue
        return datetime.utcnow()

    def fetch_article_metadata(self, url: str) -> Dict[str, Any]:
        return {"title": None, "published_date": None, "summary": None, "source": "apitube"}

    def fetch_article_content(self, url: str) -> str:
        return None

    def check_access(self) -> bool:
        if not self.api_key:
            return False
        try:
            response = requests.get(
                APITUBE_ENDPOINT,
                params={"title": "test", "per_page": 1},
                timeout=self.timeout,
                headers={"X-API-Key": self.api_key, "Accept": "application/json"},
            )
            return response.status_code == 200
        except requests.RequestException:
            return False

    def is_enabled(self) -> bool:
        return bool(self.api_key)
