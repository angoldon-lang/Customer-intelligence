"""The dashboard must stay writable while a monitoring run is in progress.

A run takes many minutes (providers are throttled on purpose). Before WAL
and per-company commits, it held the SQLite write lock for its whole
duration and any dashboard write failed with "database is locked".
"""

import threading
import time

import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker

from app.models import Base, Cluster, ClusterRecipient


@pytest.fixture
def db_url(tmp_path):
    return f"sqlite:///{tmp_path}/concurrency.db"


def make_engine(db_url, wal: bool):
    """Build an engine the way app.database does (optionally without WAL)."""
    engine = create_engine(
        db_url,
        connect_args={"check_same_thread": False, "timeout": 30 if wal else 1},
    )

    @event.listens_for(engine, "connect")
    def _pragmas(dbapi_conn, record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        if wal:
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA busy_timeout=30000")
        cursor.close()

    return engine


def add_recipient(SessionFactory, email):
    """What "aggiungi destinatario" does from the dashboard."""
    session = SessionFactory()
    try:
        cluster = session.query(Cluster).first()
        session.add(ClusterRecipient(cluster_id=cluster.id, email=email, active=True))
        session.commit()
    finally:
        session.close()


def test_dashboard_write_succeeds_during_a_slow_run(db_url):
    """The real scenario: saving a recipient while a run is writing."""
    engine = make_engine(db_url, wal=True)
    Base.metadata.create_all(engine)
    SessionFactory = sessionmaker(bind=engine)

    setup = SessionFactory()
    setup.add(Cluster(cluster_name="Top clienti", cluster_type="manual",
                      frequency="daily", active=True))
    setup.commit()
    setup.close()

    run_started = threading.Event()
    run_errors = []

    def slow_monitoring_run():
        """Writes per company with a pause between them, like a real run."""
        session = SessionFactory()
        try:
            for i in range(6):
                session.add(Cluster(cluster_name=f"Auto {i}", cluster_type="auto",
                                    frequency="weekly", active=True))
                session.commit()  # per-company commit releases the lock
                run_started.set()
                time.sleep(0.05)  # provider throttling / Claude call
        except Exception as e:  # pragma: no cover - failure path
            run_errors.append(e)
        finally:
            session.close()

    runner = threading.Thread(target=slow_monitoring_run)
    runner.start()
    assert run_started.wait(timeout=5), "the background run never started"

    # Mid-run, exactly what failed before.
    add_recipient(SessionFactory, "andrea.goldoni@example.com")

    runner.join(timeout=10)
    assert not run_errors

    check = SessionFactory()
    assert check.query(ClusterRecipient).count() == 1
    check.close()


def test_a_run_that_never_commits_is_what_locks_the_database(db_url):
    """Characterises the old behaviour, so the fix can't silently regress.

    Holding one uncommitted write transaction open - a run that commits
    only at the end - blocks every other writer regardless of WAL.
    """
    engine = make_engine(db_url, wal=True)
    Base.metadata.create_all(engine)
    SessionFactory = sessionmaker(bind=engine)

    setup = SessionFactory()
    setup.add(Cluster(cluster_name="Top clienti", cluster_type="manual",
                      frequency="daily", active=True))
    setup.commit()
    setup.close()

    hog = engine.connect()
    hog.execute(text("BEGIN IMMEDIATE"))
    hog.execute(text(
        "INSERT INTO clusters (cluster_name, cluster_type, frequency, active) "
        "VALUES ('Run in corso', 'auto', 'weekly', 1)"
    ))

    blocked = make_engine(db_url, wal=False)  # 1s timeout, fails fast
    BlockedSession = sessionmaker(bind=blocked)
    with pytest.raises(Exception) as exc:
        add_recipient(BlockedSession, "andrea.goldoni@example.com")
    assert "locked" in str(exc.value).lower()

    hog.rollback()
    hog.close()

    # Once the long transaction ends, the same write goes through.
    add_recipient(SessionFactory, "andrea.goldoni@example.com")
    check = SessionFactory()
    assert check.query(ClusterRecipient).count() == 1
    check.close()
