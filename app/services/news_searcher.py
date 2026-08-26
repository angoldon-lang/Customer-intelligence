"""News search and monitoring service.

Pipeline: Google News RSS + GDELT + GNews.io + official RSS feeds produce a
deduplicated list of structured article stubs (title, url, source, date,
snippet only - never full page content), which are then handed to Claude
for the "intelligent" part: judging whether the article really is about
the company, summarizing it, and scoring it.
"""

from typing import List, Dict, Any, Optional
from datetime import datetime
from sqlalchemy.orm import Session
from app.config import settings
from app.models import Company, NewsItem, SearchLog, SeenArticle
from app.services.classifier import NewsClassifier
from app.providers.base import NewsSourceProvider
from app.providers.google_news_rss import GoogleNewsRSSProvider
from app.providers.gdelt import GDELTProvider
from app.providers.gnews import GNewsProvider
from app.providers.rss import RSSProvider
from app.providers.apitube import APITubeProvider
from app.providers.test import TestNewsProvider


class NewsSearcher:
    """Search for news across providers, dedupe, and classify by relevance."""

    def __init__(self):
        self.classifier = self._build_classifier()

    @staticmethod
    def _build_classifier():
        """
        Pick the classifier for CLASSIFIER_MODE.

        Rebuilt at the start of every run, not just once, so switching mode
        from Impostazioni (e.g. to the free heuristic one to stop consuming
        Anthropic credits) takes effect without restarting the server.
        """
        # CLASSIFIER_MODE lets you avoid API credits entirely:
        # "heuristic" classifies by keywords offline, "off" skips scoring.
        if settings.CLASSIFIER_MODE == "heuristic":
            from app.services.heuristic_classifier import HeuristicClassifier
            print("[NewsSearcher] Classificazione: euristica (gratuita, nessuna API)")
            return HeuristicClassifier()
        return NewsClassifier()

    # Source key -> how to build it. The key is what the user sees and
    # reorders in Impostazioni.
    PROVIDER_KEYS = ("google_news_rss", "gdelt", "gnews", "rss", "apitube")

    def _build_providers(self, db: Session) -> List[NewsSourceProvider]:
        """
        Build the provider list for one monitoring run.

        Which sources run, and in what order, comes from Impostazioni
        (PROVIDER_ORDER + the per-source switches) rather than being fixed
        in code: on some company lists the official RSS feeds are worth
        asking before Google News, on others the opposite.
        """
        available = {}

        if settings.GOOGLE_NEWS_RSS_ENABLED:
            available["google_news_rss"] = GoogleNewsRSSProvider

        if settings.GDELT_ENABLED:
            available["gdelt"] = GDELTProvider

        if settings.GNEWS_API_KEY:
            available["gnews"] = GNewsProvider

        if settings.RSS_ENABLED:
            available["rss"] = lambda: self._build_rss(db)

        if settings.APITUBE_API_KEY:
            available["apitube"] = self._build_apitube

        providers = [available[key]() for key in self.provider_order() if key in available]

        if not providers:
            # Nothing configured (no network / no keys) - fall back to
            # sample data so the rest of the pipeline stays testable.
            providers.append(TestNewsProvider())

        return providers

    @classmethod
    def provider_order(cls) -> List[str]:
        """Configured order, with any source missing from it appended."""
        configured = [
            key.strip()
            for key in (settings.PROVIDER_ORDER or "").split(",")
            if key.strip() in cls.PROVIDER_KEYS
        ]
        # A source left out of the setting must still run, just last -
        # otherwise adding a provider would silently disable it.
        return configured + [key for key in cls.PROVIDER_KEYS if key not in configured]

    @staticmethod
    def _build_rss(db: Session) -> NewsSourceProvider:
        rss = RSSProvider(db)
        rss.refresh()
        return rss

    @staticmethod
    def _build_apitube() -> NewsSourceProvider:
        apitube = APITubeProvider()
        # Paid and metered: by default only asked about companies the free
        # sources found nothing for, wherever it sits in the order.
        apitube.fallback_only = settings.APITUBE_FALLBACK_ONLY
        return apitube

    @staticmethod
    def is_ambiguous(company: Company) -> bool:
        """
        A company with no website and no tax code (P.IVA / codice fiscale)
        has no reliable anchor to disambiguate it from a homonym - a broad
        web search on a name like "ASA SRL" or "ARMANDO SRL" mostly returns
        noise. These are skipped until enriched with a website or tax code
        (see companies_needing_enrichment in the monitoring result).
        """
        return not company.website and not company.tax_code

    @staticmethod
    def _provider_label(provider: NewsSourceProvider) -> str:
        return provider.__class__.__name__.replace("Provider", "").lower()

    # Substrings of last_call_error that indicate a rate-limit/circuit
    # breaker condition rather than a genuine one-off failure.
    _BLOCKED_REASONS = (
        "HTTP 429", "HTTP 403", "HTTP 503",
        "disabled earlier this run", "in pausa",
        "quota exceeded", "malformed RSS response",
    )

    @classmethod
    def _classify_no_results(cls, provider_summary: List[str]) -> str:
        """
        Explain why a search found nothing.

        If even one provider completed its request, the "no news" answer is
        genuine and that's what we report - a secondary provider being
        rate-limited doesn't make the result unreliable. Only when every
        provider failed is the outcome actually unknown.
        """
        error_entries = [s for s in provider_summary if ":error(" in s]
        if not error_entries:
            return "no_results"

        # At least one provider answered successfully -> trust that answer.
        if len(error_entries) < len(provider_summary):
            return "no_results"

        if any(reason in s for s in error_entries for reason in cls._BLOCKED_REASONS):
            return "blocked"
        return "error"

    def search_company_news(
        self, company: Company, providers: List[NewsSourceProvider]
    ) -> tuple:
        """
        Search news for a specific company across all providers, deduped by
        URL. Returns (news_items, provider_summary) where provider_summary
        is a list of "provider:N" / "provider:blocked" / "provider:error(reason)"
        strings, recorded to SearchLog for per-company visibility.
        """
        seen_urls = set()
        news_items = []
        provider_summary = []

        for provider in providers:
            label = self._provider_label(provider)

            # Paid sources marked fallback_only are consulted only when the
            # free ones came up empty, so their quota goes to the companies
            # that actually need it.
            if getattr(provider, "fallback_only", False) and news_items:
                provider_summary.append(f"{label}:non necessario")
                continue

            try:
                articles = provider.search_company_news(company.company_name)
            except Exception as e:
                print(f"[NewsSearcher] {provider.__class__.__name__} failed for '{company.company_name}': {e}")
                provider_summary.append(f"{label}:error(exception)")
                continue

            # last_call_error is set by providers with a circuit breaker
            # (gdelt.py, gnews.py, google_news_rss.py) on THIS specific
            # call, distinct from the run-level blocked/rate_limited/
            # quota_exceeded flag - without it, a call that failed before
            # the breaker actually trips (e.g. the first of two strikes)
            # would be indistinguishable from a genuine "0 results found".
            last_error = getattr(provider, "last_call_error", None)
            if last_error:
                provider_summary.append(f"{label}:error({last_error})")
            else:
                provider_summary.append(f"{label}:{len(articles)}")

            for article in articles:
                url = (article.url or "").strip()
                if not url or url in seen_urls:
                    continue
                seen_urls.add(url)

                news_items.append({
                    "title": article.title,
                    "url": url,
                    "source_name": article.source_name,
                    "source_type": article.source_type,
                    "published_date": article.published_date,
                    "summary": article.summary,
                    "access_status": article.access_status,
                    "license_scope": article.license_scope,
                    "company_name": company.company_name,
                })

        return news_items, provider_summary

    @staticmethod
    def _fingerprint(value: str) -> str:
        """Stable hash of a URL or title, insensitive to case and spacing."""
        import hashlib

        normalised = " ".join((value or "").lower().split())
        return hashlib.sha256(normalised.encode("utf-8")).hexdigest()

    @classmethod
    def already_seen(cls, db: Session, company_id: int, url: str, title: str) -> bool:
        """Whether this article was ever offered for this company before."""
        if not settings.REMEMBER_DELETED_NEWS:
            return False

        url_hash = cls._fingerprint(url)
        title_hash = cls._fingerprint(title)

        row = (
            db.query(SeenArticle)
            .filter(
                SeenArticle.company_id == company_id,
                (SeenArticle.url_hash == url_hash) | (SeenArticle.title_hash == title_hash),
            )
            .first()
        )
        if not row:
            return False

        row.times_seen = (row.times_seen or 1) + 1
        row.last_seen_at = datetime.utcnow()
        return True

    @classmethod
    def remember_article(cls, db: Session, company_id: int, url: str, title: str) -> None:
        """Record the article so it is not offered again after a delete."""
        url_hash = cls._fingerprint(url)

        existing = (
            db.query(SeenArticle)
            .filter(SeenArticle.company_id == company_id, SeenArticle.url_hash == url_hash)
            .first()
        )
        if existing:
            existing.last_seen_at = datetime.utcnow()
            return

        db.add(SeenArticle(
            company_id=company_id,
            url_hash=url_hash,
            title_hash=cls._fingerprint(title),
        ))

    @staticmethod
    def is_off_topic(classification: Dict[str, Any]) -> bool:
        """
        Whether the classifier decided the article isn't about the company.

        Two signals, both from the classifier itself: the explicit verdict,
        and a confidence score at or below the configured floor. Kept off by
        setting AUTO_REJECT_OFF_TOPIC=False.
        """
        if not settings.AUTO_REJECT_OFF_TOPIC:
            return False

        if classification.get("is_about_company") is False:
            return True

        confidence = classification.get("confidence_score")
        # confidence 1 also means "not classified at all" (see
        # fallback_result), which is handled separately - don't reject those.
        if isinstance(confidence, (int, float)) and 1 < confidence <= settings.MIN_CONFIDENCE_SCORE:
            return True

        return False

    def process_and_classify_news(
        self,
        db: Session,
        company: Company,
        news_items: List[Dict[str, Any]]
    ) -> List[NewsItem]:
        """Deduplicate against the DB, classify with Claude, and save."""
        saved_items = []
        off_topic = 0
        already_seen = 0

        for news_data in news_items:
            existing = db.query(NewsItem).filter(
                (NewsItem.url == news_data["url"]) |
                ((NewsItem.title == news_data["title"]) & (NewsItem.company_id == company.id))
            ).first()
            if existing:
                self.remember_article(db, company.id, news_data["url"], news_data["title"])
                continue

            # Checked before classifying, not after: an article already seen
            # must not cost another Claude call. Deleting a news item used
            # to make the next run treat it as new and put it straight back.
            if self.already_seen(db, company.id, news_data["url"], news_data["title"]):
                already_seen += 1
                continue

            # A failed AI classification must NOT lose the article: the news
            # itself was really found and is still useful. Save it with a
            # neutral fallback classification and flag it "Needs Review" so
            # it stays visible and can be re-classified later.
            item_status = "New"
            try:
                classification = self.classifier.classify_news(
                    company_name=company.company_name,
                    title=news_data["title"],
                    url=news_data["url"],
                    source_name=news_data["source_name"],
                    article_text=news_data.get("summary"),
                    ateco_description=company.ateco_description,
                    account_owner=company.account_owner,
                    website=company.website,
                    tax_code=company.tax_code,
                )
                if classification.get("confidence_score") == 1 and not self.classifier.client:
                    item_status = "Needs Review"
                elif self.is_off_topic(classification):
                    # The classifier judged the article isn't about this
                    # company - Google News relaxes quoted queries and
                    # returns unrelated local news. Its verdict used to be
                    # stored and ignored, so the noise landed in the flow
                    # as if it were a real find. Park it as Rejected: still
                    # visible under the "Rifiutate" filter, out of the
                    # report, and removable in bulk.
                    item_status = "Rejected"
                    off_topic += 1
            except Exception as e:
                print(f"[NewsSearcher] Classification failed for '{news_data['title']}': {e} - saving unclassified")
                classification = self.classifier.fallback_result(
                    news_data["title"],
                    f"Classificazione AI fallita: {e}",
                    "Verifica la configurazione Claude, poi riclassifica dalla pagina Notizie",
                )
                item_status = "Needs Review"

            news_item = NewsItem(
                company_id=company.id,
                title=news_data["title"],
                url=news_data["url"],
                source_name=news_data["source_name"],
                source_type=news_data.get("source_type"),
                summary=classification.get("summary") or news_data.get("summary"),
                why_it_matters=classification.get("why_it_matters"),
                suggested_action=classification.get("suggested_action"),
                published_date=news_data.get("published_date"),
                category=classification.get("category", "Other"),
                relevance_score=classification.get("relevance_score", 5),
                urgency_score=classification.get("urgency_score", 5),
                commercial_score=classification.get("commercial_score", 5),
                risk_score=classification.get("risk_score", 5),
                confidence_score=classification.get("confidence_score", 5),
                access_status=news_data.get("access_status", "available"),
                license_scope=news_data.get("license_scope", "metadata_only"),
                status=item_status,
                created_at=datetime.utcnow(),
            )

            db.add(news_item)
            try:
                # Commit each article instead of flushing and committing at
                # the end: a flush takes the SQLite write lock, and the next
                # article's classification is a network call to Claude, so
                # the lock would be held across every API round-trip and the
                # dashboard would fail with "database is locked".
                db.commit()
            except Exception as e:
                # url is unique - a race/dup slipped past the check above
                db.rollback()
                print(f"[NewsSearcher] Skipped duplicate news item: {e}")
                continue

            self.remember_article(db, company.id, news_data["url"], news_data["title"])
            db.commit()

            saved_items.append(news_item)

        if off_topic:
            print(
                f"[NewsSearcher] {company.company_name}: {off_topic} notizie scartate "
                f"(non parlano dell'azienda). Le trovi con il filtro 'Rifiutate'."
            )
        if already_seen:
            print(f"[NewsSearcher] {company.company_name}: {already_seen} notizie gia' viste in passato, saltate")
        self.last_off_topic = off_topic
        self.last_already_seen = already_seen

        return saved_items

    def monitor_all_companies(
        self, db: Session, companies: Optional[List[Company]] = None
    ) -> Dict[str, Any]:
        """Monitor a set of companies for news (defaults to all active ones)."""
        result = {
            "companies_checked": 0,
            "companies_needing_enrichment": 0,
            "news_found": 0,
            "news_saved": 0,
            "news_unclassified": 0,
            "news_off_topic": 0,
            "classification_disabled_reason": None,
            "errors": []
        }

        if companies is None:
            companies = db.query(Company).filter_by(status="Attiva").all()

        # Rebuild the classifier so a mode/model change saved from
        # Impostazioni applies to this run. This also clears last run's
        # circuit breaker: the account problem may well have been fixed
        # since (credits topped up, key replaced), and this searcher
        # instance is reused for the lifetime of the process.
        self.classifier = self._build_classifier()
        self.classifier.disabled_reason = None

        providers = self._build_providers(db)

        for company in companies:
            if self.is_ambiguous(company):
                result["companies_needing_enrichment"] += 1
                db.add(SearchLog(
                    company_id=company.id,
                    status="skipped_ambiguous",
                    articles_found=0,
                    providers_detail="no website/tax code on file",
                ))
                db.commit()
                continue

            try:
                result["companies_checked"] += 1

                news_items, provider_summary = self.search_company_news(company, providers)
                providers_detail = ", ".join(provider_summary)

                if news_items:
                    result["news_found"] += len(news_items)
                    saved = self.process_and_classify_news(db, company, news_items)
                    result["news_saved"] += len(saved)
                    result["news_unclassified"] += sum(
                        1 for n in saved if n.status == "Needs Review"
                    )
                    result["news_off_topic"] += getattr(self, "last_off_topic", 0)
                    log_status = "found"
                else:
                    log_status = self._classify_no_results(provider_summary)

                db.add(SearchLog(
                    company_id=company.id,
                    status=log_status,
                    articles_found=len(news_items),
                    providers_detail=providers_detail,
                ))

                # Only count it as monitored if a search actually happened.
                # When every provider was blocked/paused, marking it checked
                # would push the company back to the end of its tier (up to
                # a week) over an outage that lasted a couple of minutes.
                if log_status not in ("blocked", "error"):
                    company.last_monitored_at = datetime.utcnow()
                    db.add(company)

                # Commit per company, not once at the end of the run. A run
                # over the full company list takes many minutes (providers
                # are throttled on purpose), and holding the write
                # transaction open for all of it locked out every write from
                # the dashboard: "database is locked" when saving a
                # recipient, a cluster or a setting mid-run.
                db.commit()

            except Exception as e:
                db.rollback()
                result["errors"].append(f"{company.company_name}: {str(e)}")
                db.add(SearchLog(
                    company_id=company.id,
                    status="error",
                    articles_found=0,
                    error_message=str(e),
                ))
                db.commit()

        db.commit()
        result["classification_disabled_reason"] = self.classifier.disabled_reason
        return result
