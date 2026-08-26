"""Tests for the "already seen" ledger.

Deduplication used to look only at the news_items table, so deleting an
article made the next run treat it as new, put it straight back, and pay
Claude to classify it again.
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.models import Base, Company, NewsItem, SeenArticle
from app.services.news_searcher import NewsSearcher
from app.services.heuristic_classifier import HeuristicClassifier


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


@pytest.fixture
def company(db):
    item = Company(company_name="Aquafil S.p.A.", status="Attiva", website="https://aquafil.com")
    db.add(item)
    db.commit()
    return item


@pytest.fixture
def searcher():
    s = NewsSearcher()
    s.classifier = HeuristicClassifier()
    return s


@pytest.fixture(autouse=True)
def remember_on():
    saved = settings.REMEMBER_DELETED_NEWS
    settings.REMEMBER_DELETED_NEWS = True
    yield
    settings.REMEMBER_DELETED_NEWS = saved


def article(**kwargs):
    base = {
        "title": "Aquafil investe 20 milioni in Slovenia",
        "url": "https://ilsole24ore.com/aquafil-slovenia",
        "source_name": "Il Sole 24 Ore", "source_type": "google_news_rss",
        "summary": None, "published_date": None,
        "access_status": "available", "license_scope": "summary_allowed",
    }
    base.update(kwargs)
    return base


def test_a_new_article_is_saved_and_recorded(db, company, searcher):
    searcher.process_and_classify_news(db, company, [article()])
    db.commit()

    assert db.query(NewsItem).count() == 1
    assert db.query(SeenArticle).count() == 1


def test_a_deleted_article_does_not_come_back(db, company, searcher):
    """The whole point of the ledger."""
    searcher.process_and_classify_news(db, company, [article()])
    db.commit()
    db.query(NewsItem).delete()
    db.commit()

    searcher.process_and_classify_news(db, company, [article()])
    db.commit()

    assert db.query(NewsItem).count() == 0


def test_the_same_story_from_another_source_is_recognised(db, company, searcher):
    """Same headline, different URL: still the same news."""
    searcher.process_and_classify_news(db, company, [article()])
    db.commit()
    db.query(NewsItem).delete()
    db.commit()

    searcher.process_and_classify_news(
        db, company, [article(url="https://repubblica.it/aquafil-slovenia")]
    )
    db.commit()

    assert db.query(NewsItem).count() == 0


def test_a_genuinely_different_article_still_gets_through(db, company, searcher):
    searcher.process_and_classify_news(db, company, [article()])
    db.commit()

    searcher.process_and_classify_news(db, company, [article(
        title="Aquafil chiude il bilancio 2026", url="https://ilsole24ore.com/aquafil-bilancio",
    )])
    db.commit()

    assert db.query(NewsItem).count() == 2


def test_the_ledger_is_per_company(db, company, searcher):
    """Two clients can legitimately both be in the same article."""
    other = Company(company_name="Banca Sella", status="Attiva", website="https://sella.it")
    db.add(other)
    db.commit()

    searcher.process_and_classify_news(db, company, [article()])
    db.commit()
    searcher.process_and_classify_news(db, other, [article(
        title="Aquafil e Banca Sella firmano un accordo",
        url="https://ilsole24ore.com/aquafil-sella",
    )])
    db.commit()

    assert db.query(NewsItem).count() == 2


def test_an_article_seen_again_is_not_re_classified(db, company, searcher):
    """A repeat must not cost another Claude call."""
    calls = {"n": 0}
    original = searcher.classifier.classify_news

    def counting(*args, **kwargs):
        calls["n"] += 1
        return original(*args, **kwargs)

    searcher.classifier.classify_news = counting

    searcher.process_and_classify_news(db, company, [article()])
    db.commit()
    db.query(NewsItem).delete()
    db.commit()
    searcher.process_and_classify_news(db, company, [article()])

    assert calls["n"] == 1, "the second pass classified an article it had already seen"


def test_the_match_ignores_case_and_spacing(db, company, searcher):
    searcher.process_and_classify_news(db, company, [article()])
    db.commit()
    db.query(NewsItem).delete()
    db.commit()

    searcher.process_and_classify_news(db, company, [article(
        url="https://ILSOLE24ORE.com/aquafil-slovenia  ",
    )])
    db.commit()

    assert db.query(NewsItem).count() == 0


def test_the_memory_can_be_switched_off(db, company, searcher):
    settings.REMEMBER_DELETED_NEWS = False

    searcher.process_and_classify_news(db, company, [article()])
    db.commit()
    db.query(NewsItem).delete()
    db.commit()
    searcher.process_and_classify_news(db, company, [article()])
    db.commit()

    assert db.query(NewsItem).count() == 1, "with the memory off the old behaviour returns"


def test_forgetting_lets_an_article_be_found_again(db, company, searcher):
    """The escape hatch for something deleted by mistake."""
    searcher.process_and_classify_news(db, company, [article()])
    db.commit()
    db.query(NewsItem).delete()
    db.commit()

    db.query(SeenArticle).delete()
    db.commit()

    searcher.process_and_classify_news(db, company, [article()])
    db.commit()

    assert db.query(NewsItem).count() == 1


def test_deleting_a_company_forgets_its_history(db, company, searcher):
    """Re-importing a company must not start with an empty archive."""
    searcher.process_and_classify_news(db, company, [article()])
    db.commit()

    db.delete(company)
    db.commit()

    assert db.query(SeenArticle).count() == 0
