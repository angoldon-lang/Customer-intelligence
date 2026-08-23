"""Automated monitoring scheduler with cluster-tiered frequency."""

import threading
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from datetime import datetime
from typing import Dict, Any, List
from sqlalchemy.orm import Session
from app.database import engine
from app.config import settings
from app.models import MonitoringRun, Company, Cluster, CompanyCluster
from app.services.news_searcher import NewsSearcher

# How often each cluster frequency tier requires a re-check.
FREQUENCY_HOURS = {
    "daily": 24,
    "2-3x_week": 60,
    "weekly": 168,
    "monthly": 720,
}
DEFAULT_FREQUENCY_HOURS = 168  # weekly, for companies with no active cluster


def get_due_companies(db: Session, limit: int = None) -> List[Company]:
    """
    Return active companies due for a news check, most-overdue first.

    A company's check interval is the shortest (most frequent) tier among
    the active clusters it belongs to (e.g. a top-client cluster set to
    "daily" wins over a "weekly" sector cluster for the same company).
    Companies in no active cluster default to weekly.
    """
    rows = (
        db.query(CompanyCluster.company_id, Cluster.frequency)
        .join(Cluster, Cluster.id == CompanyCluster.cluster_id)
        .filter(Cluster.active == True)
        .all()
    )

    interval_by_company = {}
    for company_id, frequency in rows:
        hours = FREQUENCY_HOURS.get(frequency, DEFAULT_FREQUENCY_HOURS)
        if company_id not in interval_by_company or hours < interval_by_company[company_id]:
            interval_by_company[company_id] = hours

    companies = db.query(Company).filter_by(status="Attiva").all()
    now = datetime.utcnow()
    due = []

    for company in companies:
        interval_hours = interval_by_company.get(company.id, DEFAULT_FREQUENCY_HOURS)
        if company.last_monitored_at is None:
            due.append((company, datetime.min))
            continue
        elapsed_hours = (now - company.last_monitored_at).total_seconds() / 3600
        if elapsed_hours >= interval_hours:
            due.append((company, company.last_monitored_at))

    due.sort(key=lambda pair: pair[1])
    companies_due = [c for c, _ in due]

    if limit:
        companies_due = companies_due[:limit]

    return companies_due


class MonitoringScheduler:
    """Handles scheduled news monitoring."""

    def __init__(self):
        self.scheduler = BackgroundScheduler()
        self.searcher = NewsSearcher()
        self.is_running = False
        self.run_in_progress = False
        self.last_classification_issue = None
        self._run_lock = threading.Lock()

    def start(self, interval_hours: int = 24):
        """Start the monitoring scheduler."""
        if self.is_running:
            return

        self.scheduler.add_job(
            self._monitoring_job,
            trigger=IntervalTrigger(hours=interval_hours),
            id='news_monitoring',
            name='News Monitoring',
            replace_existing=True
        )

        self.scheduler.start()
        self.is_running = True
        print(f"Monitoring scheduler started (interval: {interval_hours}h)")

    def stop(self):
        """Stop the monitoring scheduler."""
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)
            self.is_running = False
            print("Monitoring scheduler stopped")

    def _run(self, db: Session, limit: int = None) -> Dict[str, Any]:
        start_time = datetime.utcnow()

        due_companies = get_due_companies(db, limit=limit or settings.MAX_COMPANIES_PER_RUN)
        result = self.searcher.monitor_all_companies(db, companies=due_companies)

        end_time = datetime.utcnow()

        monitoring_run = MonitoringRun(
            started_at=start_time,
            finished_at=end_time,
            companies_processed=result['companies_checked'],
            news_found=result['news_found'],
            status='Completed',
            errors_count=len(result['errors']) if result['errors'] else 0,
        )
        db.add(monitoring_run)
        db.commit()

        self.last_classification_issue = result.get("classification_disabled_reason")

        print(
            f"[{end_time}] Monitoring completed: {result['companies_checked']} companies checked, "
            f"{result['news_saved']} news items saved, "
            f"{result['companies_needing_enrichment']} skipped (need enrichment)"
        )
        if self.last_classification_issue:
            print(
                f"  -> {result.get('news_unclassified', 0)} notizie salvate SENZA classificazione AI "
                f"({self.last_classification_issue}). Risolvi e usa Riclassifica dalla pagina Notizie."
            )

        return result

    def _monitoring_job(self, limit: int = None):
        """Monitoring job executed periodically (runs on APScheduler's own thread)."""
        if not self._run_lock.acquire(blocking=False):
            print("Monitoring job skipped: a run is already in progress")
            return

        from sqlalchemy.orm import sessionmaker
        SessionFactory = sessionmaker(bind=engine)
        db = SessionFactory()

        self.run_in_progress = True
        try:
            self._run(db, limit=limit)
        except Exception as e:
            print(f"Error in monitoring job: {e}")
            db.rollback()
        finally:
            db.close()
            self.run_in_progress = False
            self._run_lock.release()

    def run_once(self, limit: int = None) -> Dict[str, Any]:
        """
        Run monitoring immediately, synchronously, and return the result.

        Can take a long time on a large company list (GDELT/GNews are
        rate-limited client-side). Prefer run_now_async() from an HTTP
        request so a client disconnect (e.g. Ctrl+C on the server) doesn't
        leave the run orphaned mid-request with no way to observe it.
        """
        with self._run_lock:
            from sqlalchemy.orm import sessionmaker
            SessionFactory = sessionmaker(bind=engine)
            db = SessionFactory()

            self.run_in_progress = True
            try:
                return self._run(db, limit=limit)
            finally:
                db.close()
                self.run_in_progress = False

    def run_now_async(self, limit: int = None) -> bool:
        """
        Start a monitoring run on a background thread and return immediately.

        `limit` overrides MAX_COMPANIES_PER_RUN for this run only - handy to
        test on a handful of companies without editing .env and restarting.

        Returns False (without starting anything) if a run is already in
        progress. The caller should poll get_monitoring_status()/history
        for progress and results instead of waiting on this call.
        """
        if self.run_in_progress:
            return False

        thread = threading.Thread(target=self._monitoring_job, args=(limit,), daemon=True)
        thread.start()
        return True


# Global scheduler instance
monitoring_scheduler = MonitoringScheduler()
