"""Automated monitoring scheduler."""

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from datetime import datetime
from typing import Dict, Any
from sqlalchemy.orm import Session
from app.database import get_db, engine
from app.models import MonitoringRun
from app.services.news_searcher import NewsSearcher


class MonitoringScheduler:
    """Handles scheduled news monitoring."""

    def __init__(self):
        self.scheduler = BackgroundScheduler()
        self.searcher = NewsSearcher()
        self.is_running = False

    def start(self, interval_hours: int = 24):
        """Start the monitoring scheduler."""
        if self.is_running:
            return

        # Schedule monitoring job
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

    def _monitoring_job(self):
        """Monitoring job executed periodically."""
        try:
            # Create a session
            from sqlalchemy.orm import sessionmaker
            Session = sessionmaker(bind=engine)
            db = Session()

            start_time = datetime.utcnow()

            # Run the monitoring
            result = self.searcher.monitor_all_companies(db)

            end_time = datetime.utcnow()

            # Save monitoring run record
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
            db.close()

            print(f"[{end_time}] Monitoring completed: {result['news_saved']} news items saved")

        except Exception as e:
            print(f"Error in monitoring job: {e}")
            try:
                db.rollback()
                db.close()
            except:
                pass

    def run_once(self) -> Dict[str, Any]:
        """Run monitoring immediately."""
        from sqlalchemy.orm import sessionmaker
        Session = sessionmaker(bind=engine)
        db = Session()

        try:
            start_time = datetime.utcnow()
            result = self.searcher.monitor_all_companies(db)
            end_time = datetime.utcnow()

            # Save monitoring run
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

            return result

        finally:
            db.close()


# Global scheduler instance
monitoring_scheduler = MonitoringScheduler()
