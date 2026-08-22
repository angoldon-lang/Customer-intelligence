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
from app.models import Company, NewsItem
from app.services.classifier import NewsClassifier
from app.providers.base import NewsSourceProvider
from app.providers.google_news_rss import GoogleNewsRSSProvider
from app.providers.gdelt import GDELTProvider
from app.providers.gnews import GNewsProvider
from app.providers.rss import RSSProvider
from app.providers.test import TestNewsProvider


class NewsSearcher:
    """Search for news across providers, dedupe, and classify by relevance."""

    def __init__(self):
        self.classifier = NewsClassifier()

    def _build_providers(self, db: Session) -> List[NewsSourceProvider]:
        """Build the provider list for one monitoring run."""
        providers: List[NewsSourceProvider] = []

        # Google News RSS first: best coverage for small/local Italian
        # companies, which GDELT/GNews often don't index at all.
        if settings.GOOGLE_NEWS_RSS_ENABLED:
            providers.append(GoogleNewsRSSProvider())

        if settings.GDELT_ENABLED:
            providers.append(GDELTProvider())

        if settings.GNEWS_API_KEY:
            providers.append(GNewsProvider())

        if settings.RSS_ENABLED:
            rss = RSSProvider(db)
            rss.refresh()
            providers.append(rss)

        if not providers:
            # Nothing configured (no network / no keys) - fall back to
            # sample data so the rest of the pipeline stays testable.
            providers.append(TestNewsProvider())

        return providers

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

    def search_company_news(
        self, company: Company, providers: List[NewsSourceProvider]
    ) -> List[Dict[str, Any]]:
        """Search news for a specific company across all providers, deduped by URL."""
        seen_urls = set()
        news_items = []

        for provider in providers:
            try:
                articles = provider.search_company_news(company.company_name)
            except Exception as e:
                print(f"[NewsSearcher] {provider.__class__.__name__} failed for '{company.company_name}': {e}")
                continue

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

        return news_items

    def process_and_classify_news(
        self,
        db: Session,
        company: Company,
        news_items: List[Dict[str, Any]]
    ) -> List[NewsItem]:
        """Deduplicate against the DB, classify with Claude, and save."""
        saved_items = []

        for news_data in news_items:
            existing = db.query(NewsItem).filter(
                (NewsItem.url == news_data["url"]) |
                ((NewsItem.title == news_data["title"]) & (NewsItem.company_id == company.id))
            ).first()
            if existing:
                continue

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
            except Exception as e:
                print(f"[NewsSearcher] Classification failed for '{news_data['title']}': {e}")
                continue

            news_item = NewsItem(
                company_id=company.id,
                title=news_data["title"],
                url=news_data["url"],
                source_name=news_data["source_name"],
                source_type=news_data.get("source_type"),
                summary=classification.get("summary") or news_data.get("summary"),
                published_date=news_data.get("published_date"),
                category=classification.get("category", "Other"),
                relevance_score=classification.get("relevance_score", 5),
                urgency_score=classification.get("urgency_score", 5),
                commercial_score=classification.get("commercial_score", 5),
                risk_score=classification.get("risk_score", 5),
                confidence_score=classification.get("confidence_score", 5),
                access_status=news_data.get("access_status", "available"),
                license_scope=news_data.get("license_scope", "metadata_only"),
                status="New",
                created_at=datetime.utcnow(),
            )

            db.add(news_item)
            try:
                db.flush()
            except Exception as e:
                # url is unique - a race/dup slipped past the check above
                db.rollback()
                print(f"[NewsSearcher] Skipped duplicate news item: {e}")
                continue

            saved_items.append(news_item)

        if saved_items:
            db.commit()

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
            "errors": []
        }

        if companies is None:
            companies = db.query(Company).filter_by(status="Attiva").all()

        providers = self._build_providers(db)

        for company in companies:
            if self.is_ambiguous(company):
                result["companies_needing_enrichment"] += 1
                continue

            try:
                result["companies_checked"] += 1

                news_items = self.search_company_news(company, providers)
                if news_items:
                    result["news_found"] += len(news_items)
                    saved = self.process_and_classify_news(db, company, news_items)
                    result["news_saved"] += len(saved)

                company.last_monitored_at = datetime.utcnow()
                db.add(company)

            except Exception as e:
                result["errors"].append(f"{company.company_name}: {str(e)}")

        db.commit()
        return result
