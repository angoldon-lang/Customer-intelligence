"""FastAPI application entry point."""

from fastapi import FastAPI, UploadFile, File, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from datetime import datetime, timedelta
import os

from app import __version__
from app.config import settings
from app.database import init_db, get_db
from app.models import Company, Cluster, NewsItem, Report, MonitoringRun, NewsSource, CompanyCluster, ClusterRecipient
from app.services import DataImporter, DataNormalizer, ClusterManager
from app.services.classifier import NewsClassifier
from app.services.reporter import ReportGenerator
from app.services.news_searcher import NewsSearcher
from app.services.scheduler import monitoring_scheduler
from app.services.email_sender import EmailSender
from app.providers import MockNewsProvider

# Initialize database tables
init_db()

app = FastAPI(
    title="Customer Intelligence Monitor",
    description="Monitor news and intelligence about companies",
    version=__version__,
)


@app.on_event("shutdown")
def on_shutdown():
    """Stop background jobs so the process can exit cleanly on Ctrl+C."""
    monitoring_scheduler.stop()

# Setup templates
templates = Jinja2Templates(directory="app/templates")

# Mount static files if they exist
if os.path.exists("app/static"):
    app.mount("/static", StaticFiles(directory="app/static"), name="static")

# starlette changed Jinja2Templates.TemplateResponse's signature from
# (name, context) to (request, name, context) between versions. Calling it
# the old way on a newer starlette silently misassigns arguments (the
# context dict lands where `name` is expected), which surfaces deep inside
# Jinja2 as a baffling "TypeError: unhashable type: 'dict'". Detect which
# signature is installed once, so page routes work either way.
import inspect as _inspect
_template_response_params = list(_inspect.signature(templates.TemplateResponse).parameters)
_REQUEST_FIRST = bool(_template_response_params) and _template_response_params[0] == "request"


def render(request: Request, name: str, context: dict = None) -> HTMLResponse:
    """Render a Jinja2 template, compatible with old and new starlette."""
    context = dict(context or {})
    if _REQUEST_FIRST:
        return templates.TemplateResponse(request, name, context)
    context["request"] = request
    return templates.TemplateResponse(name, context)


# ============================================================================
# Page Routes - HTML Templates
# ============================================================================

@app.get("/", response_class=HTMLResponse)
def read_root(request: Request):
    """Root endpoint - dashboard."""
    return render(request, "index.html")


@app.get("/api/health")
def health_check(db: Session = Depends(get_db)):
    """Health check endpoint."""
    return {
        "status": "ok",
        "database": True,
        "api": bool(settings.CLAUDE_API_KEY),
        "version": __version__,
    }


@app.post("/api/import")
async def import_data(file: UploadFile = File(...), db: Session = Depends(get_db)):
    """Import company data from Excel or CSV file."""
    importer = DataImporter()

    try:
        content = await file.read()
        result = importer.import_file(content, file.filename)

        # Save companies to database
        added_count = 0
        duplicate_count = 0
        error_companies = []

        for company_data in result["companies"]:
            try:
                existing = db.query(Company).filter_by(company_name=company_data["company_name"]).first()
                if not existing:
                    company = Company(**company_data)
                    db.add(company)
                    db.flush()
                    added_count += 1
                else:
                    duplicate_count += 1
            except IntegrityError:
                db.rollback()
                duplicate_count += 1
                error_companies.append(company_data["company_name"])

        db.commit()

        result["added_to_database"] = added_count
        result["duplicate_companies"] = duplicate_count
        if error_companies:
            result["skipped_duplicates"] = error_companies
        return result

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/companies")
def list_companies(db: Session = Depends(get_db)):
    """List all companies."""
    companies = db.query(Company).all()
    return {
        "total": len(companies),
        "companies": [
            {
                "id": c.id,
                "company_name": c.company_name,
                "relationship_type": c.relationship_type,
                "status": c.status,
                "website": c.website,
                "account_owner": c.account_owner,
            }
            for c in companies
        ]
    }


@app.get("/api/clusters")
def list_clusters(db: Session = Depends(get_db)):
    """List all clusters."""
    clusters = db.query(Cluster).all()
    return {
        "total": len(clusters),
        "clusters": [
            {
                "id": c.id,
                "cluster_name": c.cluster_name,
                "cluster_type": c.cluster_type,
                "frequency": c.frequency,
                "active": c.active,
                "company_count": len(c.companies),
            }
            for c in clusters
        ]
    }


@app.post("/api/clusters")
def create_cluster(
    cluster_name: str,
    cluster_type: str = "manual",
    frequency: str = "weekly",
    db: Session = Depends(get_db)
):
    """Create new cluster."""
    manager = ClusterManager()
    cluster = manager.create_cluster(
        db,
        cluster_name=cluster_name,
        cluster_type=cluster_type,
        frequency=frequency,
    )
    return {
        "id": cluster.id,
        "cluster_name": cluster.cluster_name,
        "message": "Cluster created successfully"
    }


@app.post("/api/auto-clusters")
def auto_create_clusters(db: Session = Depends(get_db)):
    """Auto-create clusters from company attributes."""
    manager = ClusterManager()
    companies = db.query(Company).all()
    created = manager.create_auto_clusters(db, companies)
    return {
        "created": len(created),
        "message": f"Created {len(created)} clusters"
    }


@app.post("/api/clusters/{cluster_id}/recipients")
def add_cluster_recipient(
    cluster_id: int,
    email: str,
    name: str = None,
    db: Session = Depends(get_db)
):
    """Add recipient to cluster."""
    manager = ClusterManager()
    recipient = manager.add_recipient(db, cluster_id, email, name)
    return {
        "id": recipient.id,
        "email": recipient.email,
        "message": "Recipient added successfully"
    }


@app.get("/api/news")
def list_news(
    status: str = None,
    category: str = None,
    limit: int = 50,
    db: Session = Depends(get_db)
):
    """List news items with optional filters."""
    query = db.query(NewsItem)

    if status:
        query = query.filter_by(status=status)
    if category:
        query = query.filter_by(category=category)

    news = query.order_by(NewsItem.created_at.desc()).limit(limit).all()

    return {
        "total": len(news),
        "news": [
            {
                "id": n.id,
                "title": n.title,
                "company_name": n.company.company_name,
                "category": n.category,
                "relevance_score": n.relevance_score,
                "status": n.status,
                "source_name": n.source_name,
            }
            for n in news
        ]
    }


@app.get("/api/reports")
def list_reports(
    status: str = None,
    limit: int = 50,
    db: Session = Depends(get_db)
):
    """List generated reports."""
    query = db.query(Report)

    if status:
        query = query.filter_by(status=status)

    reports = query.order_by(Report.created_at.desc()).limit(limit).all()

    return {
        "total": len(reports),
        "reports": [
            {
                "id": r.id,
                "cluster_name": r.cluster.cluster_name,
                "period_start": r.period_start.isoformat(),
                "period_end": r.period_end.isoformat(),
                "status": r.status,
                "subject": r.subject,
            }
            for r in reports
        ]
    }


# ============================================================================
# Phase 2 - News Monitoring
# ============================================================================

@app.post("/api/monitoring/start")
def start_monitoring(
    interval_hours: int = 24,
    db: Session = Depends(get_db)
):
    """Start automatic news monitoring."""
    monitoring_scheduler.start(interval_hours)
    return {
        "status": "started",
        "interval_hours": interval_hours,
        "message": "News monitoring started"
    }


@app.post("/api/monitoring/stop")
def stop_monitoring():
    """Stop automatic news monitoring."""
    monitoring_scheduler.stop()
    return {
        "status": "stopped",
        "message": "News monitoring stopped"
    }


@app.post("/api/monitoring/run-now")
def run_monitoring_now(limit: int = None):
    """
    Start a monitoring run in the background and return immediately.

    A run can take minutes on a large company list (GDELT/GNews are
    rate-limited client-side), so this no longer blocks the HTTP request -
    poll GET /api/monitoring/status for progress and results.

    `limit` restricts this run to at most N due companies (overrides
    MAX_COMPANIES_PER_RUN for this run only) - useful to quickly test on a
    handful of companies instead of waiting on the full list.
    """
    started = monitoring_scheduler.run_now_async(limit=limit)
    if not started:
        raise HTTPException(status_code=409, detail="A monitoring run is already in progress")
    return {"status": "started", "message": "Monitoring run started in background"}


@app.get("/api/monitoring/status")
def get_monitoring_status(db: Session = Depends(get_db)):
    """Get monitoring status."""
    last_run = db.query(MonitoringRun).order_by(MonitoringRun.finished_at.desc()).first()

    return {
        "is_running": monitoring_scheduler.is_running,
        "run_in_progress": monitoring_scheduler.run_in_progress,
        "last_run": {
            "finished_at": last_run.finished_at.isoformat() if last_run else None,
            "companies_checked": last_run.companies_processed if last_run else 0,
            "news_found": last_run.news_found if last_run else 0,
            "news_saved": last_run.news_found if last_run else 0,
            "status": last_run.status if last_run else "Never run",
        } if last_run else {}
    }


@app.get("/api/monitoring/history")
def get_monitoring_history(limit: int = 10, db: Session = Depends(get_db)):
    """Get monitoring run history."""
    runs = db.query(MonitoringRun).order_by(MonitoringRun.finished_at.desc()).limit(limit).all()

    return {
        "total": len(runs),
        "runs": [
            {
                "finished_at": r.finished_at.isoformat() if r.finished_at else None,
                "companies_checked": r.companies_processed,
                "news_found": r.news_found,
                "news_saved": r.news_found,
                "status": r.status,
            }
            for r in runs
        ]
    }


@app.get("/api/monitoring/providers")
def get_providers_status(db: Session = Depends(get_db)):
    """Report which news providers are active, for the settings page."""
    rss_count = db.query(NewsSource).filter_by(source_type="rss", enabled=True).count()
    return {
        "google_news_rss": {"enabled": settings.GOOGLE_NEWS_RSS_ENABLED, "requires_key": False},
        "gdelt": {"enabled": settings.GDELT_ENABLED, "requires_key": False},
        "gnews": {"enabled": bool(settings.GNEWS_API_KEY), "requires_key": True},
        "rss": {"enabled": settings.RSS_ENABLED and rss_count > 0, "active_feeds": rss_count},
    }


@app.get("/api/news-sources")
def list_news_sources(db: Session = Depends(get_db)):
    """List configured news sources (RSS/official feeds)."""
    sources = db.query(NewsSource).order_by(NewsSource.priority).all()
    return {
        "total": len(sources),
        "sources": [
            {
                "id": s.id,
                "source_name": s.source_name,
                "source_type": s.source_type,
                "base_url": s.base_url,
                "enabled": s.enabled,
                "priority": s.priority,
                "license_scope": s.license_scope,
            }
            for s in sources
        ]
    }


@app.post("/api/news-sources")
def create_news_source(
    source_name: str,
    base_url: str,
    source_type: str = "rss",
    priority: int = 100,
    license_scope: str = "summary_allowed",
    db: Session = Depends(get_db)
):
    """Add a news source (typically an official company/IR RSS feed)."""
    existing = db.query(NewsSource).filter_by(source_name=source_name).first()
    if existing:
        raise HTTPException(status_code=400, detail="A source with this name already exists")

    source = NewsSource(
        source_name=source_name,
        source_type=source_type,
        base_url=base_url,
        enabled=True,
        priority=priority,
        license_scope=license_scope,
    )
    db.add(source)
    db.commit()
    db.refresh(source)
    return {"id": source.id, "source_name": source.source_name, "message": "Source added successfully"}


@app.post("/api/news-sources/{source_id}/toggle")
def toggle_news_source(source_id: int, db: Session = Depends(get_db)):
    """Enable/disable a news source."""
    source = db.query(NewsSource).filter_by(id=source_id).first()
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")
    source.enabled = not source.enabled
    db.commit()
    return {"id": source.id, "enabled": source.enabled}


@app.delete("/api/news-sources/{source_id}")
def delete_news_source(source_id: int, db: Session = Depends(get_db)):
    """Remove a news source."""
    source = db.query(NewsSource).filter_by(id=source_id).first()
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")
    db.delete(source)
    db.commit()
    return {"message": "Source deleted"}


# ============================================================================
# Admin / Maintenance
# ============================================================================

@app.post("/api/admin/cleanup")
def cleanup_database(days: int = 180, db: Session = Depends(get_db)):
    """
    Remove stale news items and old monitoring run history.

    News items with status Approved or Sent are kept regardless of age
    (they're curated/already used in a report); everything else older than
    `days` is removed. Old monitoring run log entries beyond the same
    window are removed too, since they're just diagnostic history.
    """
    cutoff = datetime.utcnow() - timedelta(days=days)

    deleted_news = (
        db.query(NewsItem)
        .filter(NewsItem.created_at < cutoff, NewsItem.status.notin_(["Approved", "Sent"]))
        .delete(synchronize_session=False)
    )
    deleted_runs = (
        db.query(MonitoringRun)
        .filter(MonitoringRun.started_at < cutoff)
        .delete(synchronize_session=False)
    )
    db.commit()

    return {
        "message": "Cleanup completed",
        "deleted_news_items": deleted_news,
        "deleted_monitoring_runs": deleted_runs,
        "cutoff_days": days,
    }


@app.post("/api/admin/reset")
def reset_system(confirm: str = "", db: Session = Depends(get_db)):
    """
    Wipe ALL data (companies, clusters, news, reports, sources, run history)
    while keeping the schema intact. Irreversible - requires confirm=RESET.
    """
    if confirm != "RESET":
        raise HTTPException(status_code=400, detail="Pass confirm=RESET to actually wipe all data")

    # Children before parents, to satisfy SQLite's foreign key constraints.
    for model in [NewsItem, CompanyCluster, ClusterRecipient, Report, MonitoringRun, NewsSource, Cluster, Company]:
        db.query(model).delete(synchronize_session=False)
    db.commit()

    return {"message": "All data has been reset"}


# ============================================================================
# Phase 3 - Email Sending
# ============================================================================

@app.post("/api/reports/{report_id}/send")
def send_report(
    report_id: int,
    db: Session = Depends(get_db)
):
    """Send report to recipients."""
    report = db.query(Report).filter_by(id=report_id).first()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    # Get cluster recipients
    recipients = [r.email for r in report.cluster.recipients if r.email]
    if not recipients:
        raise HTTPException(status_code=400, detail="No recipients configured for this cluster")

    # Send email
    sender = EmailSender()
    result = sender.send_report(
        to_emails=recipients,
        subject=report.subject,
        html_content=report.html_content or "<p>Report content</p>",
        text_content=report.text_content or "Report content"
    )

    if result['success']:
        report.status = 'Sent'
        report.sent_at = datetime.utcnow()
        db.commit()

        return {
            "status": "sent",
            "recipients": len(recipients),
            "message": f"Report sent to {len(recipients)} recipients"
        }
    else:
        raise HTTPException(status_code=400, detail=result['error'])


@app.post("/api/email/test-smtp")
def test_smtp_connection():
    """Test SMTP connection."""
    sender = EmailSender()
    result = sender.test_connection()

    return result


@app.post("/api/email/send-alert")
def send_alert_email(
    news_id: int,
    recipient_email: str,
    db: Session = Depends(get_db)
):
    """Send urgent alert email for critical news."""
    news = db.query(NewsItem).filter_by(id=news_id).first()
    if not news:
        raise HTTPException(status_code=404, detail="News not found")

    sender = EmailSender()
    result = sender.send_alert(
        to_email=recipient_email,
        company_name=news.company.company_name,
        news_title=news.title,
        risk_score=news.risk_score
    )

    if result['success']:
        return {"status": "sent", "message": "Alert sent successfully"}
    else:
        raise HTTPException(status_code=400, detail=result['error'])


@app.post("/api/reports/generate")
def generate_report(
    cluster_id: int,
    days_back: int = 7,
    db: Session = Depends(get_db)
):
    """Generate report for cluster."""
    cluster = db.query(Cluster).filter_by(id=cluster_id).first()
    if not cluster:
        raise HTTPException(status_code=404, detail="Cluster not found")

    period_end = datetime.utcnow()
    period_start = period_end - timedelta(days=days_back)

    generator = ReportGenerator()
    report = generator.generate_cluster_report(db, cluster, period_start, period_end)

    return {
        "id": report.id,
        "cluster_name": cluster.cluster_name,
        "status": report.status,
        "message": "Report generated successfully"
    }


@app.get("/upload", response_class=HTMLResponse)
def upload_page(request: Request):
    """Upload page."""
    return render(request, "upload.html")


@app.get("/companies", response_class=HTMLResponse)
def companies_page(request: Request):
    """Companies management page."""
    return render(request, "companies.html")


@app.get("/clusters", response_class=HTMLResponse)
def clusters_page(request: Request):
    """Clusters configuration page."""
    return render(request, "clusters.html")


@app.get("/news", response_class=HTMLResponse)
def news_page(request: Request):
    """News management page."""
    return render(request, "news.html")


@app.get("/reports", response_class=HTMLResponse)
def reports_page(request: Request):
    """Reports management page."""
    return render(request, "reports.html")


@app.get("/settings", response_class=HTMLResponse)
def settings_page(request: Request):
    """Settings page."""
    return render(request, "settings.html")


# /monitoring stays disabled: not a bug (the "unhashable dict" issue that
# originally broke it was a starlette API mismatch in render(), now fixed
# above for every page) - its controls were simply moved into Impostazioni
# (/settings) to avoid a duplicate UI. app/templates/monitoring.html is
# unused but left in place in case it's wanted back as a dedicated page.
# @app.get("/monitoring", response_class=HTMLResponse)
# def monitoring_page(request: Request):
#     """Monitoring page."""
#     return render(request, "monitoring.html")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=settings.HOST, port=settings.PORT)
