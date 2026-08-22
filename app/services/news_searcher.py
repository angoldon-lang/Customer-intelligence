"""News search and monitoring service."""

from typing import List, Dict, Any
from datetime import datetime, timedelta
import requests
from bs4 import BeautifulSoup
from sqlalchemy.orm import Session
from app.models import Company, NewsItem, NewsSource
from app.services.classifier import NewsClassifier
from app.providers.test import TestNewsProvider  # Use test provider for now


class NewsSearcher:
    """Search for news and classify by relevance."""

    def __init__(self, use_test_provider: bool = True):
        self.classifier = NewsClassifier()
        # Use test provider by default for development/testing
        if use_test_provider:
            self.test_provider = TestNewsProvider()
        else:
            self.test_provider = None

    def search_company_news(self, company: Company) -> List[Dict[str, Any]]:
        """Search news for a specific company."""
        news_items = []

        # Use test provider first (for development/testing)
        if self.test_provider:
            test_articles = self.test_provider.search_company_news(company.company_name)
            for article in test_articles:
                news_items.append({
                    'title': article.title,
                    'url': article.url,
                    'source_name': article.source_name,
                    'published_date': article.published_date,
                    'summary': article.summary,
                    'company_name': company.company_name,
                })

        # Also try Google News (will fail due to proxy but keeping for future)
        # news_from_google = self._search_google_news(company.company_name)
        # news_items.extend(news_from_google)

        return news_items

    def _search_google_news(self, company_name: str) -> List[Dict[str, Any]]:
        """Search Google News for company."""
        try:
            # Using a simple approach with news search
            # In production, you'd use NewsAPI or similar service
            url = f"https://news.google.com/search?q={company_name}&hl=en-US&gl=US&ceid=US:en"

            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }

            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()

            soup = BeautifulSoup(response.content, 'html.parser')
            news_items = []

            # Parse Google News articles
            articles = soup.find_all('article', limit=10)
            for article in articles:
                try:
                    title_elem = article.find('h3')
                    link_elem = article.find('a')
                    time_elem = article.find('time')
                    source_elem = article.find('div', {'data-n-tooltip': True})

                    if title_elem and link_elem:
                        news_items.append({
                            'title': title_elem.get_text(strip=True),
                            'url': link_elem.get('href', ''),
                            'source_name': source_elem.get_text(strip=True) if source_elem else 'Google News',
                            'published_date': datetime.utcnow(),
                            'summary': '',
                            'company_name': company_name,
                        })
                except Exception:
                    continue

            return news_items

        except Exception as e:
            print(f"Error searching Google News: {e}")
            return []

    def process_and_classify_news(
        self,
        db: Session,
        company: Company,
        news_items: List[Dict[str, Any]]
    ) -> List[NewsItem]:
        """Process and classify news items."""
        saved_items = []

        for news_data in news_items:
            # Check if news already exists (deduplicate)
            existing = db.query(NewsItem).filter_by(
                title=news_data['title'],
                company_id=company.id
            ).first()

            if existing:
                continue

            # Classify with AI
            classification = self.classifier.classify_news(
                company_name=company.company_name,
                title=news_data['title'],
                url=news_data['url'],
                source_name=news_data['source_name'],
                article_text=news_data.get('summary', ''),
            )

            # Create news item
            news_item = NewsItem(
                company_id=company.id,
                title=news_data['title'],
                url=news_data['url'],
                source_name=news_data['source_name'],
                summary=news_data.get('summary', ''),
                category=classification.get('category', 'Other'),
                relevance_score=classification.get('relevance_score', 5),
                urgency_score=classification.get('urgency_score', 5),
                commercial_score=classification.get('commercial_score', 5),
                risk_score=classification.get('risk_score', 5),
                status='New',
                created_at=datetime.utcnow(),
            )

            db.add(news_item)
            saved_items.append(news_item)

        if saved_items:
            db.commit()

        return saved_items

    def monitor_all_companies(self, db: Session) -> Dict[str, Any]:
        """Monitor all active companies for news."""
        result = {
            'companies_checked': 0,
            'news_found': 0,
            'news_saved': 0,
            'errors': []
        }

        companies = db.query(Company).filter_by(status='Attiva').all()

        for company in companies:
            try:
                result['companies_checked'] += 1

                # Search news
                news_items = self.search_company_news(company)
                if news_items:
                    result['news_found'] += len(news_items)

                    # Process and save
                    saved = self.process_and_classify_news(db, company, news_items)
                    result['news_saved'] += len(saved)

            except Exception as e:
                result['errors'].append(f"{company.company_name}: {str(e)}")

        return result
