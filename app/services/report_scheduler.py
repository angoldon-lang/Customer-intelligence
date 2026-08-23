"""Automatic report generation and delivery, per cluster frequency."""

from datetime import datetime, timedelta
from typing import Dict, Any
from sqlalchemy.orm import Session
from app.models import Cluster, Report
from app.services.reporter import ReportGenerator
from app.services.email_sender import EmailSender

# How often each cluster frequency expects a report, and how far back the
# report should look. Mirrors the monitoring tiers in scheduler.py.
FREQUENCY_DAYS = {
    "daily": 1,
    "2-3x_week": 3,
    "weekly": 7,
    "monthly": 30,
}
DEFAULT_FREQUENCY_DAYS = 7


def cluster_is_due(db: Session, cluster: Cluster, now: datetime = None) -> bool:
    """True if this cluster hasn't had a report sent within its interval."""
    now = now or datetime.utcnow()
    interval = timedelta(days=FREQUENCY_DAYS.get(cluster.frequency, DEFAULT_FREQUENCY_DAYS))

    last_sent = (
        db.query(Report)
        .filter(Report.cluster_id == cluster.id, Report.status == "Sent")
        .order_by(Report.sent_at.desc())
        .first()
    )
    if not last_sent or not last_sent.sent_at:
        return True
    return (now - last_sent.sent_at) >= interval


def send_due_reports(db: Session, force: bool = False) -> Dict[str, Any]:
    """
    Generate and email a report for every active cluster that is due.

    Clusters with no recipients are skipped rather than generating a report
    nobody receives. `force` ignores the schedule (used by "invia ora").
    """
    result = {"sent": 0, "skipped_no_recipients": 0, "skipped_not_due": 0,
              "skipped_no_news": 0, "errors": []}

    clusters = db.query(Cluster).filter_by(active=True).all()
    generator = ReportGenerator()
    sender = EmailSender(db)
    now = datetime.utcnow()

    for cluster in clusters:
        try:
            recipients = [r.email for r in cluster.recipients if r.email and r.active]
            if not recipients:
                result["skipped_no_recipients"] += 1
                continue

            if not force and not cluster_is_due(db, cluster, now):
                result["skipped_not_due"] += 1
                continue

            days = FREQUENCY_DAYS.get(cluster.frequency, DEFAULT_FREQUENCY_DAYS)
            report = generator.generate_cluster_report(
                db, cluster, now - timedelta(days=days), now
            )

            # Don't email an empty digest - and don't keep it either: the
            # daily job would otherwise pile up an empty Draft per cluster
            # per day in the reports list.
            if report.body_html and "Nessuna notizia rilevante" in report.body_html:
                db.delete(report)
                db.commit()
                result["skipped_no_news"] += 1
                continue

            outcome = sender.send_report(
                to_emails=recipients,
                subject=report.subject,
                html_content=report.body_html or "<p>Report</p>",
                text_content=report.body_text or "Report",
            )

            if outcome.get("success"):
                report.status = "Sent"
                report.sent_at = datetime.utcnow()
                db.commit()
                result["sent"] += 1
                print(f"[Report] Inviato '{cluster.cluster_name}' a {len(recipients)} destinatari")
            else:
                report.status = "Failed"
                db.commit()
                result["errors"].append(f"{cluster.cluster_name}: {outcome.get('error')}")

        except Exception as e:
            db.rollback()
            result["errors"].append(f"{cluster.cluster_name}: {e}")

    return result
