"""Tests for the per-cluster report delivery schedule."""

from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models import Base, Cluster, Report
from app.services.report_scheduler import (
    FREQUENCY_DAYS,
    DEFAULT_FREQUENCY_DAYS,
    cluster_is_due,
)


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


def make_cluster(db, frequency="weekly"):
    cluster = Cluster(cluster_name="Top clienti", cluster_type="manual",
                      frequency=frequency, active=True)
    db.add(cluster)
    db.commit()
    return cluster


def add_sent_report(db, cluster, sent_at):
    report = Report(
        cluster_id=cluster.id,
        subject="Report",
        period_start=sent_at - timedelta(days=7),
        period_end=sent_at,
        status="Sent",
        sent_at=sent_at,
    )
    db.add(report)
    db.commit()
    return report


def test_cluster_never_sent_is_due(db):
    cluster = make_cluster(db)

    assert cluster_is_due(db, cluster) is True


def test_cluster_sent_within_interval_is_not_due(db):
    cluster = make_cluster(db, frequency="weekly")
    now = datetime.utcnow()
    add_sent_report(db, cluster, now - timedelta(days=2))

    assert cluster_is_due(db, cluster, now) is False


def test_cluster_sent_before_interval_is_due_again(db):
    cluster = make_cluster(db, frequency="weekly")
    now = datetime.utcnow()
    add_sent_report(db, cluster, now - timedelta(days=8))

    assert cluster_is_due(db, cluster, now) is True


def test_daily_cluster_is_due_after_one_day(db):
    cluster = make_cluster(db, frequency="daily")
    now = datetime.utcnow()
    add_sent_report(db, cluster, now - timedelta(days=1, hours=1))

    assert cluster_is_due(db, cluster, now) is True


def test_monthly_cluster_is_not_due_after_a_week(db):
    cluster = make_cluster(db, frequency="monthly")
    now = datetime.utcnow()
    add_sent_report(db, cluster, now - timedelta(days=7))

    assert cluster_is_due(db, cluster, now) is False


def test_unknown_frequency_falls_back_to_the_default_interval(db):
    cluster = make_cluster(db, frequency="quando_capita")
    now = datetime.utcnow()
    add_sent_report(db, cluster, now - timedelta(days=DEFAULT_FREQUENCY_DAYS - 1))

    assert cluster_is_due(db, cluster, now) is False


def test_draft_reports_do_not_count_as_sent(db):
    """Only a report actually delivered resets the cluster's clock."""
    cluster = make_cluster(db, frequency="weekly")
    now = datetime.utcnow()
    db.add(Report(
        cluster_id=cluster.id,
        subject="Report",
        period_start=now - timedelta(days=7),
        period_end=now,
        status="Draft",
    ))
    db.commit()

    assert cluster_is_due(db, cluster, now) is True


def test_every_monitoring_tier_has_a_report_interval(db):
    from app.services.scheduler import FREQUENCY_HOURS

    assert set(FREQUENCY_DAYS) == set(FREQUENCY_HOURS)
