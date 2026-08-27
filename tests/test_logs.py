"""Tests for the search log and its CSV export."""

from datetime import datetime, timedelta

import csv
import io

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.database import SessionLocal
from app.models import (
    AppSetting, Company, Cluster, CompanyCluster, ClusterRecipient,
    MonitoringRun, NewsItem, SearchLog, SeenArticle,
)
from app.services import auth

PASSWORD = "unaPasswordLunga1"


def wipe(db):
    for model in (NewsItem, SeenArticle, SearchLog, MonitoringRun,
                  CompanyCluster, ClusterRecipient, Cluster, Company, AppSetting):
        db.query(model).delete()
    db.commit()


@pytest.fixture
def client():
    db = SessionLocal()
    wipe(db)
    db.close()
    auth.login_throttle.record_success()

    c = TestClient(app, follow_redirects=False)
    c.post("/api/auth/setup", data={
        "username": "admin", "password": PASSWORD, "password_confirm": PASSWORD,
    })
    yield c

    db = SessionLocal()
    wipe(db)
    db.close()


@pytest.fixture
def db():
    session = SessionLocal()
    yield session
    session.close()


@pytest.fixture
def seeded(db):
    entries = [
        ("Aquafil S.p.A.", "found", 4, None),
        ("Banca Sella", "no_results", 0, None),
        ("CMC Ravenna", "error", 0, "HTTP 503 dopo 4 tentativi"),
        ("Sag Tubi Tredozio", "blocked", 0, None),
    ]
    for index, (name, status, count, error) in enumerate(entries):
        company = Company(company_name=name, status="Attiva", website="https://x.it")
        db.add(company)
        db.commit()
        db.add(SearchLog(
            company_id=company.id, status=status, articles_found=count,
            providers_detail="googlenewsrss:%d, gdelt:0" % count,
            error_message=error,
            searched_at=datetime.utcnow() - timedelta(minutes=index),
        ))
    db.add(MonitoringRun(
        started_at=datetime.utcnow() - timedelta(minutes=25),
        finished_at=datetime.utcnow() - timedelta(minutes=3),
        companies_processed=194, news_found=413, errors_count=2, status="Completed",
    ))
    db.commit()


def parse_csv(response):
    text = response.text.lstrip("﻿")
    return list(csv.reader(io.StringIO(text), delimiter=";"))


# --- reading the log --------------------------------------------------

def test_the_log_lists_outcomes_newest_first(client, seeded):
    data = client.get("/api/logs").json()

    assert data["total"] == 4
    stamps = [e["searched_at"] for e in data["entries"]]
    assert stamps == sorted(stamps, reverse=True)


def test_each_entry_carries_what_happened(client, seeded):
    entries = {e["company_name"]: e for e in client.get("/api/logs").json()["entries"]}

    assert entries["Aquafil S.p.A."]["articles_found"] == 4
    assert entries["Aquafil S.p.A."]["label"] == "Notizie trovate"
    assert entries["CMC Ravenna"]["error_message"] == "HTTP 503 dopo 4 tentativi"
    assert "googlenewsrss" in entries["Banca Sella"]["providers_detail"]


def test_statuses_are_translated_not_raw(client, seeded):
    labels = {e["label"] for e in client.get("/api/logs").json()["entries"]}

    assert "Nessun risultato" in labels
    assert "no_results" not in labels


def test_the_tally_counts_every_outcome(client, seeded):
    tally = {s["status"]: s["count"] for s in client.get("/api/logs").json()["by_status"]}

    assert tally == {"found": 1, "no_results": 1, "error": 1, "blocked": 1}


def test_the_log_can_be_filtered_by_outcome(client, seeded):
    data = client.get("/api/logs?status=error").json()

    assert data["total"] == 1
    assert data["entries"][0]["company_name"] == "CMC Ravenna"


def test_the_log_can_be_filtered_by_company(client, seeded):
    data = client.get("/api/logs?search=aquafil").json()

    assert [e["company_name"] for e in data["entries"]] == ["Aquafil S.p.A."]


def test_an_empty_log_is_not_an_error(client):
    data = client.get("/api/logs").json()

    assert data["total"] == 0
    assert data["entries"] == []


# --- run history ------------------------------------------------------

def test_the_run_history_reports_duration_and_counts(client, seeded):
    run = client.get("/api/logs/runs").json()["runs"][0]

    assert run["companies_processed"] == 194
    assert run["news_found"] == 413
    assert run["errors_count"] == 2
    assert run["duration_seconds"] == pytest.approx(22 * 60, abs=5)


def test_an_unfinished_run_has_no_duration(client, db):
    db.add(MonitoringRun(started_at=datetime.utcnow(), status="running"))
    db.commit()

    assert client.get("/api/logs/runs").json()["runs"][0]["duration_seconds"] is None


# --- CSV export -------------------------------------------------------

def test_the_search_log_downloads_as_csv(client, seeded):
    response = client.get("/api/logs/export?kind=search")

    assert response.status_code == 200
    assert "text/csv" in response.headers["content-type"]
    assert "attachment" in response.headers["content-disposition"]
    assert ".csv" in response.headers["content-disposition"]


def test_the_csv_has_a_header_and_a_row_per_entry(client, seeded):
    rows = parse_csv(client.get("/api/logs/export?kind=search"))

    assert rows[0] == ["Data", "Azienda", "Esito", "Notizie trovate", "Dettaglio fonti", "Errore"]
    assert len(rows) == 5  # header + 4 entries


def test_the_run_history_downloads_as_csv(client, seeded):
    rows = parse_csv(client.get("/api/logs/export?kind=runs"))

    assert rows[0][0] == "Inizio"
    assert rows[1][3] == "194"


def test_the_csv_starts_with_a_bom_so_excel_reads_the_accents(client, seeded):
    """Without it Excel shows "Saltata (manca P.IVA/sito)" as mojibake."""
    assert client.get("/api/logs/export?kind=search").text.startswith("﻿")


def test_a_company_name_with_a_separator_does_not_break_the_csv(client, db):
    """Names contain semicolons, quotes and commas; hand-built CSV corrupts."""
    company = Company(company_name='Rossi; "Figli" & C. Srl', status="Attiva")
    db.add(company)
    db.commit()
    db.add(SearchLog(company_id=company.id, status="error", articles_found=0,
                     error_message='Errore: "timeout"; riprovare'))
    db.commit()

    rows = parse_csv(client.get("/api/logs/export?kind=search"))

    assert len(rows) == 2, "the row was split across lines"
    assert rows[1][1] == 'Rossi; "Figli" & C. Srl'
    assert rows[1][5] == 'Errore: "timeout"; riprovare'


def test_the_log_needs_a_session(client):
    client.cookies.clear()

    assert client.get("/api/logs").status_code == 401
    assert client.get("/api/logs/export").status_code == 401
