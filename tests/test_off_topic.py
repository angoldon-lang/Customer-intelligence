"""Tests for keeping articles that aren't about the company out of the flow.

Google News relaxes a quoted query when it finds few hits, so searching
"CMC RAVENNA SPA" returned local news about roadworks in Palermo. The
classifier's verdict on that was stored and then ignored, so the noise
entered the flow as if it were a real find.
"""

import pytest

from app.config import settings
from app.services.classifier import NewsClassifier
from app.services.heuristic_classifier import HeuristicClassifier
from app.services.news_searcher import NewsSearcher


@pytest.fixture(autouse=True)
def restore_settings():
    saved = (settings.AUTO_REJECT_OFF_TOPIC, settings.MIN_CONFIDENCE_SCORE)
    yield
    settings.AUTO_REJECT_OFF_TOPIC, settings.MIN_CONFIDENCE_SCORE = saved


# --- does the name actually appear ------------------------------------

def test_the_real_false_positive_is_recognised():
    """The exact article from the screenshot, filed under CMC Ravenna."""
    assert NewsClassifier.name_appears(
        "CMC RAVENNA SPA",
        'Palermo, riaperto al transito un tratto di viale Michelangelo: "Fine dei disagi"',
    ) is False


def test_a_genuine_mention_is_recognised():
    assert NewsClassifier.name_appears(
        "CMC RAVENNA SPA",
        "CMC Ravenna si aggiudica l'appalto per la nuova tratta ferroviaria",
    ) is True


def test_legal_forms_do_not_count_as_a_match():
    """Otherwise every article mentioning "S.p.A." would look like a hit."""
    assert NewsClassifier.name_appears(
        "AQUAFIL S.P.A.", "La societa' S.p.A. ha chiuso il bilancio"
    ) is False


def test_every_distinctive_word_must_be_present():
    """"Ravenna" alone is a city, not this company."""
    assert NewsClassifier.name_appears(
        "CMC RAVENNA SPA", "Ravenna, aperto il nuovo tratto stradale"
    ) is False


def test_the_snippet_counts_too():
    assert NewsClassifier.name_appears(
        "CMC RAVENNA SPA",
        "Nuovo appalto ferroviario",
        "L'opera e' stata assegnata a CMC Ravenna, che iniziera' i lavori a settembre.",
    ) is True


def test_a_match_is_case_and_punctuation_insensitive():
    assert NewsClassifier.name_appears("Aquafil S.p.A.", "AQUAFIL investe in Slovenia") is True
    assert NewsClassifier.name_appears("Banca Sella", "banca sella cresce nel 2026") is True


def test_an_empty_company_name_never_matches():
    assert NewsClassifier.name_appears("", "Un titolo qualsiasi") is False
    assert NewsClassifier.name_appears("S.p.A.", "Un titolo qualsiasi") is False


# --- acting on the verdict --------------------------------------------

def test_an_explicit_negative_verdict_is_respected():
    assert NewsSearcher.is_off_topic({"is_about_company": False, "confidence_score": 8}) is True


def test_a_positive_verdict_is_kept_even_with_middling_confidence():
    assert NewsSearcher.is_off_topic({"is_about_company": True, "confidence_score": 5}) is False


def test_low_confidence_alone_is_enough_to_park_it():
    settings.MIN_CONFIDENCE_SCORE = 3

    assert NewsSearcher.is_off_topic({"confidence_score": 2}) is True
    assert NewsSearcher.is_off_topic({"confidence_score": 3}) is True
    assert NewsSearcher.is_off_topic({"confidence_score": 4}) is False


def test_an_unclassified_item_is_not_treated_as_off_topic():
    """confidence 1 means "the AI never ran", not "wrong company"."""
    settings.MIN_CONFIDENCE_SCORE = 3

    assert NewsSearcher.is_off_topic({"confidence_score": 1}) is False


def test_the_filter_can_be_switched_off():
    settings.AUTO_REJECT_OFF_TOPIC = False

    assert NewsSearcher.is_off_topic({"is_about_company": False, "confidence_score": 1}) is False


def test_a_classification_without_the_field_is_kept():
    """An older/partial result must not be thrown away by default."""
    settings.MIN_CONFIDENCE_SCORE = 3

    assert NewsSearcher.is_off_topic({"relevance_score": 7, "confidence_score": 7}) is False
    assert NewsSearcher.is_off_topic({}) is False


# --- the free classifier agrees ---------------------------------------

def test_the_heuristic_classifier_reports_the_same_verdict():
    classifier = HeuristicClassifier()

    off_topic = classifier.classify_news(
        company_name="CMC RAVENNA SPA",
        title="Palermo, riaperto al transito un tratto di viale Michelangelo",
        url="https://x.it/1",
        source_name="La Sicilia",
    )
    on_topic = classifier.classify_news(
        company_name="CMC RAVENNA SPA",
        title="CMC Ravenna si aggiudica un appalto da 40 milioni",
        url="https://x.it/2",
        source_name="Il Sole 24 Ore",
    )

    assert off_topic["is_about_company"] is False
    assert on_topic["is_about_company"] is True
    assert NewsSearcher.is_off_topic(off_topic) is True
    assert NewsSearcher.is_off_topic(on_topic) is False


# --- end to end -------------------------------------------------------

def test_an_off_topic_article_is_saved_as_rejected_not_lost():
    """It must stay recoverable: the user was burned by news disappearing."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.models import Base, Company, NewsItem

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()

    company = Company(company_name="CMC RAVENNA SPA", status="Attiva", website="https://cmc.it")
    db.add(company)
    db.commit()

    searcher = NewsSearcher()
    searcher.classifier = HeuristicClassifier()

    saved = searcher.process_and_classify_news(db, company, [
        {
            "title": "Palermo, riaperto al transito un tratto di viale Michelangelo",
            "url": "https://x.it/palermo", "source_name": "La Sicilia",
            "source_type": "google_news_rss", "summary": None,
            "published_date": None, "access_status": "available",
            "license_scope": "summary_allowed",
        },
        {
            "title": "CMC Ravenna si aggiudica un appalto da 40 milioni",
            "url": "https://x.it/appalto", "source_name": "Il Sole 24 Ore",
            "source_type": "google_news_rss", "summary": None,
            "published_date": None, "access_status": "available",
            "license_scope": "summary_allowed",
        },
    ])

    assert len(saved) == 2, "nothing may be discarded outright"

    status_of = {n.url: n.status for n in db.query(NewsItem).all()}
    assert status_of["https://x.it/palermo"] == "Rejected", "the false positive entered the flow"
    assert status_of["https://x.it/appalto"] == "New", "a genuine article was parked"

    db.close()
