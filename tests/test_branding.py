"""Tests for report branding and the configurable search window."""

import os
from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.models import Base, Company, Cluster, CompanyCluster, NewsItem
from app.services import branding
from app.services.email_sender import EmailSender
from app.services.reporter import ReportGenerator

# Smallest valid PNG.
PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
    "890000000a49444154789c63000100000500010d0a2db40000000049454e44ae426082"
)


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setattr(branding, "LOGO_DIR", str(tmp_path / "branding"))
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


@pytest.fixture
def cluster(db):
    company = Company(company_name="Aquafil S.p.A.", status="Attiva")
    db.add(company)
    c = Cluster(cluster_name="Top clienti", cluster_type="manual",
                frequency="weekly", active=True, min_relevance_score=5)
    db.add(c)
    db.commit()
    db.add(CompanyCluster(company_id=company.id, cluster_id=c.id))
    db.add(NewsItem(company_id=company.id, title="Aquafil investe", url="https://x.it/1",
                    source_name="Il Sole", status="Approved", relevance_score=8,
                    urgency_score=5, commercial_score=6, risk_score=3,
                    published_date=datetime.utcnow()))
    db.commit()
    return c


def build(db, cluster):
    now = datetime.utcnow()
    return ReportGenerator().generate_cluster_report(
        db, cluster, now - timedelta(days=7), now + timedelta(days=1)
    )


# --- texts and colours ------------------------------------------------

def test_the_report_title_is_customisable(db, cluster):
    from app.services import settings_store
    settings_store.save_settings(db, {"BRAND_NAME": "ADC Group — Rassegna clienti"})

    report = build(db, cluster)

    assert "ADC Group" in report.body_html
    assert "ADC Group" in report.subject


def test_the_header_colour_is_applied(db, cluster):
    from app.services import settings_store
    settings_store.save_settings(db, {"BRAND_COLOR": "#8e44ad"})

    assert "#8e44ad" in build(db, cluster).body_html


@pytest.mark.parametrize("bad", ["red; } body { display:none", "javascript:alert(1)", "nonsense"])
def test_a_colour_that_is_not_hex_falls_back(db, cluster, bad):
    """The value goes straight into the email's CSS."""
    from app.services import settings_store
    settings_store.save_settings(db, {"BRAND_COLOR": bad})

    html = build(db, cluster).body_html

    assert "#2c3e50" in html
    assert "display:none" not in html


def test_the_opening_text_is_customisable(db, cluster):
    from app.services import settings_store
    settings_store.save_settings(db, {"REPORT_INTRO": "Ciao team,\necco la rassegna."})

    html = build(db, cluster).body_html

    assert "<p>Ciao team,</p>" in html
    assert "<p>ecco la rassegna.</p>" in html


def test_the_footer_is_customisable(db, cluster):
    from app.services import settings_store
    settings_store.save_settings(db, {"REPORT_FOOTER": "ADC Group S.p.A. - riservato"})

    assert "ADC Group S.p.A. - riservato" in build(db, cluster).body_html


def test_scores_can_be_hidden(db, cluster):
    from app.services import settings_store

    assert "Rilevanza:" in build(db, cluster).body_html

    settings_store.save_settings(db, {"REPORT_SHOW_SCORES": "false"})
    assert "Rilevanza:" not in build(db, cluster).body_html


# --- logo -------------------------------------------------------------

def test_a_logo_is_stored_and_referenced_by_cid(db, cluster):
    branding.save_logo(db, PNG, "image/png", "logo.png")

    html = build(db, cluster).body_html

    assert f'src="cid:{branding.LOGO_CID}"' in html


def test_no_logo_means_no_image_tag(db, cluster):
    assert "cid:" not in build(db, cluster).body_html


def test_the_logo_is_attached_to_the_email(db, cluster):
    """A cid: reference without the attachment shows as a broken image."""
    branding.save_logo(db, PNG, "image/png", "logo.png")
    html = build(db, cluster).body_html

    sender = EmailSender(db)
    part = sender._logo_part(html)

    assert part is not None
    assert part.get("Content-ID") == f"<{branding.LOGO_CID}>"
    assert part.get_content_type() == "image/png"


def test_nothing_is_attached_when_the_body_has_no_logo(db):
    branding.save_logo(db, PNG, "image/png", "logo.png")
    sender = EmailSender(db)

    assert sender._logo_part("<p>Report senza logo</p>") is None


def test_a_deleted_logo_file_does_not_stop_the_email(db):
    branding.save_logo(db, PNG, "image/png", "logo.png")
    sender = EmailSender(db)
    os.remove(sender.logo_path)

    assert sender._logo_part(f'<img src="cid:{branding.LOGO_CID}">') is None


@pytest.mark.parametrize("content_type", ["application/pdf", "text/html", "image/svg+xml"])
def test_only_real_image_formats_are_accepted(db, content_type):
    with pytest.raises(ValueError):
        branding.save_logo(db, PNG, content_type, "logo.x")


def test_an_oversized_logo_is_refused(db):
    with pytest.raises(ValueError):
        branding.save_logo(db, b"x" * (branding.MAX_LOGO_BYTES + 1), "image/png", "logo.png")


def test_uploading_again_replaces_the_previous_logo(db):
    branding.save_logo(db, PNG, "image/png", "logo.png")
    branding.save_logo(db, PNG, "image/jpeg", "logo.jpg")

    files = os.listdir(branding.LOGO_DIR)
    assert files == ["logo.jpg"], f"stale files left behind: {files}"


def test_removing_the_logo_clears_the_setting_and_the_file(db):
    branding.save_logo(db, PNG, "image/png", "logo.png")

    assert branding.remove_logo(db) is True
    assert branding.logo_path(db) is None


# --- search window ----------------------------------------------------

def test_every_provider_uses_the_same_window(monkeypatch):
    from app.providers.google_news_rss import GoogleNewsRSSProvider
    from app.providers.apitube import APITubeProvider

    monkeypatch.setattr(settings, "NEWS_SEARCH_DAYS", 14)

    assert GoogleNewsRSSProvider().days == 14
    assert APITubeProvider(api_key="x").days == 14


def test_the_window_reaches_the_google_news_query(monkeypatch):
    from app.providers import google_news_rss
    from app.providers.google_news_rss import GoogleNewsRSSProvider

    monkeypatch.setattr(settings, "NEWS_SEARCH_DAYS", 7)
    monkeypatch.setattr(google_news_rss.time, "sleep", lambda s: None)

    captured = {}

    def fake_get(url, params=None, timeout=None, headers=None):
        captured.update(params)
        raise google_news_rss.requests.ConnectionError("stop here")

    monkeypatch.setattr(google_news_rss.requests, "get", fake_get)
    GoogleNewsRSSProvider().search_company_news("Aquafil S.p.A.")

    assert "when:7d" in captured["q"]


def test_gdelt_is_clamped_to_its_own_limit(monkeypatch):
    """GDELT's free API refuses a timespan beyond about three months."""
    from app.providers import gdelt
    from app.providers.gdelt import GDELTProvider

    monkeypatch.setattr(settings, "NEWS_SEARCH_DAYS", 365)
    monkeypatch.setattr(gdelt.time, "sleep", lambda s: None)

    captured = {}

    def fake_get(url, params=None, timeout=None):
        captured.update(params)
        raise gdelt.requests.ConnectionError("stop here")

    monkeypatch.setattr(gdelt.requests, "get", fake_get)
    GDELTProvider().search_company_news("Aquafil S.p.A.")

    assert captured["timespan"] == "90d"
