"""Tests for what the report email actually contains.

Two problems from the delivered email: the only link was the small source
name, and it pointed at a Google News /rss/ URL that opens raw XML
("Questo feed non e' disponibile") instead of the article.
"""

from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models import Base, Company, Cluster, CompanyCluster, NewsItem
from app.services.reporter import ReportGenerator

# The opaque id format: the payload holds no publisher URL at all.
BROKEN_URL = "https://news.google.com/rss/articles/CBMisgFBVV95cUxOeWhQYQ"
TITLE = "Scienze motorie, sport e salute: nuovo bando di ammissione - unipr.it"


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


@pytest.fixture
def cluster(db):
    company = Company(company_name="CISIA", status="Attiva", website="https://cisiaonline.it")
    db.add(company)
    cluster = Cluster(cluster_name="Account: Andrea Goldoni", cluster_type="manual",
                      frequency="weekly", active=True, min_relevance_score=5)
    db.add(cluster)
    db.commit()
    db.add(CompanyCluster(company_id=company.id, cluster_id=cluster.id))
    db.commit()
    return cluster


def add_news(db, cluster, **kwargs):
    company = db.query(Company).first()
    defaults = dict(
        company_id=company.id, title=TITLE, url=BROKEN_URL, source_name="unipr.it",
        status="Approved", relevance_score=6, urgency_score=4,
        commercial_score=5, risk_score=3, published_date=datetime.utcnow(),
    )
    defaults.update(kwargs)
    item = NewsItem(**defaults)
    db.add(item)
    db.commit()
    return item


def build(db, cluster):
    now = datetime.utcnow()
    return ReportGenerator().generate_cluster_report(
        db, cluster, now - timedelta(days=7), now + timedelta(days=1)
    )


# --- the link works ---------------------------------------------------

def test_a_broken_google_news_link_is_never_sent(db, cluster):
    add_news(db, cluster)

    report = build(db, cluster)

    assert "news.google.com/rss/articles" not in report.body_html
    assert "news.google.com/rss/articles" not in report.body_text


def test_the_reader_gets_a_search_on_the_headline_instead(db, cluster):
    add_news(db, cluster)

    report = build(db, cluster)

    assert "google.com/search" in report.body_html
    assert "Scienze+motorie" in report.body_html


def test_a_working_publisher_link_is_left_alone(db, cluster):
    add_news(db, cluster, url="https://www.unipr.it/notizie/bando-2026")

    report = build(db, cluster)

    assert "https://www.unipr.it/notizie/bando-2026" in report.body_html


def test_there_is_an_explicit_read_button_not_just_the_source_name(db, cluster):
    add_news(db, cluster)

    report = build(db, cluster)

    assert "Leggi l'articolo" in report.body_html
    assert "Leggi l'articolo" in report.body_text


def test_the_headline_itself_is_a_link(db, cluster):
    add_news(db, cluster)

    assert f'<h3>1. <a href=' in build(db, cluster).body_html


# --- the text under the headline --------------------------------------

def test_the_summary_appears_in_the_email(db, cluster):
    add_news(db, cluster, summary="L'ateneo riapre le iscrizioni per i posti rimasti liberi.")

    report = build(db, cluster)

    assert "L'ateneo riapre le iscrizioni" in report.body_html
    assert "L'ateneo riapre le iscrizioni" in report.body_text


def test_why_it_matters_is_included(db, cluster):
    """The classifier writes this on every article and it used to be lost."""
    add_news(db, cluster, summary="Nuovo bando.",
             why_it_matters="CISIA gestisce i test di ammissione: possibile picco di traffico.")

    report = build(db, cluster)

    assert "possibile picco di traffico" in report.body_html


def test_the_text_is_capped_to_a_few_lines(db, cluster):
    add_news(db, cluster, summary="parola " * 200)

    text = ReportGenerator.article_text(db.query(NewsItem).first())

    assert len(text) <= 325
    assert text.endswith("...")


def test_the_placeholder_of_an_unclassified_item_is_not_shown(db, cluster):
    add_news(db, cluster, summary=None,
             why_it_matters="Classificazione AI fallita: credit balance too low")

    assert ReportGenerator.article_text(db.query(NewsItem).first()) == ""


def test_an_item_with_no_text_still_renders(db, cluster):
    add_news(db, cluster, summary=None, why_it_matters=None)

    report = build(db, cluster)

    assert TITLE in report.body_html
    assert "Leggi l'articolo" in report.body_html


def test_summary_and_why_are_not_duplicated(db, cluster):
    add_news(db, cluster, summary="Stessa frase.", why_it_matters="Stessa frase.")

    assert ReportGenerator.article_text(db.query(NewsItem).first()) == "Stessa frase."


# --- safety -----------------------------------------------------------

def test_markup_in_a_headline_cannot_break_the_email(db, cluster):
    """Headlines come from third-party feeds and went in unescaped."""
    add_news(db, cluster, title='Titolo <script>alert(1)</script> & "virgolette"')

    html = build(db, cluster).body_html

    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html
