"""Tests for the weekly-flow guide and the scheduler being remembered."""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.database import SessionLocal
from app.models import (
    AppSetting, Company, Cluster, ClusterRecipient, CompanyCluster, NewsItem,
)
from app.services import auth, settings_store
from app.services.scheduler import monitoring_scheduler

PASSWORD = "unaPasswordLunga1"


def wipe(db):
    for model in (NewsItem, CompanyCluster, ClusterRecipient, Cluster, Company, AppSetting):
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

    monitoring_scheduler.stop()
    db = SessionLocal()
    wipe(db)
    db.close()


@pytest.fixture
def db():
    session = SessionLocal()
    yield session
    session.close()


# --- weekly flow guide ------------------------------------------------

def test_an_empty_system_reports_every_step_as_missing(client):
    status = client.get("/api/workflow/status").json()

    assert status["ready"] is False
    assert status["missing_count"] > 0
    assert {s["key"] for s in status["steps"]} >= {
        "companies", "scheduler", "news", "clusters", "recipients", "smtp"
    }


def test_each_unfinished_step_says_what_to_do_and_where(client):
    status = client.get("/api/workflow/status").json()

    for step in status["steps"]:
        if not step["done"]:
            assert step["todo"], f"step {step['key']} has no instruction"
            assert step["link"].startswith("/")


def test_pending_news_keeps_the_flow_incomplete(client, db):
    company = Company(company_name="Aquafil S.p.A.", status="Attiva", website="https://x.it")
    db.add(company)
    db.commit()
    db.add(NewsItem(company_id=company.id, title="Notizia", url="https://x.it/1",
                    source_name="Fonte", status="New"))
    db.commit()

    news_step = next(s for s in client.get("/api/workflow/status").json()["steps"]
                     if s["key"] == "news")

    assert news_step["done"] is False
    assert news_step["count"] == 1


def test_a_company_outside_every_cluster_is_reported(client, db):
    db.add(Company(company_name="Fuori dai cluster", status="Attiva", website="https://x.it"))
    db.commit()

    step = next(s for s in client.get("/api/workflow/status").json()["steps"]
                if s["key"] == "clusters")

    assert step["done"] is False
    assert step["count"] == 1


def test_a_cluster_without_recipients_is_named(client, db):
    db.add(Cluster(cluster_name="Top clienti", cluster_type="manual",
                   frequency="weekly", active=True))
    db.commit()

    step = next(s for s in client.get("/api/workflow/status").json()["steps"]
                if s["key"] == "recipients")

    assert step["done"] is False
    assert "Top clienti" in step["detail"]


def test_the_scheduler_step_follows_the_scheduler(client):
    before = next(s for s in client.get("/api/workflow/status").json()["steps"]
                  if s["key"] == "scheduler")
    assert before["done"] is False

    client.post("/api/monitoring/start?interval_hours=24")

    after = next(s for s in client.get("/api/workflow/status").json()["steps"]
                 if s["key"] == "scheduler")
    assert after["done"] is True


# --- quick approve ----------------------------------------------------

def test_one_click_approves_every_pending_item_for_a_company(client, db):
    company = Company(company_name="Aquafil S.p.A.", status="Attiva", website="https://x.it")
    other = Company(company_name="Altra S.r.l.", status="Attiva", website="https://y.it")
    db.add_all([company, other])
    db.commit()

    for i in range(3):
        db.add(NewsItem(company_id=company.id, title=f"Notizia {i}",
                        url=f"https://x.it/{i}", source_name="Fonte", status="New"))
    db.add(NewsItem(company_id=company.id, title="Da rivedere", url="https://x.it/rev",
                    source_name="Fonte", status="Needs Review"))
    db.add(NewsItem(company_id=company.id, title="Rifiutata", url="https://x.it/no",
                    source_name="Fonte", status="Rejected"))
    db.add(NewsItem(company_id=other.id, title="Di un'altra", url="https://y.it/1",
                    source_name="Fonte", status="New"))
    db.commit()

    result = client.post(f"/api/workflow/approve-company/{company.id}").json()

    assert result["updated"] == 4  # 3 New + 1 Needs Review, not the rejected one

    db.expire_all()
    approved = db.query(NewsItem).filter_by(status="Approved").all()
    assert {n.company_id for n in approved} == {company.id}, "another company was touched"
    assert db.query(NewsItem).filter_by(status="Rejected").count() == 1


def test_quick_approve_can_skip_low_relevance_items(client, db):
    company = Company(company_name="Aquafil S.p.A.", status="Attiva", website="https://x.it")
    db.add(company)
    db.commit()
    db.add(NewsItem(company_id=company.id, title="Rilevante", url="https://x.it/1",
                    source_name="Fonte", status="New", relevance_score=8))
    db.add(NewsItem(company_id=company.id, title="Rumore", url="https://x.it/2",
                    source_name="Fonte", status="New", relevance_score=2))
    db.commit()

    result = client.post(f"/api/workflow/approve-company/{company.id}?min_relevance=5").json()

    assert result["updated"] == 1


def test_quick_approve_on_an_unknown_company_is_a_404(client):
    assert client.post("/api/workflow/approve-company/999999").status_code == 404


# --- scheduler persistence --------------------------------------------

def test_starting_the_scheduler_is_remembered(client, db):
    client.post("/api/monitoring/start?interval_hours=12")

    assert settings_store.get_setting(db, "SCHEDULER_ENABLED") is True
    assert settings_store.get_setting(db, "SCHEDULER_CHECK_INTERVAL_HOURS") == 12


def test_stopping_the_scheduler_is_remembered(client, db):
    client.post("/api/monitoring/start?interval_hours=12")
    client.post("/api/monitoring/stop")

    assert settings_store.get_setting(db, "SCHEDULER_ENABLED") is False


def test_starting_without_an_interval_reuses_the_saved_one(client):
    client.post("/api/monitoring/start?interval_hours=8")
    client.post("/api/monitoring/stop")

    result = client.post("/api/monitoring/start").json()

    assert result["interval_hours"] == 8, "it must not fall back to 24 and lose the choice"


def test_the_status_reports_when_the_next_run_is_due(client):
    client.post("/api/monitoring/start?interval_hours=24")

    status = client.get("/api/monitoring/status").json()

    assert status["is_running"] is True
    assert status["interval_hours"] == 24
    assert status["next_run_at"], "the page needs this to show when it will run"


def test_an_invalid_interval_is_refused(client):
    assert client.post("/api/monitoring/start?interval_hours=0").status_code == 400


# --- provider order over HTTP -----------------------------------------

def test_the_order_can_be_changed_and_is_reported_back(client):
    response = client.post("/api/monitoring/providers/order",
                           json={"order": ["gdelt", "rss", "google_news_rss"]})

    assert response.status_code == 200
    assert response.json()["order"][:3] == ["gdelt", "rss", "google_news_rss"]

    listed = client.get("/api/monitoring/providers").json()
    assert [p["key"] for p in listed["providers"]][:3] == ["gdelt", "rss", "google_news_rss"]
    assert listed["providers"][0]["position"] == 1


def test_an_order_with_no_valid_source_is_refused(client):
    response = client.post("/api/monitoring/providers/order",
                           json={"order": ["non_esiste"]})

    assert response.status_code == 400
