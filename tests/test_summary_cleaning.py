"""Tests for cleaning Google News summaries.

Google News puts markup, not prose, in <description>. When something
upstream truncated that markup mid-tag, the old cleaner could not match the
unclosed tag and the raw HTML reached the card verbatim - a wall of
'<a href="https://news.google.com/rss/articles/CBMixgF...'.
"""

import pytest

from app.providers.google_news_rss import GoogleNewsRSSProvider as Provider


TITLE = 'Palermo, riaperto al transito un tratto di viale Michelangelo'

DESCRIPTION = (
    '<a href="https://news.google.com/rss/articles/'
    'CBMixgFBVV95cUxPT2dYS1BnekhId2Y5cEczdWVtcDY0cnk2aWc5aWNaZy03MEd0dXVaUNhRzRrekhOV3hR'
    'SXZCbjFRUTFIdHFvUXhkLVhKcWxEaWI2ejY4Z0dKQ3Jud2Zt?oc=5" target="_blank">'
    + TITLE +
    '</a>&nbsp;&nbsp;<font color="#6f6f6f">La Sicilia</font>'
)


def test_markup_is_stripped_from_a_complete_description():
    cleaned = Provider.clean_summary(DESCRIPTION, TITLE)

    assert '<' not in (cleaned or '')
    assert 'news.google.com' not in (cleaned or '')


@pytest.mark.parametrize("cut", [60, 120, 200, 300])
def test_a_description_cut_mid_tag_never_reaches_the_card(cut):
    """The exact bug: no closing '>' meant nothing was stripped."""
    cleaned = Provider.clean_summary(DESCRIPTION[:cut], TITLE)

    assert '<a href' not in (cleaned or ''), "raw markup survived the cleaning"
    assert 'CBMixgF' not in (cleaned or ''), "the base64 article id survived"


def test_real_prose_is_kept():
    cleaned = Provider.clean_summary(
        "<p>Il gruppo annuncia un investimento da 20 milioni di euro.</p>", TITLE
    )

    assert cleaned == "Il gruppo annuncia un investimento da 20 milioni di euro."


def test_a_summary_that_only_repeats_the_headline_is_dropped():
    assert Provider.clean_summary(f"<p>{TITLE}</p>", TITLE) is None


def test_a_bare_link_is_not_a_summary():
    assert Provider.clean_summary("https://www.lasicilia.it/articolo-12345", TITLE) is None


def test_html_entities_are_decoded():
    cleaned = Provider.clean_summary("<p>Utili &gt; 10 milioni &amp; in crescita</p>", TITLE)

    assert cleaned == "Utili > 10 milioni & in crescita"


def test_empty_input_is_handled():
    assert Provider.clean_summary(None, TITLE) is None
    assert Provider.clean_summary("", TITLE) is None
    assert Provider.clean_summary("<a href='x'>", TITLE) is None


def test_stored_rows_are_repaired_by_the_maintenance_action():
    """"Correggi link notizie" must fix what is already in the database."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.models import Base, Company, NewsItem

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()

    company = Company(company_name="CMC RAVENNA SPA", status="Attiva")
    db.add(company)
    db.commit()

    # Stored the way the screenshot showed them: markup, cut mid-tag.
    db.add(NewsItem(
        company_id=company.id, title=TITLE,
        url="https://news.google.com/rss/articles/CBMixgF",
        source_name="La Sicilia", status="New", summary=DESCRIPTION[:200],
    ))
    db.commit()

    stored = db.query(NewsItem).first()
    repaired = Provider.clean_summary(stored.summary, stored.title)
    stored.summary = repaired
    db.commit()

    assert '<a href' not in (db.query(NewsItem).first().summary or '')
    db.close()
