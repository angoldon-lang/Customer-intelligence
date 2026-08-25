"""Tests for bulk company actions, and for what "Pausa" actually means.

The status is not a label: only "Attiva" companies are searched. That
guarantee is what makes pausing a batch a real off switch, so it is pinned
down here.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.main import app
from app.database import SessionLocal
from app.models import (
    Base, AppSetting, Company, Cluster, CompanyCluster, ClusterRecipient, NewsItem,
)
from app.services import auth
from app.services.scheduler import get_due_companies

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

    db = SessionLocal()
    wipe(db)
    db.close()


@pytest.fixture
def db():
    session = SessionLocal()
    yield session
    session.close()


def seed(db, count=3, status="Attiva"):
    companies = [
        Company(company_name=f"Azienda {i}", status=status, website=f"https://a{i}.it")
        for i in range(count)
    ]
    db.add_all(companies)
    db.commit()
    return [c.id for c in companies]


# --- what "Pausa" means -----------------------------------------------

def test_only_active_companies_are_monitored():
    """The guarantee behind the pause switch."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()

    for name, status in [
        ("Attiva SpA", "Attiva"), ("In Pausa Srl", "Pausa"),
        ("Archiviata Snc", "Archiviata"), ("Da Verificare", "Needs Review"),
    ]:
        session.add(Company(company_name=name, status=status, website="https://x.it"))
    session.commit()

    due = {c.company_name for c in get_due_companies(session)}

    assert due == {"Attiva SpA"}
    session.close()


def test_pausing_removes_a_company_from_the_next_run(client, db):
    ids = seed(db, 3)
    assert len(get_due_companies(db)) == 3

    client.post("/api/companies/bulk-status", json={"ids": ids[:2], "status": "Pausa"})

    db.expire_all()
    assert [c.company_name for c in get_due_companies(db)] == ["Azienda 2"]


def test_reactivating_puts_it_back(client, db):
    ids = seed(db, 2, status="Pausa")
    assert get_due_companies(db) == []

    client.post("/api/companies/bulk-status", json={"ids": ids, "status": "Attiva"})

    db.expire_all()
    assert len(get_due_companies(db)) == 2


# --- bulk status ------------------------------------------------------

def test_bulk_status_changes_only_the_selected(client, db):
    ids = seed(db, 4)

    response = client.post("/api/companies/bulk-status",
                           json={"ids": ids[:2], "status": "Pausa"})

    assert response.json()["updated"] == 2
    db.expire_all()
    paused = {c.company_name for c in db.query(Company).filter_by(status="Pausa")}
    assert paused == {"Azienda 0", "Azienda 1"}


def test_the_message_says_whether_they_are_still_monitored(client, db):
    ids = seed(db, 1)

    paused = client.post("/api/companies/bulk-status",
                         json={"ids": ids, "status": "Pausa"}).json()
    active = client.post("/api/companies/bulk-status",
                         json={"ids": ids, "status": "Attiva"}).json()

    assert "non verranno" in paused["message"]
    assert "rientrano" in active["message"]


def test_an_invalid_status_is_refused(client, db):
    ids = seed(db, 1)

    response = client.post("/api/companies/bulk-status",
                           json={"ids": ids, "status": "Inventato"})

    assert response.status_code == 400
    db.expire_all()
    assert db.query(Company).first().status == "Attiva"


def test_an_empty_selection_is_refused(client):
    assert client.post("/api/companies/bulk-status",
                       json={"ids": [], "status": "Pausa"}).status_code == 400


# --- bulk cluster -----------------------------------------------------

def test_companies_can_be_added_to_a_cluster_in_bulk(client, db):
    ids = seed(db, 3)
    cluster = Cluster(cluster_name="Top clienti", cluster_type="manual",
                      frequency="weekly", active=True)
    db.add(cluster)
    db.commit()

    result = client.post("/api/companies/bulk-cluster",
                         json={"ids": ids, "cluster_id": cluster.id}).json()

    assert result["added"] == 3
    assert db.query(CompanyCluster).filter_by(cluster_id=cluster.id).count() == 3


def test_adding_twice_does_not_duplicate(client, db):
    ids = seed(db, 2)
    cluster = Cluster(cluster_name="Top clienti", cluster_type="manual",
                      frequency="weekly", active=True)
    db.add(cluster)
    db.commit()

    client.post("/api/companies/bulk-cluster", json={"ids": ids, "cluster_id": cluster.id})
    second = client.post("/api/companies/bulk-cluster",
                         json={"ids": ids, "cluster_id": cluster.id}).json()

    assert second["added"] == 0
    assert second["skipped"] == 2
    assert db.query(CompanyCluster).count() == 2


def test_an_unknown_cluster_is_a_404(client, db):
    ids = seed(db, 1)

    assert client.post("/api/companies/bulk-cluster",
                       json={"ids": ids, "cluster_id": 999999}).status_code == 404


# --- bulk delete ------------------------------------------------------

def test_bulk_delete_removes_companies_and_their_news(client, db):
    ids = seed(db, 3)
    db.add(NewsItem(company_id=ids[0], title="Notizia", url="https://x.it/1",
                    source_name="Fonte", status="New"))
    db.commit()

    result = client.post("/api/companies/bulk-delete", json={"ids": ids[:2]}).json()

    assert result["deleted"] == 2
    assert db.query(Company).count() == 1
    assert db.query(NewsItem).count() == 0, "news of a deleted company must go too"


def test_bulk_delete_leaves_no_orphan_cluster_links(client, db):
    ids = seed(db, 2)
    cluster = Cluster(cluster_name="Top clienti", cluster_type="manual",
                      frequency="weekly", active=True)
    db.add(cluster)
    db.commit()
    client.post("/api/companies/bulk-cluster", json={"ids": ids, "cluster_id": cluster.id})

    client.post("/api/companies/bulk-delete", json={"ids": ids})

    assert db.query(CompanyCluster).count() == 0


def test_bulk_delete_needs_a_selection(client):
    assert client.post("/api/companies/bulk-delete", json={"ids": []}).status_code == 400
